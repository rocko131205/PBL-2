"""PDF → JSON parser for the web app.

Wraps the OCR pipeline (extractor → parser → builder) so the Streamlit app can
turn uploaded PDFs into the repo's JSON payload **in memory**. Nothing is written
to disk — data flows through the app via session state (and MongoDB for history).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from finveritas.ingestion.pdf.builder import build_company_json
from finveritas.ingestion.pdf.extractor import extract_pdf
from finveritas.ingestion.pdf.parser import parse_statement


def parse_pdf_to_json(
    *,
    uploads: list[tuple[bytes, str]],
    output_dir: str | Path = "output",  # kept for call-site compatibility; unused (no disk writes)
) -> tuple[dict[str, Any], None, dict[str, Any]]:
    """Parse one or more uploaded PDFs and merge them into the repo's JSON schema.

    Passing both an Income Statement PDF and a Balance Sheet PDF unlocks all metrics.

    Returns ``(payload, None, {})`` — the payload dict plus two legacy slots kept
    only so existing call sites unpack cleanly. No files are written.
    """
    if not uploads:
        raise ValueError("No PDF files provided")

    parsed_statements = []
    with tempfile.TemporaryDirectory() as td:
        for idx, (pdf_bytes, filename) in enumerate(uploads):
            suffix = "" if filename.lower().endswith(".pdf") else ".pdf"
            pdf_path = Path(td) / f"upload_{idx}{suffix or Path(filename).suffix}"
            pdf_path.write_bytes(pdf_bytes)

            content = extract_pdf(pdf_path)
            if not content.pages:
                raise ValueError(f"No pages extracted from '{filename}'")

            parsed = parse_statement(content)
            parsed.source_file = filename  # for traceability
            if parsed.data:
                parsed_statements.append(parsed)

        if not parsed_statements:
            raise ValueError("No recognised financial data extracted from any uploaded PDF")

        payload = build_company_json(parsed_statements)

    return payload, None, {}


def payload_to_agent_files(
    payload: dict[str, Any],
    output_dir: str | Path = "output",  # kept for call-site compatibility; unused (no disk writes)
) -> tuple[dict[str, Any], None, dict[str, Any]]:
    """Pass an in-memory payload (yfinance / CSV) straight through, no disk writes.

    Returns ``(payload, None, {})`` to match :func:`parse_pdf_to_json`.
    """
    return payload, None, {}
