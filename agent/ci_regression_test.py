"""
EvoOps CI/CD Benchmark Regression Gate (Phase 19).
Automated quality gate for GitHub Actions CI/CD pipelines.
Runs empirical incident benchmarks against ground truth, enforces Grade A (>= 90%),
and exits with code 0 (Pass) or code 1 (Fail).
"""


import sys
import os
import json
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

from agent.benchmark import run_comparison
from agent.evaluator import load_ground_truth_scenario

load_dotenv(Path(__file__).parent / ".env")


def setup_incident_environment(scenario: dict):
    """Automatically prepares the cluster with the scenario's failure mode and traces."""
    port = scenario.get("port")
    injection = scenario.get("injection")
    if not port or not injection:
        return
    print(f"[*] CI Setup: Injecting fault on port {port} ({scenario.get('name')})...")
    req = urllib.request.Request(
        f"http://localhost:{port}/chaos/inject",
        data=json.dumps(injection).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"    [Warning] Could not reach chaos endpoint: {e}")
    # Generate 3 realistic requests to produce waterfall spans in Jaeger
    print("[*] CI Setup: Generating sample traffic to seed telemetry traces...")
    for _ in range(3):
        try:
            order_data = json.dumps({"user_id": "ci_user", "product_id": "prod-1", "quantity": 1, "amount": 49.99}).encode("utf-8")
            treq = urllib.request.Request("http://localhost:8000/orders", data=order_data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(treq, timeout=6)
        except Exception:
            pass  # Expected during fault injection
    time.sleep(1)


def teardown_incident_environment(scenario: dict):
    """Automatically restores cluster back to healthy state after test completes."""
    port = scenario.get("port")
    if not port:
        return
    print(f"\n[*] CI Teardown: Resetting chaos faults on port {port}...")
    try:
        req = urllib.request.Request(
            f"http://localhost:{port}/chaos/reset",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        print("[*] CI Teardown: Cluster restored to normal healthy operation.")
    except Exception as e:
        print(f"    [Warning] Chaos reset failed: {e}")



def run_regression_gate(scenario_id: str = "downstream_timeout", min_score: float = 90.0) -> bool:
    """
    Executes the comparative benchmark with automated setup and teardown.
    Returns True if passed, False if regressed.
    """
    scenario = load_ground_truth_scenario(scenario_id)
    if not scenario:
        print(f"[Error] Scenario '{scenario_id}' not found in catalog.json")
        return False
    print("\n" + "=" * 70)
    print("  EvoOps CI/CD Automated Benchmark Regression Gate")
    print(f"  Target Scenario : {scenario.get('name')} ({scenario_id})")
    print(f"  Required Gate   : Grade A (Score >= {min_score}%)")
    print("=" * 70 + "\n")
    # 1. SETUP: Prepare live incident telemetry
    setup_incident_environment(scenario)
    try:
        # 2. RUN: Execute benchmark
        comparison = run_comparison(scenario_id=scenario_id)
        after = comparison.get("after_learning", {})
        before = comparison.get("before_learning", {})
        after_score = after.get("composite_score", 0.0)
        after_grade = after.get("grade", "F")
        before_score = before.get("composite_score", 0.0)
        improvement = comparison.get("score_improvement", 0.0)
        print("\n" + "-" * 70)
        print("  CI/CD Quality Gate Evaluation Summary")
        print("-" * 70)
        print(f"  • Baseline Score (Before Learning) : {before_score:.1f}%")
        print(f"  • Agent Score (After Learning)    : {after_score:.1f}% ({after_grade})")
        print(f"  • Measured Net Improvement        : +{improvement:.1f}%")
        print(f"  • Quality Gate Threshold Required : >= {min_score:.1f}%\n")
        if after_score >= min_score:
            pass_banner = f"""[bold green]✅ QUALITY GATE PASSED: GRADE {after_grade} ({after_score:.1f}% >= {min_score:.1f}%)[/bold green]
                The agent diagnosed the incident correctly with full evidence grounding.
                No intelligence regression detected. Safe to merge to production."""
            if USE_RICH:
                console.print(Panel(pass_banner, border_style="green", title="🛡️ CI Quality Gate"))
            else:
                print(f"SUCCESS: Grade {after_grade} ({after_score:.1f}%). Safe to merge!")
            return True
        else:
            fail_banner = f"""[bold red]❌ QUALITY GATE FAILED: REGRESSION DETECTED[/bold red]
            Observed Score: {after_score:.1f}% ({after_grade}) < Required Threshold: {min_score:.1f}%
            The agent failed to meet production accuracy standards.
            Pull Request merge is BLOCKED to prevent production outages."""
            if USE_RICH:
                console.print(Panel(fail_banner, border_style="red", title="🚨 CI Quality Gate"))
            else:
                print(f"FAILURE: Score {after_score:.1f}% < {min_score:.1f}%. Merge blocked!")
            return False
    finally:
        # 3. TEARDOWN: Always reset the cluster even if test fails
        teardown_incident_environment(scenario)

    


def main():
    parser = argparse.ArgumentParser(description="EvoOps CI/CD Benchmark Regression Gate")
    parser.add_argument(
        "--scenario",
        default="downstream_timeout",
        help="Scenario ID from catalog.json to evaluate against",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=90.0,
        help="Minimum required composite score to pass (default: 90.0)",
    )
    args = parser.parse_args()
    passed = run_regression_gate(scenario_id=args.scenario, min_score=args.min_score)
    if passed:
        sys.exit(0)
    else:
        sys.exit(1)



if __name__ == "__main__":
    main()
