"""
EvoOps Incident Scenario Runner CLI
Usage:
    python scenarios/runner.py list
    python scenarios/runner.py show <scenario_id>
    python scenarios/runner.py status
    python scenarios/runner.py trigger <scenario_id>
    python scenarios/runner.py reset [service_name|all]
    python scenarios/runner.py traffic [--duration 30] [--rate 1.0]
"""

import sys
import json
import time
import random
import argparse
from pathlib import Path
import urllib.request
import urllib.error

CATALOG_PATH = Path(__file__).parent / "catalog.json"

SERVICES = {
    "api-gateway": 8000,
    "order-service": 8001,
    "inventory-service": 8002,
    "payment-service": 8003,
    "notification-service": 8004,
}


def load_catalog():
    if not CATALOG_PATH.exists():
        print(f"[Error] Catalog file not found at {CATALOG_PATH}")
        sys.exit(1)
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def http_post(url: str, data: dict):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 0, str(e)


def http_get(url: str):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 0, str(e)


def cmd_list(args):
    catalog = load_catalog()
    scenarios = catalog.get("scenarios", [])
    print(f"\n{'='*75}")
    print(f"  EvoOps Incident Scenarios Catalog ({len(scenarios)} Scenarios)")
    print(f"{'='*75}")
    print(f"{'ID':<30} {'TARGET':<22} {'RISK':<8} {'APPROVAL'}")
    print("-" * 75)
    for sc in scenarios:
        appr = "Yes" if sc.get("requires_approval") else "No"
        print(f"{sc['id']:<30} {sc['target_service']:<22} {sc['risk_level']:<8} {appr}")
    print("-" * 75)
    print("Run: python scenarios/runner.py show <scenario_id> for details.\n")


def cmd_show(args):
    catalog = load_catalog()
    sc = next((s for s in catalog["scenarios"] if s["id"] == args.scenario_id), None)
    if not sc:
        print(f"[Error] Scenario '{args.scenario_id}' not found.")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"  Scenario: {sc['name']} ({sc['id']})")
    print(f"{'='*70}")
    print(f"Target Service   : {sc['target_service']} (Port {sc['port']})")
    print(f"Category         : {sc['category']}")
    print(f"Risk Level       : {sc['risk_level']} (Requires Approval: {sc['requires_approval']})")
    print(f"Fault Injection  : {json.dumps(sc['injection'])}")
    print(f"\n[Root Cause]\n  {sc['root_cause']}")
    print(f"\n[Symptoms]\n  - Metrics: {sc['symptoms']['metrics']}\n  - Traces : {sc['symptoms']['traces']}\n  - Logs   : {sc['symptoms']['logs']}")
    print(f"\n[Misleading Signals]\n  {sc['misleading_signals']}")
    print(f"\n[Recommended Remediation]\n  {sc['recommended_remediation']}")
    print(f"\n[Verification Metric]\n  {sc['verification_metric']}")
    print(f"{'='*70}\n")


def cmd_status(args):
    print(f"\n{'='*65}")
    print("  EvoOps Cluster Chaos Status")
    print(f"{'='*65}")
    print(f"{'SERVICE':<24} {'STATUS':<10} {'LATENCY':<10} {'ERR RATE'}")
    print("-" * 65)
    for svc_name, port in SERVICES.items():
        url = f"http://localhost:{port}/chaos/status"
        code, resp = http_get(url)
        if code == 200 and isinstance(resp, dict):
            active_str = "ACTIVE" if resp.get("active") else "NORMAL"
            lat = f"{resp.get('latency_seconds', 0.0):.1f}s"
            rate = f"{resp.get('error_rate', 0.0) * 100:.0f}%"
            print(f"{svc_name:<24} {active_str:<10} {lat:<10} {rate}")
        else:
            print(f"{svc_name:<24} OFFLINE ({resp})")
    print("-" * 65 + "\n")


