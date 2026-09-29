"""Security UI — per-user Security Settings and the admin Security Dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from finveritas.auth.controller import (
    begin_mfa_enrolment, confirm_mfa_enrolment, disable_mfa, get_user_by_id, is_admin,
)
from finveritas.auth.db import get_audit_log, get_sessions
from finveritas.security import audit, mfa, sessions


def _section(title: str, sub: str) -> None:
    st.markdown(f"### {title}")
    st.caption(sub)


def _events_frame(events: list[dict]) -> pd.DataFrame:
    rows = []
    for e in events:
        ts = e.get("timestamp")
        rows.append({
            "Time (UTC)": ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else "—",
            "Event": e.get("event", ""),
            "Outcome": e.get("outcome", ""),
            "Email": e.get("email") or "",
            "IP": e.get("ip") or "",
            "Detail": ", ".join(f"{k}={v}" for k, v in (e.get("detail") or {}).items()),
        })
    return pd.DataFrame(rows)


def page_security_settings(user: dict) -> None:
    """Per-user controls: MFA, active sessions, recent account activity."""
    user_id = user["user_id"]
    db_user = get_user_by_id(user_id) or {}

    st.markdown("## Security Settings")

    # ── MFA ───────────────────────────────────────────────────────────────────
    _section("Two-factor authentication (TOTP)",
             "Protects your account even if your password leaks. Works with Google Authenticator, "
             "Microsoft Authenticator, Authy or 1Password.")
    if db_user.get("mfa_enabled"):
        st.success("Two-factor authentication is **enabled**.")
        with st.form("mfa_disable_form", clear_on_submit=True):
            code = st.text_input("Enter a current code to disable 2FA", max_chars=6)
            if st.form_submit_button("Disable 2FA"):
                ok, msg = disable_mfa(user_id, code)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
    else:
        st.warning("Two-factor authentication is **not enabled**.")
        pending = st.session_state.get("mfa_enrol_secret")
        if not pending:
            if st.button("Set up two-factor authentication"):
                secret, _ = begin_mfa_enrolment(user_id)
                st.session_state["mfa_enrol_secret"] = secret
                st.rerun()
        else:
            uri = mfa.provisioning_uri(pending, db_user.get("email", ""))
            c1, c2 = st.columns([1, 2])
            with c1:
                st.image(mfa.qr_png(uri), caption="Scan with your authenticator app", width=200)
            with c2:
                st.markdown("Can't scan? Enter this key manually:")
                st.code(pending, language=None)
                with st.form("mfa_enrol_form", clear_on_submit=True):
                    code = st.text_input("Enter the 6-digit code shown in the app", max_chars=6)
                    confirmed = st.form_submit_button("Verify and enable")
                if confirmed:
                    ok, msg = confirm_mfa_enrolment(user_id, pending, code)
                    if ok:
                        st.session_state.pop("mfa_enrol_secret", None)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                if st.button("Cancel setup"):
                    st.session_state.pop("mfa_enrol_secret", None)
                    st.rerun()

    st.divider()

    # ── Sessions ──────────────────────────────────────────────────────────────
    _section("Sessions", "Sessions expire after 8 hours or 15 minutes of inactivity.")
    active = sessions.active_count(user_id)
    st.write(f"Active sessions: **{active}**")
    if st.button("Sign out all other sessions"):
        n = sessions.revoke_all(user_id, except_jti=user.get("jti"))
        st.success(f"Signed out {n} other session(s).")

    st.divider()

    # ── Own activity ──────────────────────────────────────────────────────────
    _section("Recent account activity", "Review this for sign-ins you don't recognise.")
    events = audit.recent_events(user_id=user_id, email=db_user.get("email"), limit=25)
    if events:
        st.dataframe(_events_frame(events), hide_index=True, use_container_width=True)
    else:
        st.caption("No activity recorded yet.")


def page_security_dashboard(user: dict) -> None:
    """Admin-only monitoring view. Authorisation is re-checked here, not just in the nav."""
    if not is_admin(user["user_id"]):
        audit.log_event(audit.AUTHZ_DENIED, user_id=user["user_id"], detail={"page": "security_dashboard"})
        st.error("You do not have permission to view this page.")
        return

    st.markdown("## Security Dashboard")
    st.caption("Authentication and abuse signals across all users (last 24 hours).")

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    log = get_audit_log()

    def n(event: str) -> int:
        return log.count_documents({"event": event, "timestamp": {"$gte": since}})

    c = st.columns(5)
    c[0].metric("Successful logins", n(audit.LOGIN_SUCCESS))
    c[1].metric("Failed logins", n(audit.LOGIN_FAILURE))
    c[2].metric("Lockouts", n(audit.LOGIN_LOCKED))
    c[3].metric("OTP failures", n(audit.OTP_FAILURE))
    c[4].metric("Prompt-injection hits", n(audit.PROMPT_INJECTION))

    st.metric("Active sessions (all users)",
              get_sessions().count_documents({"revoked": False, "expires_at": {"$gt": datetime.now(timezone.utc)}}))

    st.markdown("#### Top targeted accounts (failed logins)")
    top = list(log.aggregate([
        {"$match": {"event": audit.LOGIN_FAILURE, "timestamp": {"$gte": since}}},
        {"$group": {"_id": "$email", "failures": {"$sum": 1}, "ips": {"$addToSet": "$ip"}}},
        {"$sort": {"failures": -1}},
        {"$limit": 10},
    ]))
    if top:
        st.dataframe(pd.DataFrame([
            {"Email": t["_id"], "Failures": t["failures"], "Distinct IPs": len([i for i in t["ips"] if i])}
            for t in top
        ]), hide_index=True, use_container_width=True)
    else:
        st.caption("No failed logins in the last 24 hours.")

    st.markdown("#### Top source IPs (failures)")
    ips = list(log.aggregate([
        {"$match": {"outcome": "failure", "timestamp": {"$gte": since}, "ip": {"$ne": None}}},
        {"$group": {"_id": "$ip", "events": {"$sum": 1}, "accounts": {"$addToSet": "$email"}}},
        {"$sort": {"events": -1}},
        {"$limit": 10},
    ]))
    if ips:
        st.dataframe(pd.DataFrame([
            {"IP": i["_id"], "Failure events": i["events"], "Accounts targeted": len([a for a in i["accounts"] if a])}
            for i in ips
        ]), hide_index=True, use_container_width=True)
        st.caption("Many accounts from one IP suggests credential stuffing; many IPs against one account "
                   "suggests a distributed brute-force attempt.")

    st.markdown("#### Recent security events")
    only_failures = st.toggle("Failures only", value=True)
    q = {"outcome": "failure"} if only_failures else {}
    events = list(log.find(q).sort("timestamp", -1).limit(200))
    if events:
        st.dataframe(_events_frame(events), hide_index=True, use_container_width=True)
    else:
        st.caption("No events recorded.")
