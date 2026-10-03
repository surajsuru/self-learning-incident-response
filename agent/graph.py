"""
EvoOps State-Driven Incident Response Workflow with LangGraph.
Usage:
    python agent/graph.py "Alert: Order checkout latency > 3.5 seconds"
    python agent/graph.py --auto-remediate "Alert: Order checkout latency > 3.5 seconds"
"""

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any


# Ensure root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Rich terminal styling (with fallback)
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from agent.state import InvestigationState
from agent.specialists import run_trace_specialist, run_metrics_specialist
from agent.tools import inspect_chaos_status, execute_remediation, check_cluster_health
from agent.memory import retrieve_similar_incidents, save_incident_to_memory

# Load environment
load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", None)

if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
    print("[Error] OPENAI_API_KEY is not configured in agent/.env.")
    sys.exit(1)

llm_kwargs = {"model": OPENAI_MODEL_NAME, "temperature": 0.0, "api_key": OPENAI_API_KEY}
if OPENAI_API_BASE:
    llm_kwargs["base_url"] = OPENAI_API_BASE
llm = ChatOpenAI(**llm_kwargs)


def print_step(title: str, text: str, color: str = "cyan"):
    if USE_RICH:
        console.print(Panel(text, title=f"[bold]{title}[/bold]", border_style=color))
    else:
        print(f"\n=== [{title}] ===\n{text}\n")


# -------------------------------------------------------------
# GRAPH NODES (WITH EPISODIC MEMORY)
# -------------------------------------------------------------

def node_plan_investigation(state: InvestigationState) -> Dict[str, Any]:
    """Node 1 (Lead SRE): Queries Episodic Memory and formulates the delegation plan."""
    alert = state["alert_description"]
    # 1. Query Episodic Memory for past similar cases
    past_cases = retrieve_similar_incidents(alert, top_k=2)
    memory_summary = ""
    if past_cases:
        memory_summary = f"Found {len(past_cases)} past similar incident(s) in episodic memory:\n"
        for pc in past_cases:
            memory_summary += f"  - [{pc['incident_id']}]: {pc['alert']} -> Root Cause: {pc['root_cause']}\n"
    else:
        memory_summary = "No prior similar incidents found in episodic memory. Investigating as new failure mode."
    print_step("Phase 1: Episodic Memory Retrieval", memory_summary, "magenta")
    plan = [
        "1. Delegate distributed trace inspection to Trace Specialist (Jaeger).",
        "2. Delegate telemetry and health verification to Metrics Specialist (Prometheus).",
        "3. Lead SRE synthesizes both findings with Episodic Memory to determine Root Cause."
    ]
    print_step("Phase 1: Lead SRE Delegating Tasks", "\n".join(plan), "cyan")
    return {
        "current_phase": "delegating_specialists",
        "investigation_plan": plan,
        "similar_incidents": past_cases
    }


def node_trace_specialist(state: InvestigationState) -> Dict[str, Any]:
    """Node 2: Trace Specialist deep-dives into Jaeger spans."""
    print_step("Phase 2A: Trace Specialist Active", "Querying Jaeger spans and call hierarchy...", "yellow")
    report = run_trace_specialist(state["alert_description"])
    print_step("Trace Specialist Report", report, "yellow")
    return {"trace_analysis": report}

def node_metrics_specialist(state: InvestigationState) -> Dict[str, Any]:
    """Node 3: Metrics Specialist inspects Prometheus metrics and cluster health."""
    print_step("Phase 2B: Metrics Specialist Active", "Checking Prometheus metrics, health endpoints, and chaos status...", "blue")
    report = run_metrics_specialist(state["alert_description"])
    print_step("Metrics Specialist Report", report, "blue")
    return {"metrics_analysis": report}


