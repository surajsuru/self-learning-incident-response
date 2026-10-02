"""
EvoOps Domain-Specific SRE Agents:
1. Trace Specialist  - Focuses on Jaeger distributed traces & span waterfalls.
2. Metrics Specialist - Focuses on Prometheus PromQL & container health.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from agent.tools import (
    get_jaeger_traces,
    query_prometheus,
    check_cluster_health,
    inspect_chaos_status,
)

# Load environment
load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", None)

llm_kwargs = {"model": OPENAI_MODEL_NAME, "temperature": 0.0, "api_key": OPENAI_API_KEY}
if OPENAI_API_BASE:
    llm_kwargs["base_url"] = OPENAI_API_BASE

llm = ChatOpenAI(**llm_kwargs)


# -------------------------------------------------------------
# 1. TRACE SPECIALIST AGENT
# -------------------------------------------------------------
TRACE_SPECIALIST_PROMPT = """You are the Senior Distributed Tracing Specialist for EvoCommerce.
Your ONLY responsibility is to analyze distributed traces in Jaeger to find where latency or errors are originating.

Guidelines:
1. Call get_jaeger_traces for relevant services (e.g. 'order-service', 'api-gateway').
2. Follow parent and child spans. Measure which microservice hop took the longest.
3. Identify if upstream services are healthy and merely waiting on a slow downstream dependency.
4. Output a concise 3-4 bullet report summarizing:
   - Root service vs. bottleneck service
   - Specific span duration (e.g., 'POST /payments/process took 3500ms')
   - Your conclusion from trace analysis.
"""

def run_trace_specialist(alert: str) -> str:
    """Runs the Trace Specialist to analyze Jaeger traces."""
    tools = [get_jaeger_traces]
    agent = llm.bind_tools(tools)
    
    messages = [
        SystemMessage(content=TRACE_SPECIALIST_PROMPT),
        HumanMessage(content=f"Investigate trace bottlenecks for this alert: '{alert}'")
    ]
    
    # 2-step ReAct execution
    for _ in range(3):
        res = agent.invoke(messages)
        messages.append(res)
        if not res.tool_calls:
            return res.content
        for tc in res.tool_calls:
            output = get_jaeger_traces.invoke(tc["args"])
            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(tool_call_id=tc["id"], content=str(output), name=tc["name"]))
    
    return messages[-1].content if messages else "Trace analysis completed."


# -------------------------------------------------------------
# 2. METRICS & HEALTH SPECIALIST AGENT
# -------------------------------------------------------------
METRICS_SPECIALIST_PROMPT = """You are the Senior Metrics & Infrastructure Specialist for EvoCommerce.
Your ONLY responsibility is to analyze Prometheus metrics, container health, and active cluster faults.

Guidelines:
1. Use check_cluster_health to see if all containers are reachable and responding HTTP 200.
2. Use query_prometheus to inspect error rates (5xx) or request rate spikes.
3. Use inspect_chaos_status to see if any service has active artificial faults.
4. Output a concise 3-4 bullet report summarizing:
   - Health status of each container
   - Prometheus 5xx or latency metrics observed
   - Any active chaos or fault injection found.
"""

def run_metrics_specialist(alert: str) -> str:
    """Runs the Metrics Specialist to analyze Prometheus and cluster health."""
    tools = [check_cluster_health, query_prometheus, inspect_chaos_status]
    agent = llm.bind_tools(tools)
    
    messages = [
        SystemMessage(content=METRICS_SPECIALIST_PROMPT),
        HumanMessage(content=f"Investigate metrics and health for this alert: '{alert}'")
    ]
    
    # 2-step ReAct execution
    tool_map = {t.name: t for t in tools}
    for _ in range(4):
        res = agent.invoke(messages)
        messages.append(res)
        if not res.tool_calls:
            return res.content
        for tc in res.tool_calls:
            tool_fn = tool_map.get(tc["name"])
            output = tool_fn.invoke(tc["args"]) if tool_fn else "Tool not found"
            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(tool_call_id=tc["id"], content=str(output), name=tc["name"]))
    
    return messages[-1].content if messages else "Metrics analysis completed."
