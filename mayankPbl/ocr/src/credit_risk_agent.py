from __future__ import annotations
from typing import Any, Dict
import json
import requests

def run_credit_risk_assessment(
    record: Any,
    dscr_ratio: float,
    saas_metrics: Dict[str, Any],
    peers: Dict[str, Any],
    base_url: str,
    model: str,
    api_key: str
) -> Dict[str, Any]:
    """
    Final synthesis agent that generates the credit risk report.
    """
    
    qualitative_context = getattr(record, 'qualitative_context', '')
    qualitative_str = f"Management Commentary / Qualitative Strategy:\n{qualitative_context}" if qualitative_context else ""
    
    prompt = f"""
    You are a Credit Risk Officer specializing in SaaS companies.
    Review the following financial profile:
    
    DSCR (Debt Service Coverage Ratio): {dscr_ratio:.2f}
    SaaS Rule of 40: {saas_metrics.get('rule_of_40', 0):.2f}%
    SaaS Growth Rate: {saas_metrics.get('growth_rate_pct', 0):.2f}%
    
    {qualitative_str}
    
    Identified Peers:
    {json.dumps(peers, indent=2)}
    
    Write a concise credit risk summary. Include:
    1. A risk rating (Low, Moderate, High)
    2. A brief analysis of their debt serviceability (DSCR).
    3. A brief analysis of their SaaS health (Rule of 40) compared to typical peers.
    4. Explicitly synthesize the quantitative metrics with the Qualitative Strategy / Management Commentary provided above (e.g. how does management's strategic pivot or noted risks affect their ability to service debt?).
    
    Output strictly as a JSON object with exactly these 3 keys: "risk_rating", "analysis", "recommendation".
    CRITICAL: The values for "analysis" and "recommendation" MUST be plain text strings (e.g. paragraphs). Do NOT return nested JSON objects or arrays for these fields.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a Credit Risk Officer. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    try:
        resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        report = json.loads(content)
        return {"report": report}
    except Exception as e:
        return {"error": str(e)}
