"""End-to-end verification of OpsDoctor agent product and approval workflow."""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from apps.web.main import app

def test_opsdoctor_end_to_end():
    client = TestClient(app)

    print("=== Step 1: Health & Systems Check ===")
    r = client.get("/health")
    assert r.status_code == 200
    print("Health OK:", r.json())

    r = client.get("/api/systems/status")
    assert r.status_code == 200
    data = r.json()
    print("All connected:", data.get("all_connected"))

    print("\n=== Step 2: Trigger Autonomous Investigation ===")
    req_body = {
        "session_id": "e2e-test-session",
        "message": "Investigate incident ticket KAN-4 and check if any policy escalation is required",
    }
    chat_res = client.post("/api/agent/chat", json=req_body)
    assert chat_res.status_code == 200, chat_res.text
    chat_data = chat_res.json()

    print("Activities emitted:", len(chat_data.get("activities", [])))
    for a in chat_data.get("activities", []):
        print(f"  [{a['step_type']}] {a['title']}")

    print("\nEvidence items retrieved:", len(chat_data.get("evidence", [])))
    for ev in chat_data.get("evidence", []):
        print(f"  [{ev['system']}] {ev['title']}")

    approvals = chat_data.get("approvals", [])
    print(f"\nApprovals staged: {len(approvals)}")
    assert len(approvals) >= 1, "Expected at least 1 approval request staged for Jira escalation comment"

    target_appr = approvals[0]
    appr_id = target_appr["id"]
    print(f"Staged Approval ID: {appr_id}")
    print(f"Title: {target_appr['title']}")
    print(f"Target: {target_appr['target']}")
    print(f"Status: {target_appr['status']}")

    print("\n=== Step 3: Verify Approval in /api/approvals ===")
    appr_list_res = client.get("/api/approvals")
    assert appr_list_res.status_code == 200
    appr_list = appr_list_res.json()
    assert any(a["id"] == appr_id for a in appr_list)
    print("Approval verified in registry.")

    print("\n=== Step 4: Execute Human-in-the-Loop Approval ===")
    # Approve and execute via Swytchcode live
    approve_res = client.post(f"/api/approvals/{appr_id}/approve")
    assert approve_res.status_code == 200, approve_res.text
    approve_data = approve_res.json()
    print("Execution status:", approve_data.get("status"))
    print("Message:", approve_data.get("message"))
    exec_appr = approve_data.get("approval", {})
    assert exec_appr.get("status") == "executed"
    print("Executed at:", exec_appr.get("executed_at"))
    print("Result:", exec_appr.get("execution_result"))

    print("\n=== SUCCESS: OpsDoctor Agent Product Verified End-to-End! ===")

if __name__ == "__main__":
    test_opsdoctor_end_to_end()
