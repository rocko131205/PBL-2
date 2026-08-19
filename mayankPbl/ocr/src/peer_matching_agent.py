from __future__ import annotations
from typing import Any, Dict
import json
import requests

def run_peer_matching(
    record: Any, 
    saas_metrics: Dict[str, Any], 
    base_url: str, 
    model: str, 
    api_key: str
) -> Dict[str, Any]:
    """
    Uses an LLM to identify similar SaaS peers based on the company's financial profile.
    This acts as the PeerMatchingAgent in the LangGraph workflow.
    """
    
    if not record.revenue:
        return {"error": "Missing revenue data for peer matching."}
        
    latest_rev = record.revenue[-1].value
    growth = saas_metrics.get("growth_rate_pct", 0)
    rule_of_40 = saas_metrics.get("rule_of_40", 0)
    entity_id = getattr(record, 'entity_id', 'The target company')
    currency = getattr(record, 'currency', 'Unknown Currency')
    
    prompt = f"""
    You are a SaaS specialized financial analyst. 
    A company ({entity_id}) has the following profile:
    - Latest Annual Revenue: {latest_rev:,.2f} {currency}
    - Growth Rate: {growth:.2f}%
    - Rule of 40: {rule_of_40:.2f}
    
    Based on this profile, identify 3 publicly traded global SaaS peers that have a similar size and growth profile.
    CRITICAL INSTRUCTIONS:
    1. Do NOT include {entity_id} in your list of peers!
    2. UNIQUE PEERS ONLY: Ensure all 3 peers are completely distinct companies. Do not list the same company twice.
    3. Currency Normalization: The target company's revenue is in {currency}. Before searching for peers, mentally convert this revenue into a global benchmark (like USD) to understand its true global scale. 
    4. Ensure that the peers you select genuinely match this normalized scale (do not compare a $10M local startup to a $10B global giant).
    Provide your output STRICTLY as a JSON array of objects with keys: 
    "company_name", "ticker", "estimated_revenue_usd" (string, e.g. "$1B"), "estimated_growth_rate" (number), "estimated_profit_margin" (number), "estimated_rule_of_40" (number), "competitive_delta" (1 concise sentence comparing them to {entity_id}).
    Do not include any markdown formatting, only the JSON.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert SaaS financial analyst. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    try:
        resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        peers = json.loads(content)
        return {"peers": peers}
    except Exception as e:
        return {"error": str(e)}
