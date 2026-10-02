"""
EvoOps Episodic Memory Engine.
Stores resolved incident cases and retrieves relevant historical runbooks.
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

MEMORY_DIR = Path(__file__).parent / "data"
MEMORY_FILE = MEMORY_DIR / "episodic_memory.json"

# Initial seed of institutional historical incidents
DEFAULT_INCIDENT_ARCHIVE = [
    {
        "incident_id": "INC-HIST-01",
        "timestamp": "2026-08-15T14:30:00Z",
        "alert": "Alert: Database query connection pool exhaustion on order-service",
        "symptoms": "High P99 latency on POST /orders (>4s); database connection timeout errors in order-service logs.",
        "root_cause": "PostgreSQL connection pool exhausted due to long-running unindexed transaction locks.",
        "remediation_action": "reset_chaos",
        "target_service": "order-service",
        "resolution_notes": "Cleared hung database queries and restarted order-service connection pool."
    },
    {
        "incident_id": "INC-HIST-02",
        "timestamp": "2026-09-02T09:15:00Z",
        "alert": "Alert: 502 Bad Gateway spike on inventory stock verification",
        "symptoms": "Inventory stock check endpoint returning 502; Redis cache read timeout.",
        "root_cause": "Redis cache degradation on inventory-service forcing database fallback overload.",
        "remediation_action": "reset_chaos",
        "target_service": "inventory-service",
        "resolution_notes": "Reset inventory-service chaos and verified Redis container ping health."
    }
]


def init_memory():
    """Ensures memory storage directory and JSON archive exist."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_INCIDENT_ARCHIVE, f, indent=2)


def retrieve_similar_incidents(alert_query: str, top_k: int = 2) -> List[Dict[str, Any]]:
    """
    Searches episodic memory for past incidents with similar symptoms or alert keywords.
    """
    init_memory()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
    except Exception:
        return []
    # Simple, explainable keyword & token relevance scoring
    query_tokens = set(alert_query.lower().replace("alert:", "").replace(">", "").split())
    scored = []
    
    for inc in archive:
        target_text = f"{inc.get('alert', '')} {inc.get('symptoms', '')} {inc.get('root_cause', '')}".lower()
        score = sum(1 for token in query_tokens if token in target_text)
        if score > 0:
            scored.append((score, inc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]



def save_incident_to_memory(state: Dict[str, Any]) -> bool:
    """
    Saves a successfully verified incident postmortem into episodic memory.
    """
    init_memory()
    new_case = {
        "incident_id": state.get("incident_id", "INC-AUTO"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "alert": state.get("alert_description"),
        "symptoms": f"Trace: {state.get('trace_analysis', '')[:200]} | Metrics: {state.get('metrics_analysis', '')[:200]}",
        "root_cause": state.get("root_cause"),
        "remediation_action": state.get("recommended_action"),
        "target_service": state.get("target_service"),
        "resolution_notes": f"Verified: {state.get('recovery_verified')}. Confidence: {state.get('confidence_score', 0)*100:.0f}%"
    }
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
        
        # Don't add duplicate incident IDs
        if not any(item.get("incident_id") == new_case["incident_id"] for item in archive):
            archive.append(new_case)
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(archive, f, indent=2)
            return True
    except Exception as e:
        print(f"[Warning] Failed to save incident to episodic memory: {e}")
    return False


