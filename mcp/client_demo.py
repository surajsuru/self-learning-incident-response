"""
EvoOps MCP Client Demo (Phase 17 - Stage 2).
Demonstrates how an external AI client (Claude Desktop / Cursor) connects
to EvoOps MCP Server via STDIO (subprocess) and JSON-RPC 2.0.
"""


import sys
import json
import subprocess
from pathlib import Path

PYTHON_EXE = sys.executable
SERVER_SCRIPT = str(Path(__file__).parent / "sre_server.py")


def send_rpc(proc, msg: dict) -> dict:
    """Sends a JSON-RPC message over stdin and reads the response from stdout."""
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    proc.stdin.flush()
    response_line = proc.stdout.readline().decode("utf-8").strip()
    if not response_line:
        raise RuntimeError("Empty response received from MCP server process.")
    return json.loads(response_line)



def main():
    print("=" * 65)
    print("  EvoOps MCP Client Demo — Connecting via STDIO (Subprocess)")
    print("=" * 65)
    # 1. Spawn the MCP server as a subprocess exactly like Claude Desktop / Cursor does
    print(f"\n[1/4] Spawning server process: {PYTHON_EXE} mcp/sre_server.py ...")
    proc = subprocess.Popen(
        [PYTHON_EXE, SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )
    try:
        # 2. Handshake: initialize
        print("\n[2/4] Handshaking (initialize)...")
        init_resp = send_rpc(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        })
        server_name = init_resp["result"]["serverInfo"]["name"]
        server_ver = init_resp["result"]["serverInfo"]["version"]
        print(f"Status: Connected to '{server_name}' (version {server_ver})")
        # 3. Discover tools: tools/list
        print("\n[3/4] Discovering available tools (tools/list)...")
        tools_resp = send_rpc(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        })
        tools = tools_resp["result"]["tools"]
        print(f"Found {len(tools)} tools exposed by EvoOps:")
        for t in tools:
            print(f"  • {t['name']}: {t['description'][:70]}...")
        # 4. Execute tool: tools/call (check_cluster_health)
        print("\n[4/4] Executing tool 'check_cluster_health' over JSON-RPC STDIO...")
        call_resp = send_rpc(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "check_cluster_health", "arguments": {}}
        })
        content = call_resp["result"]["content"][0]["text"]
        print("Response received from cluster:")
        print(content[:350] + "\n  ... [truncated for display]")
        print("\n" + "=" * 65)
        print("  Stage 2 Verification Complete: STDIO JSON-RPC Communication Verified!")
        print("=" * 65)
    finally:
        # Cleanly shut down the subprocess
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
