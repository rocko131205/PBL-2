"""Background analysis jobs.

The LangGraph pipeline calls an LLM and live data providers and can run for a minute
or more, so it can't live inside a request. `start()` records the run and hands it to a
small thread pool; the browser polls `GET /api/analysis/{id}` for per-stage progress.

Runs are in-process, which matches the single-instance deployment. If the server
restarts mid-run, `recover_interrupted()` marks those runs failed instead of leaving
them "running" forever.
"""
from __future__ import annotations

import os
import secrets
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from api import workspace
from api.report import redact_strings
from finveritas.analysis.workflow import PIPELINE_STAGES, run_analysis
from finveritas.auth.db import get_analyses, get_analysis_locks, get_file_history
from finveritas.ingestion.credibility import run_verification
from finveritas.security import ratelimit

ACTIVE = ("queued", "running")
RUN_MAX = 10
RUN_WINDOW_MINUTES = 10

_SOURCE_TYPE = {"pdf": "bloomberg_pdf", "ticker": "ticker", "csv": "csv"}
# The pipeline carries its configuration in its state; none of it may be stored or shown to users.
_PRIVATE_STATE_KEYS = ("llm_api_key", "llm_base_url", "llm_model", "fmp_api_key", "news_api_key")
_executor = ThreadPoolExecutor(max_workers=int(os.getenv("ANALYSIS_WORKERS", "2")), thread_name_prefix="analysis")


def _submit(fn: Callable[..., None], *args: Any) -> None:
    """Indirection so tests can run jobs inline."""
    _executor.submit(fn, *args)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _llm_settings() -> dict[str, str]:
    return {
        "llm_base_url": os.getenv("LLM_BASE_URL") or os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
        "llm_model": os.getenv("LLM_MODEL", "qwen2.5-coder-1.5b-instruct-mlx"),
        "llm_api_key": os.getenv("LLM_API_KEY", "local"),
    }


def throttled(user_id: str) -> bool:
    key = f"analysis:{user_id}"
    if ratelimit.is_limited(key, RUN_MAX, RUN_WINDOW_MINUTES):
        return True
    ratelimit.record(key, RUN_WINDOW_MINUTES)
    return False


# ── One run per user, enforced atomically ────────────────────────────────────
#
# The lock document's _id is the user id, so inserting it is an atomic "claim": a second concurrent
# start gets DuplicateKeyError and is refused. The running job refreshes `heartbeat` at every stage.
# A lock whose heartbeat is older than STALE_SECONDS belongs to a dead process and may be taken over.

STALE_SECONDS = int(os.getenv("ANALYSIS_STALE_SECONDS", "600"))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_stale(lock: dict[str, Any]) -> bool:
    return (_now() - _aware(lock["heartbeat"])).total_seconds() > STALE_SECONDS


class AlreadyRunning(Exception):
    def __init__(self, analysis_id: str | None):
        super().__init__("An analysis is already running.")
        self.analysis_id = analysis_id


def _acquire(user_id: str) -> None:
    locks = get_analysis_locks()
    try:
        locks.insert_one({"_id": user_id, "analysis_id": None, "heartbeat": _now()})
        return
    except DuplicateKeyError:
        pass
    existing = locks.find_one({"_id": user_id})
    if existing is None:  # released between our insert and read — try once more
        return _acquire(user_id)
    if _is_stale(existing):
        # Take over from a dead run; the conditional update means only one contender wins.
        cutoff = _now() - timedelta(seconds=STALE_SECONDS)
        won = locks.find_one_and_update({"_id": user_id, "heartbeat": {"$lt": cutoff}},
                                        {"$set": {"heartbeat": _now(), "analysis_id": None}})
        if won:
            if won.get("analysis_id"):
                _fail_run(ObjectId(won["analysis_id"]), INTERRUPTED)
            return
    raise AlreadyRunning(existing.get("analysis_id"))


def _release(user_id: str, analysis_id: ObjectId | None = None) -> None:
    query: dict[str, Any] = {"_id": user_id}
    if analysis_id is not None:
        query["analysis_id"] = str(analysis_id)  # never release a lock that has since been taken over
    get_analysis_locks().delete_one(query)


def _heartbeat(user_id: str) -> None:
    get_analysis_locks().update_one({"_id": user_id}, {"$set": {"heartbeat": _now()}})


INTERRUPTED = "The server restarted while this analysis was running. Please run it again."


def _fail_run(analysis_id: ObjectId, message: str) -> None:
    get_analyses().update_one(
        {"_id": analysis_id, "status": {"$in": list(ACTIVE)}},
        {"$set": {"status": "failed", "finished_at": _now(), "error": message}},
    )


def reap(doc: dict[str, Any]) -> dict[str, Any]:
    """If `doc` is an in-flight run whose process has died, mark it failed. Safe to call on any run.

    A run is alive only while its lock is held by it with a fresh heartbeat. This is checked lazily
    (when a run is read) as well as at startup, so a run orphaned by a crash is noticed either way —
    and a run that ANOTHER live process is executing is never touched.
    """
    if doc.get("status") not in ACTIVE:
        return doc
    lock = get_analysis_locks().find_one({"_id": doc["user_id"]})
    mine = lock is not None and lock.get("analysis_id") in (None, str(doc["_id"]))
    if mine and not _is_stale(lock):
        return doc
    _fail_run(doc["_id"], INTERRUPTED)
    return get_analyses().find_one({"_id": doc["_id"]}) or doc


