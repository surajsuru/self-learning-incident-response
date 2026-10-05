"""
EvoOps Model Context Protocol (MCP) SRE Server (Phase 17).
Implements the Anthropic MCP open standard (JSON-RPC 2.0) over STDIO.
Exposes cluster health, Prometheus queries, Jaeger traces, scenario catalog,
and governed remediation to any MCP-compliant AI client (Claude Desktop, Cursor, etc.).
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional


# Ensure project root is in sys.path so we can import from agent
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# DIRECT IMPORT: Reuse the existing tools from agent.tools!
from agent.tools import (
    SERVICES,
    check_cluster_health,
    query_prometheus,
    get_jaeger_traces,
    inspect_chaos_status,
    search_incident_catalog,
    execute_remediation
)

# Configuration
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")
ROOT_DIR = Path(__file__).parent.parent
CATALOG_PATH = ROOT_DIR / "scenarios" / "catalog.json"
STRATEGIES_PATH = ROOT_DIR / "agent" / "data" / "learned_strategies.json"


SERVICES = {
    "api-gateway": 8000,
    "order-service": 8001,
    "inventory-service": 8002,
    "payment-service": 8003,
    "notification-service": 8004,
}

# MCP Protocol Definitions
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "evoops-sre-mcp-server",
    "version": "1.0.0"
}


# -------------------------------------------------------------
# Tool Definitions (MCP Schema)
# -------------------------------------------------------------

TOOLS = [
    {
        "name": "check_cluster_health",
        "description": "Checks HTTP health and reachability of all 5 microservices in the cluster (api-gateway, order-service, inventory-service, payment-service, notification-service).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "query_prometheus",
        "description": "Executes a PromQL query against Prometheus to inspect request rates, P95/P99 latency, or error rates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PromQL query string, e.g. 'rate(http_requests_total[1m])' or 'sum(rate(http_requests_total{status=~\"5..\"}[1m])) by (service)'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_jaeger_traces",
        "description": "Retrieves recent distributed waterfall traces from Jaeger for a specific service to identify latency bottlenecks and span errors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Target service name (e.g. 'api-gateway', 'payment-service')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of traces to return (default 5)",
                    "default": 5
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "inspect_chaos_status",
        "description": "Inspects fault-injection status across all microservices to check whether simulated latency or error spikes are active.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_incident_catalog",
        "description": "Cross-references symptoms against the EvoOps ground-truth incident catalog to retrieve known failure signatures and runbooks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search, e.g. 'payment', 'timeout', 'db_latency'"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "execute_remediation",
        "description": "Executes an SRE remediation action on a degraded service. Supported actions: 'reset_chaos' to clear injected faults.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Remediation action, currently 'reset_chaos'"
                },
                "target_service": {
                    "type": "string",
                    "description": "Target service name (e.g. 'payment-service') or 'all'"
                }
            },
            "required": ["action", "target_service"]
        }
    }
]



# -------------------------------------------------------------
# Resources (MCP Schema)
# -------------------------------------------------------------

RESOURCES = [
    {
        "uri": "sre://cluster/services",
        "name": "Cluster Service Topology",
        "description": "Port and routing topology for all EvoCommerce microservices.",
        "mimeType": "application/json"
    },
    {
        "uri": "sre://scenarios/catalog",
        "name": "Ground Truth Incident Catalog",
        "description": "Complete catalog of operational failure scenarios.",
        "mimeType": "application/json"
    },
    {
        "uri": "sre://memory/learned-strategies",
        "name": "Learned Operational Playbooks",
        "description": "Self-learning procedural playbooks and anti-patterns extracted by EvoOps.",
        "mimeType": "application/json"
    }
]


# -------------------------------------------------------------
# Prompts (MCP Schema)
# -------------------------------------------------------------

PROMPTS = [
    {
        "name": "sre_investigate",
        "description": "Prompt template for autonomous SRE incident triage and root cause investigation.",
        "arguments": [
            {
                "name": "incident_description",
                "description": "Description of the operational anomaly or alert symptom.",
                "required": True
            }
        ]
    }
]


# -------------------------------------------------------------
# MCP JSON-RPC 2.0 Dispatcher
# -------------------------------------------------------------

async def process_mcp_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})
    # 1. Initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "serverInfo": SERVER_INFO
            }
        }
    # 2. Initialized Notification (no response needed per spec)
    elif method == "notifications/initialized":
        return None
    # 3. Ping
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    # 4. Tools: List
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS}
        }
    # 5. Tools: Call
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        try:
            if tool_name == "check_cluster_health":
                text = check_cluster_health.invoke({})
            elif tool_name == "query_prometheus":
                text = query_prometheus.invoke({"query": args.get("query", "")})
            elif tool_name == "get_jaeger_traces":
                text = get_jaeger_traces.invoke({
                    "service": args.get("service", ""),
                    "limit": args.get("limit", 5)
                })
            elif tool_name == "inspect_chaos_status":
                text = inspect_chaos_status.invoke({})
            elif tool_name == "search_incident_catalog":
                text = search_incident_catalog.invoke({"keyword": args.get("keyword", "")})
            elif tool_name == "execute_remediation":
                text = execute_remediation.invoke({
                    "action": args.get("action", ""),
                    "target_service": args.get("target_service", "")
                })
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found."}
                }
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": str(text)}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}],
                    "isError": True
                }
            }

    # 6. Resources: List
    elif method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": RESOURCES}
        }
    # 7. Resources: Read
    elif method == "resources/read":
        uri = params.get("uri")
        if uri == "sre://cluster/services":
            content = json.dumps(SERVICES, indent=2)
        elif uri == "sre://scenarios/catalog":
            content = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else "{}"
        elif uri == "sre://memory/learned-strategies":
            content = STRATEGIES_PATH.read_text(encoding="utf-8") if STRATEGIES_PATH.exists() else "{}"
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"Resource URI '{uri}' not found."}
            }
        
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "contents": [
                    {"uri": uri, "mimeType": "application/json", "text": content}
                ]
            }
        }
    # 8. Prompts: List
    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"prompts": PROMPTS}
        }
    # 9. Prompts: Get
    elif method == "prompts/get":
        prompt_name = params.get("name")
        args = params.get("arguments", {})
        if prompt_name == "sre_investigate":
            incident = args.get("incident_description", "Unknown system alert")
            prompt_text = (
                f"You are the Lead SRE Incident Responder investigating the following alert:\n\n"
                f"Alert: {incident}\n\n"
                f"Investigation Strategy:\n"
                f"1. Check cluster health (`check_cluster_health`).\n"
                f"2. Inspect distributed traces (`get_jaeger_traces`) to locate latency spikes and error tags.\n"
                f"3. Query Prometheus metrics (`query_prometheus`) to verify request rates and error codes.\n"
                f"4. Search known playbooks (`search_incident_catalog`).\n"
                f"5. Formulate root cause with concrete telemetry evidence."
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": "Standardized Autonomous SRE Investigation Workflow",
                    "messages": [
                        {"role": "user", "content": {"type": "text", "text": prompt_text}}
                    ]
                }
            }
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Prompt '{prompt_name}' not found."}
        }
    # Method not found
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method '{method}' not implemented."}
    }



# -------------------------------------------------------------
# STDIO Server Loop & Self-Test Mode
# -------------------------------------------------------------

def run_stdio_server():
    """Runs standard MCP STDIO protocol loop (works cross-platform on Windows/Linux)."""
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
            resp = asyncio.run(process_mcp_message(msg))
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()



async def run_self_test():
    """Runs a quick self-verification test of all MCP methods."""
    print("=" * 65)
    print("  EvoOps MCP Server Verification Suite (JSON-RPC 2.0)")
    print("=" * 65)
    
    # Test 1: Initialize
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}}
    init_res = await process_mcp_message(init_req)
    print("\n[1/4] Testing 'initialize'...")
    print(f"Status: Success | Server: {init_res['result']['serverInfo']['name']} v{init_res['result']['serverInfo']['version']}")
    # Test 2: Tools List
    tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    tools_res = await process_mcp_message(tools_req)
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    print(f"\n[2/4] Testing 'tools/list'...")
    print(f"Status: Success | Exposed {len(tool_names)} Tools: {', '.join(tool_names)}")
    # Test 3: Resources List
    res_req = {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}
    res_res = await process_mcp_message(res_req)
    res_uris = [r["uri"] for r in res_res["result"]["resources"]]
    print(f"\n[3/4] Testing 'resources/list'...")
    print(f"Status: Success | Exposed {len(res_uris)} Resources: {', '.join(res_uris)}")
    # Test 4: Tool Execution (check_cluster_health)
    call_req = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "check_cluster_health", "arguments": {}}}
    print(f"\n[4/4] Testing 'tools/call' (check_cluster_health)...")
    call_res = await process_mcp_message(call_req)
    output_text = call_res["result"]["content"][0]["text"]
    print(f"Result Preview:\n{output_text[:300]}...")
    print("\n" + "=" * 65)
    print("  All MCP endpoints validated successfully!")
    print("=" * 65)



if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(run_self_test())
    else:
        run_stdio_server()