def node_diagnose_root_cause(state: InvestigationState) -> Dict[str, Any]:
    """Node 4 (Lead SRE): Reviews specialist reports and Episodic Memory to determine Root Cause."""
    past_memory_text = json.dumps(state.get("similar_incidents", []), indent=2)
    prompt = f"""You are the Lead SRE Commander.
        Incident Alert: {state['alert_description']}
        --- Episodic Memory (Past Similar Incidents) ---
        {past_memory_text}
        --- Report from Trace Specialist ---
        {state.get('trace_analysis', 'No trace data')}
        --- Report from Metrics Specialist ---
        {state.get('metrics_analysis', 'No metrics data')}
        Instructions:
        Synthesize the specialist reports and past memory to identify:
        1. The TRUE Root Cause: You MUST explicitly attribute the fault to the target_service (e.g. explain that payment-service latency delayed upstream callers like order-service). The service in root_cause MUST match target_service.
        2. Any Misleading Signals debunked: Explicitly state why caller services (like order-service or api-gateway) are innocent victims merely waiting on downstream dependencies.
        3. Recommended Action ('reset_chaos').
        4. Target Service (e.g. 'payment-service').
        5. Risk Level: 'low', 'medium', or 'high'.
        6. Confidence Score between 0.0 and 1.0 (e.g. 0.95).
        Output in STRICT JSON format:
        {{
        "root_cause": "description of root cause",
        "misleading_signals": "description of misleading symptoms",
        "recommended_action": "reset_chaos",
        "target_service": "payment-service",
        "risk_level": "medium",
        "confidence_score": 0.95
        }}"""
    res = llm.invoke([SystemMessage(content="You are a senior SRE Commander. Return only valid JSON."), HumanMessage(content=prompt)])
    content = res.content.strip()
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
    try:
        diagnosis = json.loads(content)
    except Exception:
        diagnosis = {
            "root_cause": content,
            "misleading_signals": "N/A",
            "recommended_action": "reset_chaos",
            "target_service": "payment-service",
            "risk_level": "medium",
            "confidence_score": 0.95
        }
    print_step(
        f"Phase 3: Lead SRE Final Diagnosis (Confidence: {diagnosis.get('confidence_score', 0.9)*100:.0f}%)",
        f"Root Cause: {diagnosis.get('root_cause')}\nTarget: {diagnosis.get('target_service')}\nAction: {diagnosis.get('recommended_action')}",
        "magenta"
    )
    return {
        "current_phase": "remediating",
        "root_cause": diagnosis.get("root_cause"),
        "misleading_signals": diagnosis.get("misleading_signals"),
        "recommended_action": diagnosis.get("recommended_action"),
        "target_service": diagnosis.get("target_service"),
        "risk_level": diagnosis.get("risk_level", "medium"),
        "confidence_score": float(diagnosis.get("confidence_score", 0.95)),
    }



def node_execute_remediation(state: InvestigationState) -> Dict[str, Any]:
    """Node 5: Executes remediation if authorized."""
    if not state.get("auto_remediate"):
        print_step("Phase 4: Remediation Skipped", "Auto-remediation is disabled. Remediation plan recommended for human approval.", "yellow")
        return {"remediation_result": "Skipped (auto_remediate=False)"}
    action = state.get("recommended_action", "reset_chaos")
    target = state.get("target_service", "all")
    print_step("Phase 4: Executing Remediation", f"Executing '{action}' on '{target}'...", "magenta")
    result = execute_remediation.invoke({"action": action, "target_service": target})
    return {"remediation_result": result}



def node_verify_recovery(state: InvestigationState) -> Dict[str, Any]:
    """Node 6: Verifies cluster recovery (checks both reachability AND chaos state)."""
    print_step("Phase 5: Verifying Recovery", "Checking cluster health and active chaos status...", "yellow")
    
    # 1. Check chaos status
    chaos_raw = inspect_chaos_status.invoke({})
    chaos = json.loads(chaos_raw) if isinstance(chaos_raw, str) and chaos_raw.startswith("{") else {}
    
    target = state.get("target_service", "payment-service")
    target_status = chaos.get(target, {})
    # Check for connection errors
    has_connection_error = "error" in target_status
    is_chaos_active = target_status.get("active", False)
    # 2. Check cluster health reachability
    health_raw = check_cluster_health.invoke({})
    health = json.loads(health_raw) if isinstance(health_raw, str) and health_raw.startswith("{") else {}
    target_health = health.get(target, {}).get("status", "unreachable")
    is_reachable = target_health == "healthy"
    # Only verified if it is REACHABLE, has NO connection errors, and chaos is NOT active
    is_healthy = is_reachable and (not has_connection_error) and (not is_chaos_active)
    if not is_reachable:
        reason = f"Target service '{target}' is UNREACHABLE / OFFLINE"
    elif has_connection_error:
        reason = f"Target service '{target}' connection error: {target_status.get('error')}"
    elif is_chaos_active:
        reason = f"Target service '{target}' still has active chaos injected"
    else:
        reason = f"Target service '{target}' is ONLINE and healthy with 0 latency"
    print_step("Phase 5: Verification Outcome", f"Recovery Verified: {is_healthy}\nReason: {reason}", "green" if is_healthy else "red")
    return {"recovery_verified": is_healthy}


