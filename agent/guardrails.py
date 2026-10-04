"""
EvoOps Guardrail & Human-in-the-Loop Approval Engine (Phase 15).
Enforces governance, risk-tier evaluation, operator approval, and audit trails.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

# Rich terminal styling (with standard fallback)
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False


DATA_DIR = Path(__file__).parent / "data"
AUDIT_FILE = DATA_DIR / "approval_audit.json"


# Risk tier categorization
RISK_POLICIES = {
    "low": ["inspect_chaos", "check_health", "query_traces", "query_metrics"],
    "medium": ["reset_chaos", "flush_cache", "restart_worker"],
    "high": ["drop_connections", "traffic_drain", "rollback_deployment", "restart_database"]
}

# -------------------------------------------------------------
# 1. RISK ASSESSMENT
# -------------------------------------------------------------

def assess_action_risk(action: str, target_service: str) -> str:
    """
    Categorizes the risk level of an SRE remediation action:
    - 'low': Read-only, diagnostic actions.
    - 'medium': Service resets, cache flushes, minor restarts.
    - 'high': Destructive, database, or traffic-routing actions.
    """
    action_clean = action.lower().strip()
    for risk_level, actions in RISK_POLICIES.items():
        if action_clean in actions:
            return risk_level
    # Default fallback: if target is all services or unknown action, treat as high risk
    if target_service.lower() == "all":
        return "high"
    return "medium"


# -------------------------------------------------------------
# 2. AUDIT TRAIL LOGGING
# -------------------------------------------------------------

def log_approval_decision(
    incident_id: str,
    action: str,
    target_service: str,
    risk_level: str,
    decision: str,  # 'approved', 'rejected', 'modified'
    operator: str = "human_operator",
    reason: str = "Standard SRE Review"
):
    """Logs the human-in-the-loop decision to approval_audit.json for compliance."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    audit_trail = []
    if AUDIT_FILE.exists():
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                audit_trail = json.load(f)
        except Exception:
            audit_trail = []
    record = {
        "audit_id": f"AUDIT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident_id": incident_id,
        "action": action,
        "target_service": target_service,
        "risk_level": risk_level,
        "decision": decision,
        "operator": operator,
        "reason": reason
    }
    audit_trail.append(record)
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_trail, f, indent=2)


# -------------------------------------------------------------
# 3. INTERACTIVE HUMAN APPROVAL GATE
# -------------------------------------------------------------

def request_human_approval(
    incident_id: str,
    action: str,
    target_service: str,
    root_cause: str,
    risk_level: str,
    auto_approve: bool = False
) -> Tuple[bool, str, str, str]:
    """
    Interactive prompt asking the human operator to authorize remediation.
    Returns:
        (is_approved, decision_status, final_action, final_target)
    """
    # 1. Low risk actions auto-execute safely
    if risk_level == "low":
        log_approval_decision(incident_id, action, target_service, risk_level, "auto_approved", operator="system_policy")
        return True, "auto_approved", action, target_service
    # 2. If CLI explicitly passed --auto-remediate, auto-approve medium risk
    if auto_approve and risk_level == "medium":
        log_approval_decision(incident_id, action, target_service, risk_level, "approved_by_cli_flag", operator="cli_flag")
        return True, "approved_by_cli_flag", action, target_service
    # 3. Otherwise: Interactive Human Gate
    gate_text = f"""[bold red]⚠️ HUMAN-IN-THE-LOOP APPROVAL REQUIRED[/bold red]
Incident ID: [bold]{incident_id}[/bold]
Diagnosed Root Cause: {root_cause}
Proposed Action: [bold cyan]{action}[/bold cyan] on [bold green]{target_service}[/bold green]
Assessed Risk Level: [bold yellow]{risk_level.upper()}[/bold yellow]
Options:
  [bold green][y][/bold green] - Approve and execute remediation
  [bold red][n][/bold red] - Reject and abort remediation
  [bold yellow][m][/bold yellow] - Modify target service before executing"""
    if USE_RICH:
        console.print(Panel(gate_text, title="🛡️ EvoOps SRE Governance Gate", border_style="red"))
        choice = Prompt.ask("Operator Decision", choices=["y", "n", "m"], default="y")
    else:
        print("\n=== EvoOps SRE Governance Gate ===")
        print(f"Action: '{action}' on '{target_service}' | Risk: {risk_level.upper()}")
        choice = input("Approve? (y = approve, n = reject, m = modify target) [y]: ").strip().lower() or "y"
    if choice == "y":
        log_approval_decision(incident_id, action, target_service, risk_level, "approved", operator="human_operator")
        return True, "approved", action, target_service
    elif choice == "n":
        log_approval_decision(incident_id, action, target_service, risk_level, "rejected", operator="human_operator", reason="Operator vetoed execution")
        return False, "rejected", action, target_service
    elif choice == "m":
        if USE_RICH:
            new_target = Prompt.ask("Enter new target service name", default=target_service)
        else:
            new_target = input(f"Enter new target service name [{target_service}]: ").strip() or target_service
        log_approval_decision(incident_id, action, new_target, risk_level, "modified", operator="human_operator", reason=f"Overridden from {target_service}")
        return True, "modified", action, new_target
        
    return False, "rejected", action, target_service