def start(user_id: str, ws: dict[str, Any]) -> str:
    """Claim the user's run slot, create the run record and queue the work. Returns the run id.

    Raises AlreadyRunning if this user already has a live run.
    """
    _acquire(user_id)
    try:
        return _create_and_submit(user_id, ws)
    except Exception:
        _release(user_id)
        raise


def _create_and_submit(user_id: str, ws: dict[str, Any]) -> str:
    doc = {
        "user_id": user_id,
        "status": "queued",
        "created_at": _now(),
        "stages": [{"key": k, "label": label, "status": "pending"} for k, label in PIPELINE_STAGES],
        "entity": str((ws["payload"].get("entity") or {}).get("entity_id") or "UNKNOWN"),
        "source": ws["source"],
        "source_label": ws["source_label"],
        "result": None,
        "error": None,
        "dscr": None,
        "ai": {"explain": None, "qa": []},
    }
    analysis_id = get_analyses().insert_one(doc).inserted_id
    get_analysis_locks().update_one({"_id": user_id}, {"$set": {"analysis_id": str(analysis_id), "heartbeat": _now()}})
    workspace.update(user_id, {"analysis_id": str(analysis_id)})
    # The data to analyse is captured now, so later edits to the workspace can't change this run.
    payload = workspace.clean(workspace.display_payload(ws))
    _submit(_run, analysis_id, user_id, payload, _SOURCE_TYPE[ws["source"]], ws.get("credibility"), ws.get("ticker"))
    return str(analysis_id)


def _set_stage(analysis_id: ObjectId, key: str, status: str) -> None:
    get_analyses().update_one(
        {"_id": analysis_id, "stages.key": key},
        {"$set": {"stages.$.status": status}},
    )


def _run(analysis_id: ObjectId, user_id: str, payload: dict[str, Any], source_type: str,
         credibility: dict[str, Any] | None, ticker: str | None) -> None:
    runs = get_analyses()
    in_flight = {"_id": analysis_id, "status": {"$in": list(ACTIVE)}}  # writes only land while the run is still live
    runs.update_one(in_flight, {"$set": {"status": "running", "started_at": _now()}})

    def on_step(event: str, key: str) -> None:
        _set_stage(analysis_id, key, "running" if event == "start" else "done")
        _heartbeat(user_id)  # proves to other processes that this run is alive

    try:
        completed = False
        try:
            state = run_analysis(payload=payload, source_type=source_type, dscr_inputs={}, on_step=on_step,
                                 **_llm_settings())
            for key in _PRIVATE_STATE_KEYS:
                state.pop(key, None)
            # Exception text from failed stages can end up in any narrative field, so every string is scrubbed.
            res = runs.update_one(in_flight, {"$set": {
                "status": "done", "finished_at": _now(), "result": redact_strings(workspace.clean(state)),
            }})
            completed = res.modified_count == 1  # 0 if the run was already declared dead meanwhile
        except Exception as exc:
            ref = secrets.token_hex(4)
            print(f"[analysis {ref}] failed: {type(exc).__name__}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
            runs.update_one(in_flight, {"$set": {
                "status": "failed", "finished_at": _now(),
                "error": f"The analysis could not be completed (reference {ref}).",
            }})
        if completed:
            _record_history(analysis_id, user_id, payload, source_type, credibility, ticker)
    finally:
        _release(user_id, analysis_id)


def _record_history(analysis_id: ObjectId, user_id: str, payload: dict[str, Any], source_type: str,
                    credibility: dict[str, Any] | None, ticker: str | None) -> None:
    """One 'My file history' row per completed analysis. Never fails the run."""
    try:
        score = (credibility or {}).get("score")
        if score is None:
            report = run_verification(source=source_type, payload=payload, ticker=ticker,
                                      fmp_api_key=os.getenv("FMP_API_KEY", ""))
            score = report.score
        run = get_analyses().find_one({"_id": analysis_id}, {"entity": 1, "source": 1, "source_label": 1})
        get_file_history().insert_one({
            "user_id": ObjectId(user_id),
            "analysis_id": str(analysis_id),
            "source_type": run["source"],
            "source_label": run["source_label"],
            "entity_name": run["entity"],
            "fields_loaded": sorted((payload.get("time_series") or {}).keys()),
            "credibility_score": score,
            "timestamp": _now(),
        })
    except Exception as exc:  # history is a convenience, not part of the analysis
        print(f"[analysis] could not record history: {type(exc).__name__}: {exc}", file=sys.stderr)


def recover_interrupted() -> int:
    """Called at startup: fail in-flight runs whose process has died.

    Uses the same liveness rule as `reap`, so a run another live worker or instance is still
    executing (fresh heartbeat) is left alone.
    """
    failed = 0
    for doc in get_analyses().find({"status": {"$in": list(ACTIVE)}}):
        if reap(doc).get("status") == "failed":
            failed += 1
    return failed