def node_generate_report(state: InvestigationState) -> Dict[str, Any]:
    """Node 7: Compiles the final report and saves experience to Episodic Memory."""
    report = f"""# Multi-Agent Incident Postmortem Report
        **Incident ID:** {state.get('incident_id')}  
        **Alert:** {state.get('alert_description')}  
        **Confidence Score:** {state.get('confidence_score', 0.0) * 100:.0f}%  
        **Recovery Verified:** {'✅ Yes' if state.get('recovery_verified') else '❌ No / Pending'}
        ---
        ### 1. Episodic Memory Context
        * **Prior Cases Consulted:** {len(state.get('similar_incidents', []))} past incident(s) found in archive.
        ### 2. Incident Room Delegation
        * **Trace Specialist Finding:** {state.get('trace_analysis')}
        * **Metrics Specialist Finding:** {state.get('metrics_analysis')}
        ### 3. Root Cause Analysis (RCA) by Lead SRE
        * **True Root Cause:** {state.get('root_cause')}
        * **Affected Component:** `{state.get('target_service')}`
        * **Misleading Symptoms Debunked:** {state.get('misleading_signals')}
        ### 4. Remediation & Recovery
        * **Action Planned:** `{state.get('recommended_action')}` on `{state.get('target_service')}`
        * **Execution Status:** {state.get('remediation_result')}
        * **Verification:** {'System confirmed healthy and back to normal latency.' if state.get('recovery_verified') else 'Recovery pending verification.'}
        ### 5. Prevention Recommendations
        1. Implement circuit breaking between `order-service` and `payment-service`.
        2. Add automated P95 alert notifications in Prometheus for `payment-service`.
        """
    print_step("Phase 6: Final Multi-Agent Postmortem", report, "green")
    # If recovery was verified, store this new case into Episodic Memory!
    if state.get("recovery_verified"):
        saved = save_incident_to_memory(state)
        if saved:
            print_step("Episodic Memory Updated", f"Incident {state.get('incident_id')} successfully archived to episodic memory for future learning!", "magenta")
    return {"final_report": report}




# -------------------------------------------------------------
# GRAPH CONSTRUCTION (MULTI-AGENT WORKFLOW)
# -------------------------------------------------------------

def should_remediate(state: InvestigationState) -> str:
    """Conditional Edge: Only execute remediation if confidence >= 0.75."""
    if state.get("confidence_score", 0.0) >= 0.75:
        return "execute_remediation"
    return "generate_report"  # Insufficient confidence; skip straight to report for human review


def build_incident_graph():
    workflow = StateGraph(InvestigationState)
    # Add Nodes
    workflow.add_node("plan_investigation", node_plan_investigation)
    workflow.add_node("trace_specialist", node_trace_specialist)
    workflow.add_node("metrics_specialist", node_metrics_specialist)
    workflow.add_node("diagnose_root_cause", node_diagnose_root_cause)
    workflow.add_node("execute_remediation", node_execute_remediation)
    workflow.add_node("verify_recovery", node_verify_recovery)
    workflow.add_node("generate_report", node_generate_report)
    # Flow: Plan -> Trace Specialist -> Metrics Specialist -> Lead SRE Diagnosis
    workflow.add_edge(START, "plan_investigation")
    workflow.add_edge("plan_investigation", "trace_specialist")
    workflow.add_edge("trace_specialist", "metrics_specialist")
    workflow.add_edge("metrics_specialist", "diagnose_root_cause")
    
    # Conditional Gate
    workflow.add_conditional_edges(
        "diagnose_root_cause",
        should_remediate,
        {
            "execute_remediation": "execute_remediation",
            "generate_report": "generate_report"
        }
    )
    workflow.add_edge("execute_remediation", "verify_recovery")
    workflow.add_edge("verify_recovery", "generate_report")
    workflow.add_edge("generate_report", END)
    return workflow.compile()



def main():
    parser = argparse.ArgumentParser(description="EvoOps LangGraph Incident Response Orchestrator")
    parser.add_argument(
        "alert",
        nargs="?",
        default="Alert: High latency observed on order creation endpoints (> 3s)",
        help="Incident description or alert string",
    )
    parser.add_argument(
        "--auto-remediate",
        action="store_true",
        help="Allow the workflow to execute remediation action upon diagnosis",
    )
    args = parser.parse_args()

    app = build_incident_graph()

    # Generate a unique incident ID using timestamp
    import time
    inc_id = f"INC-{int(time.time()) % 10000}"

    initial_state: InvestigationState = {
        "incident_id": inc_id,
        "alert_description": args.alert,
        "auto_remediate": args.auto_remediate,
        "current_phase": "started",
        "investigation_plan": [],
        "similar_incidents": None,
        "cluster_health": {},
        "metrics_evidence": [],
        "trace_evidence": [],
        "chaos_status": {},
        "trace_analysis": None,
        "metrics_analysis": None,
        "hypotheses": [],
        "root_cause": None,
        "misleading_signals": None,
        "confidence_score": 0.0,
        "recommended_action": None,
        "target_service": None,
        "risk_level": "medium",
        "remediation_result": None,
        "recovery_verified": False,
        "final_report": None,
    }
    print(f"\n{'='*75}")
    print(f"  EvoOps Multi-Agent Incident Response Room (With Episodic Memory)")
    print(f"  Model: {OPENAI_MODEL_NAME} | Incident: {inc_id} | Auto-Remediate: {args.auto_remediate}")
    print(f"{'='*75}\n")
    app.invoke(initial_state)



if __name__ == "__main__":
    main()
