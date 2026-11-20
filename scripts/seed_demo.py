#!/usr/bin/env python3
"""Seed TestPilot with a demo account, project, tests, a schedule and some run history.

    python scripts/seed_demo.py --api http://localhost:8000 --target http://demo-api:9000

Login afterwards with demo@testpilot.dev / demo-pass-123
"""

import argparse
import sys
import time

import httpx

EMAIL, PASSWORD = "demo@testpilot.dev", "demo-pass-123"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--target", default="http://demo-api:9000", help="URL of the demo API as seen by the TestPilot worker")
    parser.add_argument("--runs", type=int, default=5, help="healthy runs to create (builds performance history)")
    args = parser.parse_args()
    base = args.api.rstrip("/") + "/api/v1"

    with httpx.Client(timeout=30) as http:
        res = http.post(f"{base}/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": "Demo Developer"})
        if res.status_code == 409:
            res = http.post(f"{base}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        res.raise_for_status()
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        res = http.post(f"{base}/projects", headers=headers, json={
            "name": "Demo Store API", "description": "Sample project pointing at the bundled demo API",
            "base_url": args.target, "variables": {"token": "demo-token"},
        })
        if res.status_code == 409:
            print("Demo project already exists - nothing to do.")
            return 0
        res.raise_for_status()
        pid = res.json()["id"]
        p = f"{base}/projects/{pid}"

        col = http.post(f"{p}/collections", headers=headers, json={"name": "Smoke tests", "description": "Fast checks on every deploy"}).json()
        cases = [
            {"name": "Health check", "path": "/health", "assertions": [{"type": "json_path", "path": "$.status", "operator": "eq", "value": "ok"}]},
            {"name": "List products", "path": "/products", "query_params": {"limit": "10"}, "assertions": [
                {"type": "json_path", "path": "$.count", "operator": "gte", "value": 1},
                {"type": "json_path", "path": "$.items", "operator": "type", "value": "array"},
                {"type": "response_time", "max_ms": 1500}]},
            {"name": "Get product 1", "path": "/products/1", "assertions": [
                {"type": "json_path", "path": "$.name", "operator": "eq", "value": "Mechanical Keyboard"},
                {"type": "json_path", "path": "$.price", "operator": "type", "value": "number"}]},
            {"name": "Missing product returns 404", "path": "/products/999", "expected_status": 404},
            {"name": "Create product", "method": "POST", "path": "/products", "body_type": "json", "expected_status": 201,
             "body": {"name": "Webcam", "price": 59.9, "stock": 5}, "assertions": [{"type": "json_path", "path": "$.name", "operator": "eq", "value": "Webcam"}]},
            {"name": "Reject invalid product", "method": "POST", "path": "/products", "body_type": "json", "body": {"name": "", "price": -1}, "expected_status": 422},
            {"name": "Current user (bearer auth)", "path": "/users/me", "auth_type": "bearer", "auth_config": {"token": "{{token}}"},
             "assertions": [{"type": "json_path", "path": "$.plan", "operator": "eq", "value": "pro"}]},
            {"name": "Unauthenticated user rejected", "path": "/users/me", "expected_status": 401},
        ]
        for case in cases:
            http.post(f"{p}/test-cases", headers=headers, json={"collection_id": col["id"], **case}).raise_for_status()

        http.post(f"{p}/schedules", headers=headers, json={"name": "Every 15 minutes", "cron": "*/15 * * * *", "collection_id": col["id"]}).raise_for_status()

        for i in range(args.runs):
            run = http.post(f"{p}/runs", headers=headers, json={"collection_id": col["id"], "label": f"seed-{i + 1}"})
            run.raise_for_status()
            run_id = run.json()["id"]
            for _ in range(60):
                state = http.get(f"{p}/runs/{run_id}", headers=headers).json()
                if state["status"] not in ("queued", "running"):
                    break
                time.sleep(0.5)
            print(f"run #{run_id}: {state['status']} ({state['passed']}/{state['total']} passed)")

    print(f"\nSeeded. Sign in with {EMAIL} / {PASSWORD}")
    print("Break the demo API to see a regression:  curl -X POST <demo-api>/admin/mode -H 'content-type: application/json' -d '{\"mode\":\"broken\"}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
