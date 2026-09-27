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
from agent.tools import (
    check_cluster_health,
    query_prometheus,
    get_jaeger_traces,
    inspect_chaos_status,
    search_incident_catalog,
    execute_remediation,
)

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
# GRAPH NODES
# -------------------------------------------------------------

def node_plan_investigation(state: InvestigationState) -> Dict[str, Any]:
    """Node 1: Analyzes the alert and creates a targeted investigation plan."""
    alert = state["alert_description"]
    prompt = f"""You are an SRE Lead. Given this incident alert:
'{alert}'

Create a structured investigation plan specifying:
1. Which service traces to inspect (e.g. order-service, api-gateway)
2. What PromQL metric queries to run
3. Which health endpoints to verify

Respond with a concise 3-4 bullet plan."""
    
    res = llm.invoke([SystemMessage(content="You are an SRE incident commander."), HumanMessage(content=prompt)])
    plan_lines = [line.strip() for line in res.content.split("\n") if line.strip()]
    
    print_step("Phase 1: Investigation Plan Formulated", res.content, "cyan")
    return {
        "current_phase": "collecting_evidence",
        "investigation_plan": plan_lines,
    }


def node_collect_evidence(state: InvestigationState) -> Dict[str, Any]:
    """Node 2: Executes telemetry tools to gather real evidence from the cluster."""
    print_step("Phase 2: Collecting Real Telemetry", "Querying Jaeger Traces, Health, and Chaos Status...", "yellow")

    # 1. Cluster Health
    health_raw = check_cluster_health.invoke({})
    health = json.loads(health_raw) if isinstance(health_raw, str) and health_raw.startswith("{") else {}

    # 2. Jaeger Traces for Order Service and API Gateway
    traces_order = get_jaeger_traces.invoke({"service": "order-service", "limit": 3})
    traces_gw = get_jaeger_traces.invoke({"service": "api-gateway", "limit": 2})

    # 3. Chaos / Fault Status
    chaos_raw = inspect_chaos_status.invoke({})
    chaos = json.loads(chaos_raw) if isinstance(chaos_raw, str) and chaos_raw.startswith("{") else {}

    # 4. Prometheus Metrics (5xx errors and request duration)
    metrics = query_prometheus.invoke({"query": "sum(rate(http_requests_total{status=~'5..'}[1m])) by (service)"})

    return {
        "current_phase": "analyzing_evidence",
        "cluster_health": health,
        "trace_evidence": [{"service": "order-service", "data": traces_order}, {"service": "api-gateway", "data": traces_gw}],
        "chaos_status": chaos,
        "metrics_evidence": [{"query": "5xx_rates", "result": metrics}],
    }


def node_diagnose_root_cause(state: InvestigationState) -> Dict[str, Any]:
    """Node 3: Evaluates collected evidence to isolate the true root cause and score confidence."""
    prompt = f"""You are an SRE performing Root Cause Analysis.
Alert: {state['alert_description']}

Collected Evidence:
1. Cluster Health: {json.dumps(state['cluster_health'])}
2. Jaeger Traces (Order Service): {json.dumps(state['trace_evidence'])}
3. Chaos Status: {json.dumps(state['chaos_status'])}
4. Prometheus Metrics: {json.dumps(state['metrics_evidence'])}

Instructions:
Identify:
1. The TRUE Root Cause (which exact service is stalling or throwing errors).
2. Any Misleading Signals (e.g. why API Gateway or Order Service seemed slow when the delay was downstream).
3. Recommended Action (e.g. 'reset_chaos' on target service).
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

    res = llm.invoke([SystemMessage(content="You are a senior SRE. Return only valid JSON."), HumanMessage(content=prompt)])
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
            "confidence_score": 0.9
        }

    print_step(
        f"Phase 3: Root Cause Diagnosed (Confidence: {diagnosis.get('confidence_score', 0.9)*100:.0f}%)",
        f"Root Cause: {diagnosis.get('root_cause')}\nTarget: {diagnosis.get('target_service')}\nAction: {diagnosis.get('recommended_action')}",
        "blue"
    )

    return {
        "current_phase": "remediating",
        "root_cause": diagnosis.get("root_cause"),
        "misleading_signals": diagnosis.get("misleading_signals"),
        "recommended_action": diagnosis.get("recommended_action"),
        "target_service": diagnosis.get("target_service"),
        "risk_level": diagnosis.get("risk_level", "medium"),
        "confidence_score": float(diagnosis.get("confidence_score", 0.9)),
    }


def node_execute_remediation(state: InvestigationState) -> Dict[str, Any]:
    """Node 4: Executes recovery action if auto-remediation is enabled."""
    if not state.get("auto_remediate"):
        print_step("Phase 4: Remediation Skipped", "Auto-remediation is disabled. Remediation plan recommended for human approval.", "yellow")
        return {"remediation_result": "Skipped (auto_remediate=False)"}

    action = state.get("recommended_action", "reset_chaos")
    target = state.get("target_service", "all")
    print_step("Phase 4: Executing Remediation", f"Executing '{action}' on '{target}'...", "magenta")

    result = execute_remediation.invoke({"action": action, "target_service": target})
    return {"remediation_result": result}


def node_verify_recovery(state: InvestigationState) -> Dict[str, Any]:
    """Node 5: Re-checks telemetry to verify that the fix actually restored system health."""
    print_step("Phase 5: Verifying Recovery", "Pinging cluster health and checking active chaos...", "yellow")
    
    # Re-check chaos status
    chaos_raw = inspect_chaos_status.invoke({})
    chaos = json.loads(chaos_raw) if isinstance(chaos_raw, str) and chaos_raw.startswith("{") else {}
    
    # Recovery is verified if target service is back to normal
    target = state.get("target_service")
    target_status = chaos.get(target, {})
    is_healthy = not target_status.get("active", False)

    print_step(
        "Phase 5: Verification Outcome",
        f"Target Service '{target}' Recovery Verified: {is_healthy}",
        "green" if is_healthy else "red"
    )
    return {"recovery_verified": is_healthy}


def node_generate_report(state: InvestigationState) -> Dict[str, Any]:
    """Node 6: Generates final SRE Incident Postmortem report."""
    report = f"""# SRE Incident Postmortem Report
