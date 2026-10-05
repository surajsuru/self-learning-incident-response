"""
EvoOps MCP Client Adapter for LangChain / LangGraph Agents.
Dynamically discovers and wraps tools from mcp/sre_server.py into
LangChain StructuredTools, ensuring all agent operations route through MCP.
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from langchain_core.tools import StructuredTool
from pydantic import create_model, Field

PYTHON_EXE = sys.executable
ROOT_DIR = Path(__file__).parent.parent
SERVER_SCRIPT = str(ROOT_DIR / "mcp" / "sre_server.py")


class MCPClientConnection:
    """Manages an active STDIO connection to the EvoOps MCP Server."""
    def __init__(self):
        self.proc = subprocess.Popen(
            [PYTHON_EXE, SERVER_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        self._handshake()


    def _handshake(self):
        self.send_rpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        })


    def send_rpc(self, msg: dict) -> dict:
        line = json.dumps(msg) + "\n"
        self.proc.stdin.write(line.encode("utf-8"))
        self.proc.stdin.flush()
        resp_line = self.proc.stdout.readline().decode("utf-8").strip()
        if not resp_line:
            raise RuntimeError("MCP Server returned an empty response.")
        return json.loads(resp_line)


    def close(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()


# Global client singleton
_MCP_CONN = None

def get_mcp_connection() -> MCPClientConnection:
    global _MCP_CONN
    if _MCP_CONN is None or _MCP_CONN.proc.poll() is not None:
        _MCP_CONN = MCPClientConnection()
    return _MCP_CONN


def call_mcp_tool(tool_name: str, **kwargs) -> str:
    """Invokes a tool on the MCP Server over JSON-RPC 2.0."""
    conn = get_mcp_connection()
    resp = conn.send_rpc({
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": kwargs
        }
    })
    result = resp.get("result", {})
    contents = result.get("content", [])
    if contents and isinstance(contents, list):
        return contents[0].get("text", "")
    if "error" in resp:
        return f"MCP Error: {resp['error'].get('message')}"
    return str(result)


def load_mcp_tools() -> List[StructuredTool]:
    """
    Discovers all tools exposed by mcp/sre_server.py via `tools/list`
    and wraps them as LangChain StructuredTools.
    """
    conn = get_mcp_connection()
    resp = conn.send_rpc({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    })
    raw_tools = resp.get("result", {}).get("tools", [])
    langchain_tools = []
    for t in raw_tools:
        name = t["name"]
        description = t["description"]
        properties = t.get("inputSchema", {}).get("properties", {})
        required = t.get("inputSchema", {}).get("required", [])
        # Build dynamic pydantic schema for the tool arguments
        fields = {}
        for prop_name, prop_meta in properties.items():
            prop_type = str if prop_meta.get("type") == "string" else int
            default_val = ... if prop_name in required else prop_meta.get("default", None)
            fields[prop_name] = (prop_type, Field(default=default_val, description=prop_meta.get("description", "")))
        args_schema = create_model(f"{name}_schema", **fields) if fields else None
        # Create wrapper closure
        def make_executor(t_name: str):
            def execute(**args):
                return call_mcp_tool(t_name, **args)
            return execute
        st = StructuredTool.from_function(
            func=make_executor(name),
            name=name,
            description=description,
            args_schema=args_schema
        )
        langchain_tools.append(st)
    return langchain_tools




if __name__ == "__main__":
    print("Testing dynamic MCP tool discovery...")
    tools = load_mcp_tools()
    print(f"Successfully loaded {len(tools)} tools from MCP Server:")
    for t in tools:
        print(f"  • {t.name}: {t.description[:60]}...")
    
    print("\nCalling 'check_cluster_health' through MCP...")
    res = call_mcp_tool("check_cluster_health")
    print(f"Result Preview:\n{res[:200]}...")
