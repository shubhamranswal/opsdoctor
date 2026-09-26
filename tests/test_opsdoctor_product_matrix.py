"""OpsDoctor Product-Grade 15-Scenario Comprehensive Automated Test Suite.

Validates the complete 15-point specification defined in the Product Architecture:
1. Pending payment query does not call Jira.
2. PayPal-specific query uses PayPal.
3. Stripe-specific query uses Stripe.
4. Cross-provider payment query checks connected payment providers.
5. Disconnected providers are not queried.
6. Connected-but-empty providers are reported as empty.
7. No hardcoded transaction summaries returned.
8. Follow-up questions retain conversational context.
9. Agent dynamically selects multiple tools when evidence requires it.
10. Consequential actions require approval.
11. Approved actions execute through Swytchcode.
12. Jira comments use proper professional formatting.
13. Agent answers are derived from actual tool observations.
14. Stripe test records are real records from the connected Stripe test account.
15. Restarting the application preserves session state.
"""

import os
import sys
import unittest
import uuid
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agent.orchestrator import OpsDoctorOrchestrator
from packages.agent.approvals import ApprovalManager
from packages.agent.state import StepType, ApprovalStatus, ResponseType
from packages.adapters.payments.manager import UnifiedPaymentManager
from packages.adapters.payments.stripe import StripePaymentProvider
from packages.adapters.payments.paypal import PayPalPaymentProvider
from packages.domain.payment import PaymentStatus