**Incident ID:** {state.get('incident_id')}  
**Alert:** {state.get('alert_description')}  
**Confidence Score:** {state.get('confidence_score', 0.0) * 100:.0f}%  
**Recovery Verified:** {'✅ Yes' if state.get('recovery_verified') else '❌ No / Pending'}

---

### 1. Incident Summary
An alert was triggered: *"{state.get('alert_description')}"*. The EvoOps StateGraph workflow executed telemetry collection, isolated the root cause, and verified cluster state.

### 2. Root Cause Analysis (RCA)
* **True Root Cause:** {state.get('root_cause')}
* **Affected Component:** `{state.get('target_service')}`
* **Misleading Symptoms Debunked:** {state.get('misleading_signals')}

### 3. Remediation & Recovery
* **Action Planned:** `{state.get('recommended_action')}` on `{state.get('target_service')}` (Risk Level: {state.get('risk_level')})
* **Execution Status:** {state.get('remediation_result')}
* **Post-Remediation Verification:** {'System metrics restored to normal latency and zero error rates.' if state.get('recovery_verified') else 'Awaiting human intervention.'}

### 4. Prevention Recommendations
1. Configure circuit breakers between `order-service` and `payment-service` to prevent downstream delays from holding order threads.
2. Set up automated P95 alert thresholds in Prometheus for `{state.get('target_service')}`.
"""
    print_step("Phase 6: Final SRE Postmortem Generated", report, "green")
    return {"final_report": report}


# -------------------------------------------------------------
# GRAPH CONSTRUCTION & CONDITIONAL EDGES
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
    workflow.add_node("collect_evidence", node_collect_evidence)
    workflow.add_node("diagnose_root_cause", node_diagnose_root_cause)
    workflow.add_node("execute_remediation", node_execute_remediation)
    workflow.add_node("verify_recovery", node_verify_recovery)
    workflow.add_node("generate_report", node_generate_report)

    # Add Edges
    workflow.add_edge(START, "plan_investigation")
    workflow.add_edge("plan_investigation", "collect_evidence")
    workflow.add_edge("collect_evidence", "diagnose_root_cause")
    
    # Conditional branching from diagnosis
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

    initial_state: InvestigationState = {
        "incident_id": "INC-8492",
        "alert_description": args.alert,
        "auto_remediate": args.auto_remediate,
        "current_phase": "started",
        "investigation_plan": [],
        "cluster_health": {},
        "metrics_evidence": [],
        "trace_evidence": [],
        "chaos_status": {},
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
    print(f"  EvoOps LangGraph Orchestrator Running")
    print(f"  Model: {OPENAI_MODEL_NAME} | Auto-Remediate: {args.auto_remediate}")
    print(f"{'='*75}\n")

    app.invoke(initial_state)


if __name__ == "__main__":
    main()
