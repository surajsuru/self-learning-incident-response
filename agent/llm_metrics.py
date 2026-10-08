"""
EvoOps LLMOps Telemetry, Prompt Tracing & Cost Governance Engine (Phase 18).
Captures prompt histories, token consumption, model latencies, and USD costs.
Persists operational telemetry to agent/data/llm_telemetry.json.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

DATA_DIR = Path(__file__).parent / "data"
TELEMETRY_LOG = DATA_DIR / "llm_telemetry.json"


# Official Pricing per 1,000,000 Tokens (USD)
MODEL_PRICING = {
    "gpt-4o-mini": {
        "prompt": 0.150,       # $0.15 per 1M input tokens
        "completion": 0.600,   # $0.60 per 1M output tokens
    },
    "gpt-4o": {
        "prompt": 2.500,       # $2.50 per 1M input tokens
        "completion": 10.000,  # $10.00 per 1M output tokens
    },
    "claude-3-5-sonnet": {
        "prompt": 3.000,
        "completion": 15.000,
    },
    "default": {
        "prompt": 0.500,
        "completion": 1.500,
    }
}



class LLMTelemetryTracker:
    """Manages telemetry accounting, prompt traces, and cost governance for an incident investigation."""
    def __init__(self, incident_id: str, model_name: str = "gpt-4o-mini"):
        self.incident_id = incident_id
        self.model_name = model_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.successful_requests = 0
        self.total_cost_usd = 0.0
        
        # Chronological trace of every prompt, tool call, and model response
        self.request_trace: List[Dict[str, Any]] = []

    def record_prompt_request(self, messages_preview: str):
        """Records an outgoing prompt before it hits the model API."""
        step_number = len(self.request_trace) + 1
        self.request_trace.append({
            "step": step_number,
            "type": "llm_request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_preview": messages_preview[:300] + ("..." if len(messages_preview) > 300 else "")
        })

    def record_usage(self, prompt_tokens: int, completion_tokens: int, requests: int = 1, response_preview: str = ""):
        """Updates token accounting and logs the model response."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.successful_requests += requests
        self._calculate_cost()
        step_number = len(self.request_trace) + 1
        self.request_trace.append({
            "step": step_number,
            "type": "llm_response",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens
            },
            "response_preview": response_preview[:250] + ("..." if len(response_preview) > 250 else "")
        })

    
    def record_tool_call(self, tool_name: str, arguments: Any):
        """Records an agent tool decision."""
        step_number = len(self.request_trace) + 1
        self.request_trace.append({
            "step": step_number,
            "type": "tool_invocation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "arguments": arguments
        })
    

    def _calculate_cost(self):
        pricing = MODEL_PRICING.get(self.model_name, MODEL_PRICING["default"])
        cost_prompt = (self.prompt_tokens / 1_000_000) * pricing["prompt"]
        cost_completion = (self.completion_tokens / 1_000_000) * pricing["completion"]
        self.total_cost_usd = round(cost_prompt + cost_completion, 6)


    def finalize(self) -> Dict[str, Any]:
        """Calculates latency and saves telemetry to agent/data/llm_telemetry.json."""
        self.end_time = time.time()
        duration_sec = round(self.end_time - self.start_time, 2)
        throughput = round(self.completion_tokens / duration_sec, 1) if duration_sec > 0 else 0.0
        record = {
            "run_id": f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "incident_id": self.incident_id,
            "model_name": self.model_name,
            "metrics": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
                "llm_calls": self.successful_requests,
                "duration_seconds": duration_sec,
                "throughput_tokens_per_sec": throughput,
                "total_cost_usd": self.total_cost_usd
            },
            "request_trace": self.request_trace
        }
        self._save_to_log(record)
        return record

    
    def _save_to_log(self, record: Dict[str, Any]):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        history = []
        if TELEMETRY_LOG.exists():
            try:
                with open(TELEMETRY_LOG, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        history.append(record)
        with open(TELEMETRY_LOG, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)


    def print_summary(self):
        """Displays a clean LLMOps FinOps Scorecard in the terminal."""
        duration_sec = round((self.end_time or time.time()) - self.start_time, 2)
        throughput = round(self.completion_tokens / duration_sec, 1) if duration_sec > 0 else 0.0
        if USE_RICH:
            table = Table(title="📊 EvoOps LLMOps Operational Telemetry & Cost Scorecard", border_style="cyan")
            table.add_column("Metric", style="bold white")
            table.add_column("Observed Value", style="bold green")
            table.add_row("Target Incident ID", self.incident_id)
            table.add_row("LLM Model Name", self.model_name)
            table.add_row("Total LLM Calls", str(self.successful_requests))
            table.add_row("Prompt Tokens (Input)", f"{self.prompt_tokens:,}")
            table.add_row("Completion Tokens (Output)", f"{self.completion_tokens:,}")
            table.add_row("Total Tokens Consumed", f"{self.total_tokens:,}")
            table.add_row("Total Investigation Duration", f"{duration_sec}s")
            table.add_row("Generation Throughput", f"{throughput} tokens/sec")
            table.add_row("Estimated Run Cost (USD)", f"${self.total_cost_usd:.6f}")
            console.print(table)
        else:
            print("\n" + "=" * 65)
            print("  EvoOps LLMOps Operational Telemetry & Cost Scorecard")
            print("=" * 65)
            print(f"Incident ID        : {self.incident_id}")
            print(f"Model              : {self.model_name}")
            print(f"LLM Calls          : {self.successful_requests}")
            print(f"Prompt Tokens      : {self.prompt_tokens:,}")
            print(f"Completion Tokens  : {self.completion_tokens:,}")
            print(f"Total Tokens       : {self.total_tokens:,}")
            print(f"Duration           : {duration_sec}s")
            print(f"Cost (USD)         : ${self.total_cost_usd:.6f}")
            print("=" * 65 + "\n")



class LLMOpsCallbackHandler(BaseCallbackHandler):
    """
    LangChain Callback Handler that intercepts lifecycle events:
    - on_chat_model_start: Captures prompt payloads
    - on_llm_end: Captures token counts directly from the API response
    - on_tool_start: Captures tool executions
    """

    def __init__(self, tracker: LLMTelemetryTracker):
        super().__init__()
        self.tracker = tracker

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs):
        """Triggered right before an HTTP request is dispatched to the LLM."""
        if messages and len(messages) > 0:
            prompt_summary = " | ".join([f"{m.type}: {str(m.content)[:80]}" for m in messages[0][-3:]])
            self.tracker.record_prompt_request(prompt_summary)


    def on_llm_end(self, response: LLMResult, **kwargs):
        """Triggered right after the model responds with tokens and metadata."""
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage", {})
        
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        # Extract text preview from the first generation
        resp_text = ""
        if response.generations and len(response.generations) > 0:
            gen = response.generations[0][0]
            resp_text = str(getattr(gen, "text", "") or getattr(gen.message, "content", ""))
        # Fallback estimation if model provider did not return token_usage dict
        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = 500  # Conservative estimate
            completion_tokens = max(len(resp_text) // 4, 20)
        self.tracker.record_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            requests=1,
            response_preview=resp_text
        )

    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs):
        """Triggered when an agent decides to invoke a tool."""
        tool_name = serialized.get("name", "unknown_tool")
        self.tracker.record_tool_call(tool_name, input_str)



if __name__ == "__main__":
    print("Running LLMOps Telemetry Engine Self-Test...")
    tracker = LLMTelemetryTracker(incident_id="TEST-INC-1234", model_name="gpt-4o-mini")
    tracker.record_prompt_request("System: You are an SRE... Human: Alert: High latency on payment service")
    tracker.record_usage(prompt_tokens=2100, completion_tokens=350, requests=2, response_preview="Identified timeout at payment-service")
    tracker.finalize()
    tracker.print_summary()
    print("Verification complete. Check agent/data/llm_telemetry.json for the saved trace!")