class TestOpsDoctorProductMatrix(unittest.TestCase):
    """The authoritative 15-scenario product verification test suite."""

    @classmethod
    def setUpClass(cls):
        cls.orchestrator = OpsDoctorOrchestrator()
        cls.payment_manager = UnifiedPaymentManager()

    def _get_executed_tools(self, response) -> List[str]:
        return [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data and act.data.get("tool")
        ]

    # Scenario 1: Pending payment query does not call Jira
    def test_01_pending_payment_query_does_not_call_jira(self):
        """User asks about pending payments -> uses payment tools, NEVER calls Jira."""
        sid = f"test-matrix-01-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Show me pending payments")
        tools = self._get_executed_tools(res)

        self.assertIn("payments_get_pending", tools)
        jira_tools = [t for t in tools if t.startswith("jira_")]
        self.assertEqual(len(jira_tools), 0, f"Jira must not be invoked for pending payment queries: {jira_tools}")
        self.assertIn("STRIPE", res.content)

    # Scenario 2: PayPal-specific query uses PayPal
    def test_02_paypal_specific_query_uses_paypal(self):
        """User asks about PayPal order -> queries PayPal, not Stripe or Jira."""
        sid = f"test-matrix-02-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Inspect the status of order ORD-88190 in PayPal Sandbox")
        tools = self._get_executed_tools(res)

        self.assertIn("paypal_get_order", tools)
        self.assertEqual(len(tools), 1, "Only PayPal tool should execute")
        self.assertNotIn("stripe_get_payment", tools)
        self.assertNotIn("jira_get_issue", tools)
        self.assertIn("ORD-88190", res.content)

    # Scenario 3: Stripe-specific query uses Stripe
    def test_03_stripe_specific_query_uses_stripe(self):
        """User asks about Stripe payment -> queries Stripe, not PayPal or Jira."""
        sid = f"test-matrix-03-{uuid.uuid4().hex[:6]}"
        # Querying live real PaymentIntent seeded in Stripe test account
        res = self.orchestrator.run_turn(sid, "Inspect Stripe payment pi_3UJiheRpzp5AdrAh1Scb7Oru")
        tools = self._get_executed_tools(res)

        self.assertIn("stripe_get_payment", tools)
        self.assertEqual(len(tools), 1, "Only Stripe tool should execute")
        self.assertNotIn("paypal_get_order", tools)
        self.assertNotIn("jira_get_issue", tools)
        self.assertIn("pi_3UJiheRpzp5AdrAh1Scb7Oru", res.content)

    # Scenario 4: Cross-provider payment query checks connected payment providers
    def test_04_cross_provider_payment_query_checks_connected_providers(self):
        """Cross-provider query compares metrics across all connected gateways (PayPal & Stripe)."""
        sid = f"test-matrix-04-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "what payment gateway is having more payment fails?")
        tools = self._get_executed_tools(res)

        self.assertIn("payments_compare_providers", tools)
        self.assertIn("PAYPAL", res.content.upper())
        self.assertIn("STRIPE", res.content.upper())
        self.assertIn("failure rate", res.content.lower())
        self.assertEqual(res.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(res.actions), 0, "Read-only comparative query must never stage action cards")
        self.assertEqual(len(res.approvals), 0)

    # Scenario 5: Disconnected providers are not queried
    def test_05_disconnected_providers_are_not_queried(self):
        """When a provider is not configured/disconnected, it is skipped and not queried."""
        # Test manager with only PayPal connected
        paypal_only_mgr = UnifiedPaymentManager(providers={"paypal": PayPalPaymentProvider()})
        self.assertIsNone(paypal_only_mgr.get_provider("stripe"))
        self.assertIsNone(paypal_only_mgr.get_provider("square"))

        res = paypal_only_mgr.get_pending_payments("square")
        self.assertEqual(res["total_pending_count"], 0)
        self.assertEqual(res["provider_breakdown"], {})

        # Whole check skips disconnected providers
        all_res = paypal_only_mgr.get_pending_payments()
        self.assertIn("paypal", all_res["provider_breakdown"])
        self.assertNotIn("stripe", all_res["provider_breakdown"])
        self.assertNotIn("square", all_res["provider_breakdown"])

    # Scenario 6: Connected-but-empty providers are reported as empty
    def test_06_connected_but_empty_providers_reported_empty(self):
        """Connected provider with 0 pending payments returns count: 0 and reports empty accurately."""
        # PayPal Sandbox currently has completed and failed orders, but 0 pending
        paypal_res = self.payment_manager.get_pending_payments("paypal")
        self.assertEqual(paypal_res["provider_breakdown"]["paypal"]["count"], 0)
        self.assertEqual(paypal_res["provider_breakdown"]["paypal"]["transactions"], [])

        # Agent communicates empty state faithfully
        sid = f"test-matrix-06-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Show me pending PayPal payments")
        self.assertIn("0 pending", res.content.lower())

    # Scenario 7: No hardcoded transaction summaries returned
    def test_07_no_hardcoded_transaction_summaries_returned(self):
        """Agent's pending payment output contains real transaction IDs, amounts, and live counts."""
        sid = f"test-matrix-07-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Show me pending payments")
        
        # Verify real IDs and real customer details appear in the output
        self.assertTrue(
            "pi_3UJi" in res.content or "Meridian" in res.content,
            "Response must reflect real live Stripe data, not hardcoded dummy text"
        )
        self.assertNotIn("your_method_id", res.content)
        self.assertNotIn("fake_tx_id", res.content)

    # Scenario 8: Follow-up questions retain conversational context
    def test_08_followup_questions_retain_conversational_context(self):
        """Multi-turn context allows follow-ups like 'Why is the Meridian payment stuck?' without re-specifying IDs."""
        sid = f"test-matrix-08-{uuid.uuid4().hex[:6]}"

        turn1 = self.orchestrator.run_turn(sid, "Show me pending payments")
        self.assertIn("STRIPE", turn1.content)

        turn2 = self.orchestrator.run_turn(sid, "Which ones are stuck?")
        self.assertIn("Detailed Bottleneck Analysis", turn2.content)

        turn3 = self.orchestrator.run_turn(sid, "Why is the Meridian payment stuck?")
        self.assertIn("Meridian Tech", turn3.content)
        self.assertTrue(
            "requires_payment_method" in turn3.content or "requires_action" in turn3.content or "checkout" in turn3.content or "3d secure" in turn3.content.lower() or "pipeline" in turn3.content.lower(),
            "Turn 3 must identify the transaction bottleneck reason from multi-turn context"
        )

    # Scenario 9: Agent dynamically selects multiple tools when evidence requires it
    def test_09_agent_dynamically_selects_multiple_tools_when_needed(self):
        """Investigation of checkout payment failures dynamically pulls cross-system evidence."""
        sid = f"test-matrix-09-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Investigate why checkout payments are failing")
        tools = self._get_executed_tools(res)

        # Dynamic tool selection spanning telemetry, ticketing, policy, and communications
        self.assertEqual(tools[0], "paypal_get_incident_evidence", "First tool must be gateway telemetry")
        self.assertIn("jira_get_issue", tools)
        self.assertIn("notion_read_policy_page", tools)
        self.assertIn("slack_read_channel", tools)
        self.assertGreaterEqual(len(res.approvals), 1, "Must stage approval when policy threshold exceeded")

    # Scenario 10: Consequential actions require approval
    def test_10_consequential_actions_require_approval(self):
        """Consequential actions (e.g. Jira escalation) stage an approval request instead of auto-executing."""
        sid = f"test-matrix-10-{uuid.uuid4().hex[:6]}"
        # Direct escalation command
        res = self.orchestrator.run_turn(sid, "Escalate incident INC-2026-042 to Jira")
        self.assertGreaterEqual(len(res.approvals), 1, "Must stage approval request")
        appr = res.approvals[0]
        self.assertEqual(appr.status, ApprovalStatus.PENDING)
        self.assertEqual(appr.system, "jira")

    # Scenario 11: Approved actions execute through Swytchcode
    def test_11_approved_actions_execute_through_swytchcode(self):
        """Approving a staged action executes it via Swytchcode and transitions to EXECUTED."""
        appr_mgr = self.orchestrator.approval_manager
        req = appr_mgr.create_request(
            action_type="jira_add_comment",
            system="jira",
            target="KAN-4",
            title="Automated Suite Verification",
            explanation="Verifying that approved action executes via Swytchcode",
            proposed_payload={
                "issue_key": "KAN-4",
                "comment_text": "OpsDoctor Automated Verification\nAction approved and executed via Swytchcode.\nStatus: Verified.",
            },
        )
        self.assertEqual(req.status, ApprovalStatus.PENDING)

        executed = appr_mgr.approve_and_execute(req.id)
        self.assertEqual(executed.status, ApprovalStatus.EXECUTED)
        self.assertIsNotNone(executed.execution_result)
        self.assertEqual(executed.execution_result.get("status"), "success")
        self.assertIn("comment_id", executed.execution_result)

    # Scenario 12: Jira comments use clean plain text formatting without Markdown symbols
    def test_12_jira_comments_use_proper_professional_formatting(self):
        """Jira comment payload uses clean plain text without markdown asterisks, backticks, underscores, or headers."""
        sid = f"test-matrix-12-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Escalate it")
        self.assertGreaterEqual(len(res.approvals), 1)

        comment_text = res.approvals[0].proposed_payload.get("comment_text", "")
        self.assertIn("OpsDoctor Investigation", comment_text)
        self.assertIn("Incident: INC-2026-042", comment_text)
        self.assertTrue("Findings:" in comment_text or "Evidence:" in comment_text)
        self.assertIn("Policy:", comment_text)
        self.assertIn("Assessment:", comment_text)
        self.assertNotIn("*", comment_text, "Comment must not contain markdown asterisks")
        self.assertNotIn("_", comment_text, "Comment must not contain markdown underscores")
        self.assertNotIn("`", comment_text, "Comment must not contain backticks")
        self.assertNotIn("###", comment_text, "Comment must not contain raw markdown header tokens")
        self.assertIn("Generated by OpsDoctor", comment_text)

    # Scenario 13: Agent answers are derived from actual tool observations
    def test_13_agent_answers_derived_from_actual_tool_observations(self):
        """Agent output dynamically incorporates specific observation values returned by tools."""
        sid = f"test-matrix-13-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "What is the status and description of ticket KAN-1?")
        
        # Must reflect the actual summary and status retrieved from Jira for KAN-1
        self.assertIn("KAN-1", res.content)
        self.assertTrue("task 1" in res.content.lower() or "to do" in res.content.lower() or "ops" in res.content.lower())

    # Scenario 14: Stripe test records are real records from the connected Stripe test account
    def test_14_stripe_test_records_are_real_connected_records(self):
        """Stripe provider fetches live records directly from connected Stripe test account via Swytchcode."""
        stripe_provider = StripePaymentProvider()
        transactions = stripe_provider.list_transactions(limit=10)

        self.assertGreater(len(transactions), 0, "Connected Stripe account must return live test records")
        for tx in transactions:
            self.assertTrue(tx.id.startswith("pi_"), f"ID must be real PaymentIntent: {tx.id}")
            self.assertEqual(tx.provider, "stripe")
            self.assertEqual(tx.currency, "USD")

        # Verify real customer transaction
        customer_names = [tx.customer for tx in transactions if tx.customer]
        has_created_customer = any("cus_VKNT" in c for c in customer_names) or any("meridian" in c.lower() for c in customer_names)
        self.assertTrue(has_created_customer, f"Must include real created test customer cus_VKNT...: {customer_names}")

    # Scenario 15: Restarting the application preserves session state
    def test_15_restarting_application_preserves_session_state(self):
        """Session state persists to disk and is completely restored by a new orchestrator instance."""
        sid = f"test-matrix-15-{uuid.uuid4().hex[:6]}"

        # Instance A creates session and runs turn 1
        orch_a = OpsDoctorOrchestrator()
        turn1 = orch_a.run_turn(sid, "What is the status of ticket KAN-1?")
        self.assertIn("KAN-1", turn1.content)

        # Instance B (simulating app restart) loads session from disk
        orch_b = OpsDoctorOrchestrator()
        session_b = orch_b.session_store.get(sid)
        self.assertIsNotNone(session_b, "Session must exist on disk after restart")
        self.assertEqual(len(session_b.messages), 2, "Must contain turn 1 user and assistant messages")

        # Instance B runs turn 2
        turn2 = orch_b.run_turn(sid, "Any pending payments?")
        self.assertIn("STRIPE", turn2.content)

        # Verify combined history is intact
        orch_c = OpsDoctorOrchestrator()
        session_c = orch_c.session_store.get(sid)
        self.assertEqual(len(session_c.messages), 4, "Must contain all 4 messages across restarts")


if __name__ == "__main__":
    unittest.main()