def cmd_trigger(args):
    catalog = load_catalog()
    sc = next((s for s in catalog["scenarios"] if s["id"] == args.scenario_id), None)
    if not sc:
        print(f"[Error] Scenario '{args.scenario_id}' not found.")
        sys.exit(1)

    port = sc["port"]
    url = f"http://localhost:{port}/chaos/inject"
    print(f"[*] Injecting scenario: {sc['name']} on http://localhost:{port}/chaos/inject ...")
    code, resp = http_post(url, sc["injection"])
    if code == 200:
        print(f"[SUCCESS] Incident triggered successfully!")
        print(f"Details: {json.dumps(resp, indent=2)}")
        print("\nTip: Run traffic in parallel to observe traces in Jaeger & Grafana:")
        print("  python scenarios/runner.py traffic --duration 30")
    else:
        print(f"[FAILED] HTTP {code}: {resp}")


def cmd_reset(args):
    target = args.service
    services_to_reset = SERVICES.keys() if target in ["all", None] else [target]

    print(f"\n[*] Resetting chaos faults on: {', '.join(services_to_reset)} ...")
    for svc_name in services_to_reset:
        if svc_name not in SERVICES:
            print(f"  [Skip] Unknown service '{svc_name}'")
            continue
        port = SERVICES[svc_name]
        url = f"http://localhost:{port}/chaos/reset"
        code, resp = http_post(url, {})
        status = "OK" if code == 200 else f"ERR ({code})"
        print(f"  - {svc_name:<24}: {status}")
    print("[Done] All specified services reset to normal operation.\n")


def cmd_traffic(args):
    duration = args.duration
    rate = args.rate
    gateway_url = "http://localhost:8000/orders"

    print(f"\n[*] Generating realistic order traffic to {gateway_url} for {duration} seconds at ~{rate} req/s...")
    start_time = time.time()
    count = 0
    success = 0
    errors = 0


    while time.time() - start_time < duration:
        count += 1
        payload = {
            "user_id": f"user_{random.randint(100, 999)}",
            "product_id": random.choice(["prod-1", "prod-2"]),
            "quantity": 1,
            "amount": 49.99
        }

        req_start = time.time()
        code, resp = http_post(gateway_url, payload)
        elapsed = time.time() - req_start

        if 200 <= code < 300:
            success += 1
            print(f"  [#{count}] HTTP {code} OK ({elapsed:.2f}s)")
        else:
            errors += 1
            print(f"  [#{count}] HTTP {code} FAIL ({elapsed:.2f}s) -> {str(resp)[:60]}")

        sleep_time = max(0.0, (1.0 / rate) - elapsed)
        time.sleep(sleep_time)

    print(f"\n{'='*50}")
    print(f"Traffic Simulation Finished:")
    print(f"  Total Requests : {count}")
    print(f"  Success (2xx)  : {success}")
    print(f"  Errors (4xx/5xx): {errors}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="EvoOps Incident Scenario Runner CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List all cataloged incident scenarios")
    p_list.set_defaults(func=cmd_list)

    # show
    p_show = subparsers.add_parser("show", help="Show full details of a specific scenario")
    p_show.add_argument("scenario_id", help="Scenario ID (e.g. downstream_timeout)")
    p_show.set_defaults(func=cmd_show)

    # status
    p_status = subparsers.add_parser("status", help="Get chaos injection status of all services")
    p_status.set_defaults(func=cmd_status)

    # trigger
    p_trigger = subparsers.add_parser("trigger", help="Inject/Trigger an incident scenario")
    p_trigger.add_argument("scenario_id", help="Scenario ID from the catalog")
    p_trigger.set_defaults(func=cmd_trigger)

    # reset
    p_reset = subparsers.add_parser("reset", help="Reset chaos injection back to normal")
    p_reset.add_argument("service", nargs="?", default="all", help="Service name or 'all' (default)")
    p_reset.set_defaults(func=cmd_reset)

    # traffic
    p_traffic = subparsers.add_parser("traffic", help="Generate simulated order traffic")
    p_traffic.add_argument("--duration", type=int, default=20, help="Duration in seconds (default: 20)")
    p_traffic.add_argument("--rate", type=float, default=1.5, help="Requests per second (default: 1.5)")
    p_traffic.set_defaults(func=cmd_traffic)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
