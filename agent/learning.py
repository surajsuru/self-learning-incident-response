"""
EvoOps Self-Learning Engine (Phase 14).
Reflects on evaluated incident investigations and synthesizes reusable
SRE operational strategies & anti-pattern rules.
Usage:
    python agent/learning.py --latest
    python agent/learning.py --list
"""


import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
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

load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", None)

llm_kwargs = {"model": OPENAI_MODEL_NAME, "temperature": 0.0, "api_key": OPENAI_API_KEY}
if OPENAI_API_BASE:
    llm_kwargs["base_url"] = OPENAI_API_BASE
llm = ChatOpenAI(**llm_kwargs)


DATA_DIR = Path(__file__).parent / "data"
BENCHMARK_FILE = DATA_DIR / "eval_benchmarks.json"
STRATEGY_FILE = DATA_DIR / "learned_strategies.json"
EPISODIC_MEMORY_FILE = DATA_DIR / "episodic_memory.json"


# Seed institutional strategies
DEFAULT_STRATEGIES = [
    {
        "strategy_id": "STRAT-INIT-01",
        "category": "database_saturation",
        "proven_strategy": "When order-service query latency spikes, verify PostgreSQL connection pool locks before assuming general container CPU saturation.",
        "anti_pattern": "Do not restart application containers without checking if unindexed database transactions are blocking threads.",
        "timestamp": "2026-08-15T00:00:00Z"
    },
    {
        "strategy_id": "STRAT-INIT-02",
        "category": "cache_degradation",
        "proven_strategy": "When stock verification returns 502, check Redis cache read timeouts before suspecting inventory application code errors.",
        "anti_pattern": "Do not treat cache fallback database overload as a database schema bug.",
        "timestamp": "2026-09-02T00:00:00Z"
    }
]


# -------------------------------------------------------------
# 1. STORAGE INITIALIZATION & ACCESS
# -------------------------------------------------------------

