"""Cross-system chronological timeline route."""

import json
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter

router = APIRouter(prefix="/api/timeline", tags=["timeline"])

@router.get("")
def get_timeline() -> List[Dict[str, Any]]:
    """Return unified chronological event timeline across Jira, PayPal, Slack, Gmail, Notion."""
    fixtures_dir = Path(__file__).resolve().parents[2] / "data" / "fixtures"

    events = [
        {
            "id": "evt-01",
            "timestamp": "2026-09-25T14:12:00Z",
            "display_time": "14:12 UTC",
            "system": "slack",
            "category": "deployment",
            "title": "Service Deployment: checkout-api",
            "description": "Release checkout-api-2026.09.25.3 deployed to production (us-east-1) via CI/CD pipeline #4412. Commit 9f8a12c.",
            "source": "#ops-alerts",
            "severity": "info",
        },
        {
            "id": "evt-02",
            "timestamp": "2026-09-25T14:18:22Z",
            "display_time": "14:18 UTC",
            "system": "slack",
            "category": "metric_alert",
            "title": "Elevated HTTP 4xx on Checkout Capture",
            "description": "Error rate on endpoint /v2/checkout/orders/capture exceeded threshold 1.0% (Current: 2.14%). Flow: checkout-v2.",
            "source": "#ops-alerts",
            "severity": "warning",
        },
        {
            "id": "evt-03",
            "timestamp": "2026-09-25T14:22:00Z",
            "display_time": "14:22 UTC",
            "system": "gmail",
            "category": "customer_impact",
            "title": "Customer Complaint: BrightPath Labs (ORD-88219)",
            "description": "Customer BrightPath Labs reported repeated payment failures on annual subscription checkout with PayPal reference PAYID-MZ4910.",
            "source": "support@acmeflow.com",
            "severity": "high",
        },
        {
            "id": "evt-04",
            "timestamp": "2026-09-25T14:31:00Z",
            "display_time": "14:31 UTC",
            "system": "gmail",
            "category": "customer_impact",
            "title": "Enterprise Renewal Failure: OmniCorp Logistics (ORD-88225)",
            "description": "Procurement team encountered generic error attempting to renew $4,800.00 enterprise license.",
            "source": "procurement@omnicorplogistics.com",
            "severity": "high",
        },
        {
            "id": "evt-05",
            "timestamp": "2026-09-25T14:34:00Z",
            "display_time": "14:34 UTC",
            "system": "slack",
            "category": "pagerduty",
            "title": "PagerDuty P1 Alert: CRITICAL_PAYMENT_FAILURE_RATE",
            "description": "Provider: PayPal | Flow: checkout-v2 | Failure Rate: 14.8% (Threshold: 5.0%) | Assigned: Ethan Cole.",
            "source": "#ops-alerts",
            "severity": "critical",
        },
        {
            "id": "evt-06",
            "timestamp": "2026-09-25T14:38:00Z",
            "display_time": "14:38 UTC",
            "system": "jira",
            "category": "incident_tracking",
            "title": "Jira Incident Ticket Created: KAN-4",
            "description": "Ticket KAN-4 opened for INC-2026-042: Customer payment failures during checkout-v2 PayPal flow.",
            "source": "https://acmeflow-ops.atlassian.net/browse/KAN-4",
            "severity": "critical",
        },
        {
            "id": "evt-07",
            "timestamp": "2026-09-25T21:40:55Z",
            "display_time": "21:40 UTC",
            "system": "paypal",
            "category": "gateway_telemetry",
            "title": "7 Failed Capture Attempts Recorded in PayPal Sandbox",
            "description": "7 sequential capture attempts on orders ORD-88219, ORD-88225, ORD-88231, ORD-88240 failed with HTTP 422 ORDER_NOT_APPROVED.",
            "source": "PayPal Sandbox (api-m.sandbox.paypal.com)",
            "severity": "critical",
        },
        {
            "id": "evt-08",
            "timestamp": "2026-09-25T21:41:30Z",
            "display_time": "Policy Engine",
            "system": "notion",
            "category": "policy_evaluation",
            "title": "Notion Policy Evaluated: > 5 Failures Threshold Satisfied",
            "description": "Payment Procedures & Escalation Rules specify: More than 5 failed transactions within 15 minutes requires Finance escalation.",
            "source": "Notion > AcmeFlow Operations / Escalation Rules",
            "severity": "action_required",
        },
    ]

    return events
