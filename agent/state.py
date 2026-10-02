"""
EvoOps Investigation State Definition for LangGraph.
"""

from typing import Dict, Any, List, Optional
from typing_extensions import TypedDict


class InvestigationState(TypedDict):
    # Incident Inputs
    incident_id: str
    alert_description: str
    auto_remediate: bool

    # Investigation Lifecycle
    current_phase: str
    investigation_plan: List[str]

    # Episodic Memory (Phase 12)
    similar_incidents: Optional[List[Dict[str, Any]]]  # Retrieved past incident cases
    
    # Telemetry Evidence Collected
    cluster_health: Dict[str, Any]
    metrics_evidence: List[Dict[str, Any]]
    trace_evidence: List[Dict[str, Any]]
    chaos_status: Dict[str, Any]

    # Specialist Reports
    trace_analysis: Optional[str]      # Written by Trace Specialist
    metrics_analysis: Optional[str]    # Written by Metrics Specialist
    
    # Reasoning & Diagnosis
    hypotheses: List[str]
    root_cause: Optional[str]
    misleading_signals: Optional[str]
    confidence_score: float  # 0.0 to 1.0

    # Remediation & Recovery
    recommended_action: Optional[str]
    target_service: Optional[str]
    risk_level: str  # "low", "medium", "high"
    remediation_result: Optional[str]
    recovery_verified: bool

    # Final Output
    final_report: Optional[str]
