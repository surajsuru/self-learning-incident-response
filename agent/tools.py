"""
EvoOps SRE Telemetry & Remediation Tools for LangChain AI Agent.
"""

import os
import json
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://localhost:8000")
CATALOG_PATH = Path(__file__).parent.parent / "scenarios" / "catalog.json"

SERVICES = {
    "api-gateway": 8000,
    "order-service": 8001,
    "inventory-service": 8002,
    "payment-service": 8003,
    "notification-service": 8004,
}


@tool
def check_cluster_health() -> str:
    """
    Checks the HTTP health and reachability of all 5 microservices in the cluster:
    api-gateway, order-service, inventory-service, payment-service, and notification-service.
    Returns status and HTTP response code for each.
    """
    results = {}
    with httpx.Client(timeout=3.0) as client:
        for svc_name, port in SERVICES.items():
            url = f"http://localhost:{port}/health"
            try:
                resp = client.get(url)
                results[svc_name] = {
                    "status": "healthy" if resp.status_code == 200 else f"unhealthy ({resp.status_code})",
                    "details": resp.json() if resp.headers.get("content-type") == "application/json" else resp.text[:100]
                }
            except Exception as e:
                results[svc_name] = {"status": "unreachable", "error": str(e)}
    return json.dumps(results, indent=2)


@tool
def query_prometheus(query: str) -> str:
    """
    Executes a PromQL (Prometheus Query Language) metric query against Prometheus.
    Examples of useful queries:
    - 'rate(http_requests_total[1m])' (request rates by endpoint/status)
    - 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le, service))' (P95 latency by service)
    - 'sum(rate(http_requests_total{status=~"5.."}[1m])) by (service)' (5xx error rates)
    """
    url = f"{PROMETHEUS_URL}/api/v1/query"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params={"query": query})
            data = resp.json()
            if data.get("status") != "success":
                return f"Prometheus Error: {data.get('error', 'unknown')}"
            
            results = data.get("data", {}).get("result", [])
            if not results:
                return "Query succeeded but returned no metrics (empty result)."

            formatted = []
            for item in results[:10]:  # Limit to 10 rows to preserve context
                metric = item.get("metric", {})
                val = item.get("value", [None, None])[1]
                formatted.append({"metric": metric, "value": val})
            return json.dumps(formatted, indent=2)
    except Exception as e:
        return f"Failed to query Prometheus: {e}"


@tool
def get_jaeger_traces(service: str, limit: int = 5) -> str:
    """
    Retrieves recent distributed traces for a specific service from Jaeger.
    Useful for seeing latency breakdowns across spans and identifying which downstream dependency is stalling.
    Valid service names: 'api-gateway', 'order-service', 'inventory-service', 'payment-service', 'notification-service'.
    """
    url = f"{JAEGER_URL}/api/traces"
    params = {"service": service, "limit": limit}
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                return f"Jaeger returned HTTP {resp.status_code}: {resp.text[:200]}"
            
            data = resp.json().get("data", [])
            if not data:
                return f"No traces found for service '{service}' in Jaeger."

            summary = []
            for trace in data[:limit]:
                trace_id = trace.get("traceID")
                spans = trace.get("spans", [])
                processes = trace.get("processes", {})

                span_details = []
                for s in spans:
                    p_id = s.get("processID")
                    svc_name = processes.get(p_id, {}).get("serviceName", "unknown")
                    duration_ms = round(s.get("duration", 0) / 1000.0, 2)
                    has_error = any(tag.get("key") == "error" and tag.get("value") is True for tag in s.get("tags", []))
                    span_details.append({
                        "service": svc_name,
                        "operation": s.get("operationName"),
                        "duration_ms": duration_ms,
                        "error": has_error
                    })

                total_duration = max((s["duration_ms"] for s in span_details), default=0.0)
                summary.append({
                    "trace_id": trace_id,
                    "total_duration_ms": total_duration,
                    "spans": span_details
                })
            return json.dumps(summary, indent=2)
    except Exception as e:
        return f"Failed to fetch traces from Jaeger: {e}"


@tool
def inspect_chaos_status() -> str:
    """
    Checks the fault injection / chaos status of all services in the cluster.
    Returns whether latency or error injection is currently active on any service.
    """
    statuses = {}
    with httpx.Client(timeout=3.0) as client:
        for svc_name, port in SERVICES.items():
            try:
                resp = client.get(f"http://localhost:{port}/chaos/status")
                if resp.status_code == 200:
                    statuses[svc_name] = resp.json()
                else:
                    statuses[svc_name] = {"error": f"HTTP {resp.status_code}"}
            except Exception as e:
                statuses[svc_name] = {"error": str(e)}
    return json.dumps(statuses, indent=2)


@tool
def search_incident_catalog(keyword: str) -> str:
    """
    Searches the EvoOps Ground Truth Scenario Catalog for known incident patterns, symptoms, and runbook remediations.
    Use this to cross-reference observed symptoms with cataloged incident scenarios.
    """
    if not CATALOG_PATH.exists():
        return "Catalog file scenarios/catalog.json not found."
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        
        matches = []
        kw = keyword.lower()
        for sc in catalog.get("scenarios", []):
            sc_str = json.dumps(sc).lower()
            if kw in sc_str:
                matches.append({
                    "id": sc["id"],
                    "name": sc["name"],
                    "target_service": sc["target_service"],
                    "expected_root_cause": sc["root_cause"],
                    "recommended_remediation": sc["recommended_remediation"],
                    "misleading_signals": sc.get("misleading_signals", "")
                })
        return json.dumps(matches if matches else "No matching scenarios found in catalog.", indent=2)
    except Exception as e:
        return f"Error reading catalog: {e}"


@tool
def execute_remediation(action: str, target_service: str) -> str:
    """
    Executes a remediation action on a degraded or faulty service.
    Supported actions:
    - 'reset_chaos': Clears injected latency and errors on target_service (e.g. 'payment-service', 'all').
    """
    if action == "reset_chaos":
        targets = SERVICES.keys() if target_service == "all" else [target_service]
        results = {}
        with httpx.Client(timeout=4.0) as client:
            for svc in targets:
                if svc not in SERVICES:
                    results[svc] = "Unknown service"
                    continue
                port = SERVICES[svc]
                try:
                    resp = client.post(f"http://localhost:{port}/chaos/reset", json={})
                    results[svc] = "Reset Success" if resp.status_code == 200 else f"Reset Failed ({resp.status_code})"
                except Exception as e:
                    results[svc] = f"Error: {e}"
        return json.dumps({"action": "reset_chaos", "results": results}, indent=2)

    return f"Unsupported remediation action '{action}'. Supported actions: 'reset_chaos'."
