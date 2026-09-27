"""
EvoOps Autonomous Incident Investigation Agent
Usage:
    python agent/investigator.py "Alert: High latency observed on order creation endpoints"
    python agent/investigator.py --auto-remediate "Alert: Error spike on inventory service"
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path so 'agent.tools' is always found
sys.path.insert(0, str(Path(__file__).parent.parent))

# Rich terminal styling (with standard fallback)
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
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
    print("[Error] OPENAI_API_KEY is not configured in agent/.env. Please add your key first.")
    sys.exit(1)


SYSTEM_PROMPT = """You are EvoOps, a Senior Autonomous Site Reliability Engineer (SRE) and Incident Response Agent.
You are operating on the 'EvoCommerce' microservice platform composed of:
- api-gateway (port 8000)
- order-service (port 8001)
- inventory-service (port 8002)
- payment-service (port 8003)
- notification-service (port 8004)

Your mission:
When an incident alert is received, autonomously investigate using your available telemetry tools, isolate the TRUE root cause, execute or recommend remediation, and verify recovery.

Investigation Guidelines:
1. Evidence First: NEVER guess or assume. Always use your tools (check_cluster_health, get_jaeger_traces, query_prometheus, inspect_chaos_status) to gather empirical evidence.
2. Beware of Cascading & Misleading Symptoms:
   - For example: High latency at api-gateway or order-service is often caused by a downstream bottleneck in payment-service or inventory-service. Use get_jaeger_traces to inspect span durations and locate the exact stalling component.
3. Consult the Catalog: Use search_incident_catalog to cross-reference observed symptoms with known ground-truth scenarios.
4. Remediation:
   - If auto_remediation is requested, call execute_remediation to reset faults or recover degraded services.
   - Always verify that the system recovered after remediation by re-checking health or chaos status.
5. Final Incident Report:
   When you finish the investigation, provide a clean, professional SRE Postmortem report in Markdown format with:
   - ### Incident Summary
   - ### Evidence & Timeline (which tools were checked, key metrics/spans found)
   - ### Root Cause Analysis (RCA) (what broke and why, and what misleading signals were debunked)
   - ### Remediation Taken & Verification
   - ### Recommendations to Prevent Recurrence
"""


def log_step(title: str, content: str, style: str = "cyan"):
    if USE_RICH:
        console.print(Panel(content, title=f"[bold]{title}[/bold]", border_style=style))
    else:
        print(f"\n--- [{title}] ---\n{content}\n")


def run_investigation(incident_alert: str, auto_remediate: bool = False, max_steps: int = 10):
    print(f"\n{'='*75}")
    print(f"  EvoOps Autonomous Incident Response Agent")
    print(f"  Model: {OPENAI_MODEL_NAME} | Auto-Remediate: {auto_remediate}")
    print(f"{'='*75}\n")
    print(f"[Incident Alert Received]: {incident_alert}\n")

    # Available tools
    tools = [
        check_cluster_health,
        query_prometheus,
        get_jaeger_traces,
        inspect_chaos_status,
        search_incident_catalog,
        execute_remediation,
    ]
    tool_map = {t.name: t for t in tools}

    # Initialize LLM
    llm_kwargs = {
        "model": OPENAI_MODEL_NAME,
        "temperature": 0.0,
        "api_key": OPENAI_API_KEY,
    }
    if OPENAI_API_BASE:
        llm_kwargs["base_url"] = OPENAI_API_BASE

    llm = ChatOpenAI(**llm_kwargs)
    llm_with_tools = llm.bind_tools(tools)

    # Initial Message History
    prompt_with_instructions = incident_alert
    if auto_remediate:
        prompt_with_instructions += "\n[Notice]: You have authorization to execute remediation (e.g. execute_remediation) once root cause is diagnosed."
    else:
        prompt_with_instructions += "\n[Notice]: Auto-remediation is disabled. Recommend the remediation plan in your report without executing dangerous actions."

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_with_instructions),
    ]

    # ReAct Agent Loop
    step = 0
    while step < max_steps:
        step += 1
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # 1. If LLM provided text output or reasoning
        if response.content:
            log_step(f"Agent Thought (Step {step})", response.content, style="blue")

        # 2. If LLM did not call any tools, the investigation is complete!
        if not response.tool_calls:
            print("\n" + "="*75)
            print("  Investigation Complete — Final Incident Report")
            print("="*75 + "\n")
            if USE_RICH:
                console.print(Markdown(response.content))
            else:
                print(response.content)
            break

        # 3. Execute all requested tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            log_step(f"Tool Invocation: {tool_name}", f"Arguments: {tool_args}", style="yellow")

            if tool_name not in tool_map:
                tool_output = f"Error: Tool '{tool_name}' does not exist."
            else:
                try:
                    tool_output = tool_map[tool_name].invoke(tool_args)
                except Exception as exc:
                    tool_output = f"Tool execution failed with exception: {exc}"

            # Log tool observation (preview first 400 chars)
            preview = str(tool_output)[:400] + ("..." if len(str(tool_output)) > 400 else "")
            log_step(f"Tool Observation: {tool_name}", preview, style="green")

            # Feed tool observation back to message history
            messages.append(
                ToolMessage(
                    tool_call_id=tool_id,
                    content=str(tool_output),
                    name=tool_name,
                )
            )


def main():
    parser = argparse.ArgumentParser(description="EvoOps Autonomous Incident Investigator")
    parser.add_argument(
        "alert",
        nargs="?",
        default="Alert: Users report severe checkout delays on POST /orders (latency > 3s).",
        help="Incident description or alert string",
    )
    parser.add_argument(
        "--auto-remediate",
        action="store_true",
        help="Allow the agent to autonomously execute remediation",
    )
    args = parser.parse_args()

    run_investigation(args.alert, auto_remediate=args.auto_remediate)


if __name__ == "__main__":
    main()
