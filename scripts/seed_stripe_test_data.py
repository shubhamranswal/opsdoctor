"""Seed realistic Stripe test-mode transactions via Swytchcode.

Populates the connected Stripe test environment with operational test payments:
- Succeeded baseline transactions
- Payments requiring customer 3D-Secure action (requires_action)
- Unconfirmed / incomplete checkouts (requires_payment_method)
- Declined transactions (card_declined)

All calls execute strictly through Swytchcode without raw HTTP or API keys.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.adapters.base import BaseSwytchcodeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_stripe")


def seed_stripe_test_data():
    client = BaseSwytchcodeClient()
    logger.info("Initializing Stripe test dataset seeding via Swytchcode...")

    # 1. Create Test Customers
    customers = {}
    customer_defs = [
        {
            "name": "Meridian Tech",
            "email": "billing@meridiantech.io",
            "description": "Enterprise SaaS Customer - Cloud Tier",
            "metadata": {"org": "Meridian", "tier": "enterprise"},
        },
        {
            "name": "Vantage AI Labs",
            "email": "ops@vantageai.dev",
            "description": "Growth Plan Customer - AI Services",
            "metadata": {"org": "Vantage", "tier": "growth"},
        },
    ]

    for cdef in customer_defs:
        try:
            logger.info("Creating customer '%s'...", cdef["name"])
            res = client.execute("stripe.customer.create", cdef)
            cid = res.get("id")
            customers[cdef["name"]] = cid
            logger.info("Created customer %s with ID: %s", cdef["name"], cid)
        except Exception as e:
            logger.error("Failed to create customer %s: %s", cdef["name"], e)

    meridian_id = customers.get("Meridian Tech")
    vantage_id = customers.get("Vantage AI Labs")

    # 2. Define Test PaymentIntents
    payment_intents = [
        # (1) Succeeded baseline 1
        {
            "amount": 125000,  # $1,250.00
            "currency": "usd",
            "customer": meridian_id,
            "description": "Monthly Enterprise Subscription - Sep 2026",
            "payment_method": "pm_card_visa",
            "confirm": True,
            "return_url": "https://opsdoctor.acmeflow.internal/checkout/complete",
            "metadata": {"flow": "enterprise-billing", "order_id": "ORD-STRIPE-101"},
        },
        # (2) Succeeded baseline 2
        {
            "amount": 90000,  # $900.00
            "currency": "usd",
            "customer": vantage_id,
            "description": "API Usage Tier Upgrade",
            "payment_method": "pm_card_visa",
            "confirm": True,
            "return_url": "https://opsdoctor.acmeflow.internal/checkout/complete",
            "metadata": {"flow": "checkout-v2", "order_id": "ORD-STRIPE-102"},
        },
        # (3) Pending - 3DS Action Required (Customer Challenge Pending)
        # (Already created pi_3UJiheRpzp5AdrAh1Scb7Oru, omit to avoid duplicate)
        # (4) Pending - Unconfirmed Checkout
        # (Already created pi_3UJihjRpzp5AdrAh144OTNjH, omit to avoid duplicate)
        # (5) Failed - Card Declined Simulation
        {
            "amount": 68000,  # $680.00
            "currency": "usd",
            "customer": meridian_id,
            "description": "Failed Payment Attempt - Decline Simulated",
            "payment_method": "pm_card_chargeCustomerFail",
            "confirm": True,
            "return_url": "https://opsdoctor.acmeflow.internal/checkout/complete",
            "metadata": {
                "flow": "checkout-v2",
                "order_id": "ORD-STRIPE-105",
                "error_simulation": "card_declined",
            },
        },

    ]

    created_records = []
    for pi_def in payment_intents:
        # Clean null customer if failed
        payload = {k: v for k, v in pi_def.items() if v is not None}
        desc = payload.get("description")
        logger.info("Executing PaymentIntent creation for '%s'...", desc)
        try:
            res = client.execute("stripe.payment_intent.create", payload)
            pi_id = res.get("id")
            pi_status = res.get("status")
            pi_amt = res.get("amount")
            created_records.append({
                "id": pi_id,
                "status": pi_status,
                "amount": pi_amt,
                "description": desc,
                "metadata": payload.get("metadata", {}),
            })
            logger.info("Successfully created %s: status=%s, amount=%s", pi_id, pi_status, pi_amt)
        except Exception as e:
            logger.error("Failed to create PaymentIntent '%s': %s", desc, e)

    # 3. Read back verified transactions via Swytchcode
    logger.info("\n=== VERIFYING CREATED RECORDS VIA STRIPE.PAYMENT_INTENT.LIST ===")
    try:
        list_res = client.execute("stripe.payment_intent.list", {"limit": 10})
        live_items = list_res.get("data", [])
        logger.info("Retrieved %d PaymentIntents from live Stripe test account:", len(live_items))
        for idx, item in enumerate(live_items):
            logger.info(
                "  [%d] ID: %s | Status: %s | Amount: $%s | Desc: %s",
                idx + 1,
                item.get("id"),
                item.get("status"),
                f"{item.get('amount', 0) / 100.0:.2f}",
                item.get("description"),
            )
    except Exception as e:
        logger.error("Verification list query failed: %s", e)

    return created_records


if __name__ == "__main__":
    seed_stripe_test_data()
