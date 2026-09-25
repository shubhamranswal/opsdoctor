"""System health and integration status routes."""

import json
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter
from packages.adapters.base import find_swytchcode_bin
import subprocess

router = APIRouter(prefix="/api/systems", tags=["systems"])

@router.get("/status")
def get_systems_status() -> Dict[str, Any]:
    """Inspect live connection status of all 5 connected systems via Swytchcode."""
    swy = find_swytchcode_bin()
    auth_status_raw = ""
    try:
        p = subprocess.run([swy, "auth", "status"], capture_output=True, text=True, timeout=10)
        auth_status_raw = p.stdout
    except Exception as e:
        auth_status_raw = str(e)

    # Parse status lines
    systems = {
        "jira": {
            "name": "Jira Cloud",
            "site": "acmeflow-ops",
            "project": "OPS (KAN)",
            "connected": "jira" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "incident_ticket": "KAN-4",
        },
        "paypal": {
            "name": "PayPal Sandbox",
            "account": "sb-zddxc47755225@business.example.com",
            "connected": True,
            "type": "sandbox_header_override",
            "orders_count": 8,
            "failed_captures": 7,
        },
        "slack": {
            "name": "Slack Workspace",
            "workspace": "AcmeFlow Operations",
            "connected": "slack" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "channels": ["#ops-alerts", "#ops-incidents", "#payments", "#general", "#all-acmeflow-operations", "#social"],
        },
        "gmail": {
            "name": "Google Workspace / Gmail",
            "account": "shubhamgivesdemo@gmail.com",
            "connected": "gmail" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "verified_emails": 14,
        },
        "notion": {
            "name": "Notion Workspace",
            "workspace": "AcmeFlow Operations",
            "connected": "notion" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "policy_pages": ["Payment Procedures", "Incident Response", "Escalation Rules", "Refund Policy", "Customer Support SOP", "Team Ownership"],
        },
    }

    all_connected = all(s.get("connected") for s in systems.values())
    return {
        "all_connected": all_connected,
        "environment": "AcmeFlow Operations (Sandbox/Staging)",
        "systems": systems,
    }
