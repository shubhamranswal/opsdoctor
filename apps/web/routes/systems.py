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
    """Inspect live connection status of all connected systems via Swytchcode."""
    swy = find_swytchcode_bin()
    auth_status_raw = ""
    try:
        p = subprocess.run([swy, "auth", "status"], capture_output=True, text=True, timeout=10)
        auth_status_raw = p.stdout
    except Exception as e:
        auth_status_raw = str(e)

    import os
    has_stripe_key = bool(os.getenv("STRIPE_API_KEY"))
    stripe_connected = has_stripe_key or ("stripe" in auth_status_raw and ("connected" in auth_status_raw or "local" in auth_status_raw))

    # Check systems
    systems = {
        "jira": {
            "name": "Jira Cloud",
            "site": "acmeflow-ops",
            "project": "OPS (KAN)",
            "connected": "jira" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "incident_ticket": "KAN-4",
            "capabilities": ["issue_tracking", "incident_triage", "comments", "escalations"],
        },
        "paypal": {
            "name": "PayPal Sandbox",
            "account": "sb-zddxc47755225@business.example.com",
            "connected": True,
            "type": "sandbox_header_override",
            "orders_count": 8,
            "failed_captures": 7,
            "capabilities": ["checkout_orders", "capture_telemetry", "reporting"],
        },
        "stripe": {
            "name": "Stripe Payments",
            "account": "Connected Test Environment",
            "connected": stripe_connected,
            "auth_status": "connected" if stripe_connected else "ready_for_auth",
            "auth_command": "swytchcode auth connect Stripe",
            "type": "api_key",
            "active_methods": ["stripe.payment_intent.list", "stripe.payment_intent.get", "stripe.payment_intent.create", "stripe.charge.list", "stripe.charge.get", "stripe.refund.list"],
            "capabilities": ["payment_intents", "charges", "refunds", "customer_creation", "settlement"],
        },

        "slack": {
            "name": "Slack Workspace",
            "workspace": "AcmeFlow Operations",
            "connected": "slack" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "channels": ["#ops-alerts", "#ops-incidents", "#payments", "#general", "#all-acmeflow-operations", "#social"],
            "capabilities": ["channel_history", "incident_alerts", "team_coordination"],
        },
        "gmail": {
            "name": "Google Workspace / Gmail",
            "account": "shubhamgivesdemo@gmail.com",
            "connected": "gmail" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "verified_emails": 14,
            "capabilities": ["customer_support", "complaint_threads", "email_search"],
        },
        "notion": {
            "name": "Notion Workspace",
            "workspace": "AcmeFlow Operations",
            "connected": "notion" in auth_status_raw and "connected" in auth_status_raw,
            "type": "oauth2",
            "policy_pages": ["Payment Procedures", "Incident Response", "Escalation Rules", "Refund Policy", "Customer Support SOP", "Team Ownership"],
            "capabilities": ["operational_runbooks", "incident_policies", "escalation_thresholds"],
        },
    }

    all_connected = all(s.get("connected") for s in systems.values())
    return {
        "all_connected": all_connected,
        "environment": "AcmeFlow Operations (Sandbox/Staging)",
        "systems": systems,
    }


@router.get("/ready")
def get_readiness() -> Dict[str, Any]:
    """Readiness probe for production / container orchestration."""
    status = get_systems_status()
    is_ready = status["all_connected"]
    return {
        "status": "ready" if is_ready else "degraded",
        "ready": is_ready,
        "connected_systems_count": sum(1 for s in status["systems"].values() if s.get("connected")),
        "total_systems_count": len(status["systems"]),
    }