def init_strategy_store():
    """Ensures data directory and learned_strategies.json exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STRATEGY_FILE.exists():
        with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STRATEGIES, f, indent=2)


def load_strategies() -> List[Dict[str, Any]]:
    """Loads all learned strategies from storage."""
    init_strategy_store()
    try:
        with open(STRATEGY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_learned_strategy(strategy: Dict[str, Any]) -> bool:
    """Appends a new learned strategy to storage, preventing duplicates."""
    init_strategy_store()
    strategies = load_strategies()
    # Check for duplicate advice
    for s in strategies:
        if s.get("proven_strategy") == strategy.get("proven_strategy"):
            return False
    strategies.append(strategy)
    with open(STRATEGY_FILE, "w", encoding="utf-8") as f:
        json.dump(strategies, f, indent=2)
    return True



# -------------------------------------------------------------
# 2. REFLECTION & LEARNING ENGINE
# -------------------------------------------------------------

def extract_learning_from_eval(eval_card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Uses LLM reflection to analyze an Evaluator scorecard and extract
    a reusable SRE strategy rule and anti-pattern.
    """
    incident_id = eval_card.get("incident_id")
    scenario_name = eval_card.get("scenario_name")
    breakdown = eval_card.get("breakdown", {})
    
    svc_acc = breakdown.get("service_accuracy", {})
    rc_acc = breakdown.get("root_cause_accuracy", {})
    misleading = breakdown.get("misleading_signal_handling", {})
    prompt = f"""You are an SRE Principal Architect analyzing a post-incident evaluation.
        Incident ID: {incident_id}
        Scenario: {scenario_name}
        Composite Score: {eval_card.get('composite_score')}% (Grade {eval_card.get('grade')})
        Evaluation Details:
        - Target Service Diagnosed: {svc_acc.get('diagnosed')} (Expected: {svc_acc.get('expected')})
        - Root Cause Critique: {rc_acc.get('reasoning')}
        - Misleading Signals Comment: {misleading.get('comment')}
        Instructions:
        Extract actionable, permanent SRE operational wisdom from this case.
        1. 'proven_strategy': A clear 1-2 sentence rule on how to diagnose this type of failure correctly next time.
        2. 'anti_pattern': A clear 1-2 sentence trap/mistake to avoid (e.g., confusing caller symptoms with root causes).
        3. 'category': e.g., 'latency_propagation', 'error_spike', 'database', or 'service_communication'.
        Return ONLY valid JSON in this format:
        {{
        "category": "latency_propagation",
        "proven_strategy": "Concrete winning rule here",
        "anti_pattern": "Specific trap to avoid here"
        }}"""
    try:
        res = llm.invoke([
            SystemMessage(content="You are an expert SRE learning engine. Return only JSON."),
            HumanMessage(content=prompt)
        ])
        content = res.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        data = json.loads(content)
        new_strategy = {
            "strategy_id": f"STRAT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "incident_id": incident_id,
            "scenario": scenario_name,
            "category": data.get("category", "general_sre"),
            "proven_strategy": data.get("proven_strategy"),
            "anti_pattern": data.get("anti_pattern"),
            "grade_achieved": eval_card.get("grade"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return new_strategy
    except Exception as e:
        print(f"[Error] Failed to extract learning: {e}")
        return None


# -------------------------------------------------------------
# 3. RUNTIME RETRIEVAL FOR SRE WORKFLOW
# -------------------------------------------------------------

def retrieve_learned_strategies(alert_text: str, top_k: int = 2) -> List[Dict[str, Any]]:
    """
    Retrieves the most relevant learned strategies & anti-patterns
    based on the incoming incident alert keywords.
    """
    strategies = load_strategies()
    if not strategies:
        return []
    tokens = set(alert_text.lower().replace("alert:", "").replace(">", "").split())
    scored = []
    for s in strategies:
        text = f"{s.get('category', '')} {s.get('proven_strategy', '')} {s.get('anti_pattern', '')}".lower()
        score = sum(1 for token in tokens if token in text)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]



# -------------------------------------------------------------
# 4. CLI & DISPLAY
# -------------------------------------------------------------

def display_strategies(strategies: List[Dict[str, Any]]):
    """Displays learned strategies in a clean table."""
    if USE_RICH:
        table = Table(title="EvoOps Learned SRE Strategy Playbook (Procedural Memory)")
        table.add_column("Strategy ID", style="cyan", no_wrap=True)
        table.add_column("Category", style="magenta")
        table.add_column("Proven Strategy (What to Do)", style="green")
        table.add_column("Anti-Pattern (Trap to Avoid)", style="red")
        for s in strategies:
            table.add_row(
                s.get("strategy_id", "N/A"),
                s.get("category", "general"),
                s.get("proven_strategy", ""),
                s.get("anti_pattern", "")
            )
        console.print(table)
    else:
        print("\n=== EvoOps Learned SRE Strategy Playbook ===")
        for s in strategies:
            print(f"[{s.get('strategy_id')}] Category: {s.get('category')}")
            print(f"  + Strategy    : {s.get('proven_strategy')}")
            print(f"  - Anti-Pattern: {s.get('anti_pattern')}\n")


def main():
    parser = argparse.ArgumentParser(description="EvoOps Self-Learning Strategy Engine")
    parser.add_argument("--latest", action="store_true", help="Learn from the latest evaluation benchmark")
    parser.add_argument("--list", action="store_true", help="List all learned strategies in procedural memory")
    args = parser.parse_args()
    if args.list:
        display_strategies(load_strategies())
        return
    if args.latest:
        if not BENCHMARK_FILE.exists():
            print(f"[Error] No benchmark file found at {BENCHMARK_FILE}")
            sys.exit(1)
        with open(BENCHMARK_FILE, "r", encoding="utf-8") as f:
            benchmarks = json.load(f)
        if not benchmarks:
            print("[Error] No benchmarks found to learn from.")
            sys.exit(1)
        latest_eval = benchmarks[-1]
        print(f"\n[*] Reflecting on latest evaluation: {latest_eval.get('incident_id')} ({latest_eval.get('composite_score')}%, Grade {latest_eval.get('grade')})...")
        strategy = extract_learning_from_eval(latest_eval)
        if strategy:
            saved = save_learned_strategy(strategy)
            if saved:
                print(f"[Success] Extracted new SRE Strategy '{strategy['strategy_id']}' and saved to agent/data/learned_strategies.json!")
            else:
                print(f"[Info] Strategy already exists in playbook (no duplicate added).")
            display_strategies([strategy])


if __name__ == "__main__":
    main()
