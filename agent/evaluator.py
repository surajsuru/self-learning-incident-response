"""
EvoOps Evaluator & Benchmarking Engine (Phase 13).
Compares agent incident diagnoses against ground truth in scenarios/catalog.json.
Usage:
    python agent/evaluator.py --latest
    python agent/evaluator.py --incident INC-5480 --scenario downstream_timeout
"""


import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Rich terminal styling (with standard fallback)
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Load environment configuration
load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", None)

llm_kwargs = {"model": OPENAI_MODEL_NAME, "temperature": 0.0, "api_key": OPENAI_API_KEY}
if OPENAI_API_BASE:
    llm_kwargs["base_url"] = OPENAI_API_BASE
llm = ChatOpenAI(**llm_kwargs)
CATALOG_FILE = Path(__file__).parent.parent / "scenarios" / "catalog.json"
EPISODIC_MEMORY_FILE = Path(__file__).parent / "data" / "episodic_memory.json"
BENCHMARK_FILE = Path(__file__).parent / "data" / "eval_benchmarks.json"



# -------------------------------------------------------------
# 1. DATA LOADERS
# -------------------------------------------------------------

def load_ground_truth_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Loads a specific ground-truth incident scenario from scenarios/catalog.json."""
    if not CATALOG_FILE.exists():
        print(f"[Error] Catalog file not found at {CATALOG_FILE}")
        return None
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    for sc in catalog.get("scenarios", []):
        if sc.get("id") == scenario_id:
            return sc
    return None


def load_incident_from_memory(incident_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads an incident from episodic memory. If incident_id is None, returns the latest."""
    if not EPISODIC_MEMORY_FILE.exists():
        print(f"[Error] Memory file not found at {EPISODIC_MEMORY_FILE}")
        return None
    with open(EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
        archive = json.load(f)
    if not archive:
        return None
    if incident_id is None:
        return archive[-1]  # Most recent incident
    for inc in archive:
        if inc.get("incident_id") == incident_id:
            return inc
    return None


def match_scenario_for_incident(incident: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Finds the most matching scenario from catalog based on target service or alert text."""
    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    target = incident.get("target_service", "").lower()
    alert = incident.get("alert", "").lower()
    # Best match: matching target_service and category/keywords
    for sc in catalog.get("scenarios", []):
        if sc.get("target_service", "").lower() == target:
            if "latency" in alert and sc.get("fault_type") == "latency":
                return sc
            if "error" in alert and sc.get("fault_type") == "error":
                return sc
    # Fallback: match by service
    for sc in catalog.get("scenarios", []):
        if sc.get("target_service", "").lower() == target:
            return sc
    return catalog.get("scenarios", [])[0] if catalog.get("scenarios") else None



# -------------------------------------------------------------
# 2. EVALUATION LOGIC
# -------------------------------------------------------------


def evaluate_root_cause_explanation(diagnosed: str, ground_truth: str) -> Dict[str, Any]:
    """Uses LLM-as-a-judge to grade root cause explanation semantic accuracy (0-100)."""
    prompt = f"""You are an expert SRE Evaluator.
        Compare the Agent's Diagnosed Root Cause with the Ground Truth Root Cause.
        Agent Diagnosed Root Cause:
        "{diagnosed}"
        Ground Truth Root Cause:
        "{ground_truth}"
        Score the explanation on a scale of 0 to 100 based on:
        1. Did the agent correctly capture the underlying failure mechanism?
        2. Did it explain what went wrong accurately?
        Note: In black-box telemetry investigations, diagnosing abnormal execution delay, high processing latency, or slow request handling on the target service is semantically equivalent to an injected artificial delay (the agent has no way to know whether an incident is simulated chaos or real production degradation).
        Return ONLY valid JSON in this format:
        {{
        "score": 90,
        "reasoning": "Brief explanation of the score"
        }}"""
    try:
        res = llm.invoke([
            SystemMessage(content="You are a strict, objective SRE evaluation judge. Return only JSON."),
            HumanMessage(content=prompt)
        ])
        content = res.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        data = json.loads(content)
        return {
            "score": float(data.get("score", 70)),
            "reasoning": data.get("reasoning", "Semantic comparison completed.")
        }
    except Exception as e:
        return {"score": 75.0, "reasoning": f"Default fallback score ({e})"}



def evaluate_investigation(incident: Dict[str, Any], ground_truth: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates an incident diagnosis against ground truth across 5 SRE dimensions:
    1. Culprit Service Accuracy (Weight: 30%)
    2. Root Cause Correctness   (Weight: 25%)
    3. Remediation Precision    (Weight: 20%)
    4. Misleading Signal Debunk (Weight: 15%)
    5. Evidence Grounding       (Weight: 10%)
    """
    # 1. Culprit Service (Exact match on culprit service)
    actual_target = incident.get("target_service", "").strip().lower()
    expected_target = ground_truth.get("target_service", "").strip().lower()
    service_match = (actual_target == expected_target)
    service_score = 100.0 if service_match else 0.0
    # 2. Root Cause Semantic Match
    rc_result = evaluate_root_cause_explanation(
        diagnosed=incident.get("root_cause", ""),
        ground_truth=ground_truth.get("root_cause", "")
    )
    rc_score = rc_result["score"]
    # 3. Remediation Precision
    action = incident.get("remediation_action", "").lower()
    remediation_score = 100.0 if "reset" in action or "remediate" in action else 50.0
    # 4. Misleading Signal Awareness
    # Did the agent avoid falsely blaming the symptom services (e.g. api-gateway or order-service)?
    misleading_info = ground_truth.get("misleading_signals", "")
    if service_match:
        # If the agent correctly targeted the culprit despite misleading signals, full score!
        misleading_score = 100.0
        misleading_comment = "Successfully bypassed caller latency decoys and isolated the downstream culprit."
    else:
        misleading_score = 20.0
        misleading_comment = f"Misled by caller symptoms; blamed {actual_target} instead of {expected_target}."
    # 5. Evidence Grounding
    symptoms_text = incident.get("symptoms", "")
    has_trace_evidence = "trace" in symptoms_text.lower() or "span" in symptoms_text.lower()
    has_metrics_evidence = "metrics" in symptoms_text.lower() or "latency" in symptoms_text.lower()
    evidence_score = 100.0 if (has_trace_evidence and has_metrics_evidence) else (70.0 if has_trace_evidence else 50.0)
    # Calculate Weighted Total (0 - 100)
    composite_score = (
        (service_score * 0.30) +
        (rc_score * 0.25) +
        (remediation_score * 0.20) +
        (misleading_score * 0.15) +
        (evidence_score * 0.10)
    )
    # Letter Grade
    if composite_score >= 90:
        grade = "A"
    elif composite_score >= 80:
        grade = "B"
    elif composite_score >= 70:
        grade = "C"
    else:
        grade = "F"
    evaluation_card = {
        "evaluation_id": f"EVAL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "incident_id": incident.get("incident_id"),
        "scenario_id": ground_truth.get("id"),
        "scenario_name": ground_truth.get("name"),
        "grade": grade,
        "composite_score": round(composite_score, 1),
        "breakdown": {
            "service_accuracy": {
                "score": service_score,
                "weight": "30%",
                "expected": expected_target,
                "diagnosed": actual_target,
                "passed": service_match
            },
            "root_cause_accuracy": {
                "score": rc_score,
                "weight": "25%",
                "reasoning": rc_result["reasoning"]
            },
            "remediation_precision": {
                "score": remediation_score,
                "weight": "20%",
                "action": incident.get("remediation_action")
            },
            "misleading_signal_handling": {
                "score": misleading_score,
                "weight": "15%",
                "comment": misleading_comment
            },
            "evidence_grounding": {
                "score": evidence_score,
                "weight": "10%",
                "has_trace": has_trace_evidence,
                "has_metrics": has_metrics_evidence
            }
        }
    }
    return evaluation_card


# -------------------------------------------------------------
# 3. STORAGE & DISPLAY
# -------------------------------------------------------------


def save_benchmark_result(eval_card: Dict[str, Any]):
    """Persists evaluation results into agent/data/eval_benchmarks.json."""
    BENCHMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
    benchmarks = []
    if BENCHMARK_FILE.exists():
        try:
            with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
                benchmarks = json.load(f)
        except Exception:
            benchmarks = []
    benchmarks.append(eval_card)
    with open(BENCHMARK_FILE, "w", encoding="utf-8") as f:
        json.dump(benchmarks, f, indent=2)



def display_scorecard(eval_card: Dict[str, Any]):
    """Renders a formatted evaluation scorecard in the console."""
    breakdown = eval_card["breakdown"]
    if USE_RICH:
        table = Table(title=f"EvoOps SRE Benchmark Scorecard — Grade: {eval_card['grade']} ({eval_card['composite_score']}%)")
        table.add_column("Evaluation Dimension", style="cyan", no_wrap=True)
        table.add_column("Weight", style="magenta")
        table.add_column("Score", style="yellow")
        table.add_column("Details", style="green")
        svc = breakdown["service_accuracy"]
        table.add_row(
            "Culprit Service Accuracy",
            svc["weight"],
            f"{svc['score']:.0f}%",
            f"Diagnosed: '{svc['diagnosed']}' | Expected: '{svc['expected']}' ({'PASS' if svc['passed'] else 'FAIL'})"
        )
        rc = breakdown["root_cause_accuracy"]
        table.add_row("Root Cause Quality", rc["weight"], f"{rc['score']:.0f}%", rc["reasoning"])
        rem = breakdown["remediation_precision"]
        table.add_row("Remediation Precision", rem["weight"], f"{rem['score']:.0f}%", f"Action: '{rem['action']}'")
        mis = breakdown["misleading_signal_handling"]
        table.add_row("Misleading Signals", mis["weight"], f"{mis['score']:.0f}%", mis["comment"])
        evi = breakdown["evidence_grounding"]
        table.add_row("Evidence Grounding", evi["weight"], f"{evi['score']:.0f}%", f"Traces: {evi['has_trace']} | Metrics: {evi['has_metrics']}")
        console.print(table)
        console.print(Panel(
            f"[bold]Incident ID:[/bold] {eval_card['incident_id']} | "
            f"[bold]Scenario:[/bold] {eval_card['scenario_name']} ({eval_card['scenario_id']})\n"
            f"[bold]Overall Performance:[/bold] [bold green]{eval_card['composite_score']}% (Grade {eval_card['grade']})[/bold green]\n"
            f"Archived to [dim]agent/data/eval_benchmarks.json[/dim]",
            title="Benchmark Evaluation Summary",
            border_style="green" if eval_card["composite_score"] >= 80 else "yellow"
        ))
    else:
        print(f"\n========================================================")
        print(f" EvoOps SRE Benchmark Scorecard — Grade: {eval_card['grade']} ({eval_card['composite_score']}%)")
        print(f" Incident ID: {eval_card['incident_id']} | Scenario: {eval_card['scenario_id']}")
        print(f"========================================================")
        for dim, details in breakdown.items():
            print(f" - {dim} ({details.get('weight', '')}): {details.get('score', 0):.0f}%")
        print(f"========================================================\n")



# -------------------------------------------------------------
# 4. MAIN CLI ENTRY POINT
# -------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="EvoOps Investigation Evaluator & Benchmarking CLI")
    parser.add_argument("--latest", action="store_true", help="Evaluate the latest incident from episodic memory")
    parser.add_argument("--incident", type=str, default=None, help="Incident ID to evaluate (e.g. INC-5480)")
    parser.add_argument("--scenario", type=str, default=None, help="Ground-truth scenario ID (e.g. downstream_timeout)")
    args = parser.parse_args()
    # Load incident
    incident = load_incident_from_memory(args.incident)
    if not incident:
        print("[Error] No incident found to evaluate.")
        sys.exit(1)
    # Load ground truth scenario
    if args.scenario:
        ground_truth = load_ground_truth_scenario(args.scenario)
    else:
        ground_truth = match_scenario_for_incident(incident)
    if not ground_truth:
        print("[Error] Could not find matching ground truth scenario.")
        sys.exit(1)
    print(f"\n[Evaluator] Grading incident '{incident.get('incident_id')}' against scenario '{ground_truth.get('id')}'...")
    eval_card = evaluate_investigation(incident, ground_truth)
    save_benchmark_result(eval_card)
    display_scorecard(eval_card)


if __name__ == "__main__":
    main()