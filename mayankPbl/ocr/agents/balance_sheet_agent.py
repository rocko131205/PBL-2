"""Balance Sheet Agent wrapper for the Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.balance_sheet_agent import run_balance_sheet_agent


def run(
    *,
    json_path: str | Path,
    base_url: str,
    model: str,
    api_key: str = "local",
) -> dict[str, Any]:
    """Run the Balance Sheet Agent directly from the saved OCR output file."""
    return run_balance_sheet_agent(
        json_path=Path(json_path),
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
