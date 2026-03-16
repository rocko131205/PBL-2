"""Revenue Agent wrapper for the Streamlit dashboard.

This wraps `src.revenue_agent` so the dashboard can run the agent from the
saved OCR output file in `output/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.revenue_agent import run_revenue_agent


def run(
    *,
    json_path: str | Path,
    base_url: str,
    model: str,
    api_key: str = "local",
) -> dict[str, Any]:
    """Run the Revenue Agent directly from the saved OCR output file.

    Args:
        json_path: Path to the OCR output JSON written to output/.
        base_url/model/api_key: OpenAI-compatible LLM settings.

    Returns:
        {entity, metrics, analysis}
    """
    return run_revenue_agent(
        json_path=Path(json_path),
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
