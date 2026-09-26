"""Comprehensive Product-Grade Agent Test Suite for OpsDoctor.

Covers:
1. Capability-first routing (Jira-only, Notion-only, Gmail-only, PayPal-only, Stripe-only)
2. Multi-provider payment queries ("Any pending payments?", "Compare payment failures")
3. Verification that generic payment queries do NOT unnecessarily invoke Jira
4. Multi-hop investigations starting from gateway telemetry, not Jira
5. Ambiguous request graceful fallback
6. Tool resilience on simulated failure
7. Approval lifecycle: staging, approval execution, and rejection
8. Session persistence across instances
9. Multi-turn conversation history
"""

import json
import os
import sys
import unittest
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agent.orchestrator import OpsDoctorOrchestrator
from packages.agent.approvals import ApprovalManager
from packages.agent.state import StepType, ApprovalStatus
from packages.adapters.payments.manager import UnifiedPaymentManager


class TestComprehensiveAgentMatrix(unittest.TestCase):
    """Full-scale test matrix validating capability-first operations intelligence."""

    @classmethod
    def setUpClass(cls):
        cls.orchestrator = OpsDoctorOrchestrator()

    def _get_executed_tools(self, response):
        return [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]

    # --- 1. Domain Isolation Tests ---
    def test_01_jira_only_request(self):
        """Jira query invokes ONLY Jira tools."""
        sid = f"test-c-jira-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "What is the status and description of ticket KAN-1?")
        tools = self._get_executed_tools(res)
        
        self.assertIn("jira_get_issue", tools)
        self.assertEqual(len(tools), 1)
        self.assertNotIn("paypal_get_order", tools)
        self.assertNotIn("stripe_get_payment", tools)
        self.assertNotIn("payments_get_pending", tools)
        self.assertIn("KAN-1", res.content)

    def test_02_notion_only_request(self):
        """Notion query invokes ONLY Notion tools."""
        sid = f"test-c-notion-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "What does our Notion policy say about refund approvals?")
        tools = self._get_executed_tools(res)

        self.assertIn("notion_read_policy_page", tools)
        self.assertEqual(len(tools), 1)
        self.assertNotIn("jira_get_issue", tools)
        self.assertNotIn("payments_get_pending", tools)
        self.assertIn("Refund Policy", res.content)

    def test_03_gmail_only_request(self):
        """Gmail query invokes ONLY Gmail tools."""
        sid = f"test-c-gmail-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Search customer emails for complaints from BrightPath Labs")
        tools = self._get_executed_tools(res)

        self.assertIn("gmail_search_messages", tools)
        self.assertEqual(len(tools), 1)
        self.assertNotIn("jira_get_issue", tools)
        self.assertNotIn("payments_get_pending", tools)
        self.assertTrue("brightpath" in res.content.lower() or "subscription" in res.content.lower())

    def test_04_paypal_only_request(self):
        """PayPal order query invokes ONLY PayPal tool."""
        sid = f"test-c-pp-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Inspect the status of order ORD-88190 in PayPal Sandbox")
        tools = self._get_executed_tools(res)

        self.assertIn("paypal_get_order", tools)
        self.assertEqual(len(tools), 1)
        self.assertNotIn("jira_get_issue", tools)
        self.assertNotIn("stripe_get_payment", tools)
        self.assertIn("ORD-88190", res.content)

    def test_05_stripe_only_request(self):
        """Stripe payment query invokes ONLY Stripe tool."""
        sid = f"test-c-stripe-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Inspect Stripe payment pi_3PqaA4LkdIwHu7ix01mK81a1")
        tools = self._get_executed_tools(res)

        self.assertIn("stripe_get_payment", tools)
        self.assertEqual(len(tools), 1)
        self.assertNotIn("jira_get_issue", tools)
        self.assertNotIn("paypal_get_order", tools)
        self.assertIn("pi_3PqaA4LkdIwHu7ix01mK81a1", res.content)
        self.assertIn("Meridian Tech", res.content)

    # --- 2. Multi-Provider Payment Intelligence & Non-Jira Verification ---
    def test_06_generic_pending_payments_does_not_invoke_jira(self):
        """CRITICAL: 'Any pending payments?' must inspect payment providers and NOT invoke Jira."""
        sid = f"test-c-pending-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Any pending payments?")
        tools = self._get_executed_tools(res)

        self.assertIn("payments_get_pending", tools)
        self.assertNotIn("jira_get_issue", tools, "Jira MUST NOT be invoked for generic payment queries")
        self.assertNotIn("jira_search_issues", tools)
        self.assertIn("2 transaction(s)", res.content)
        self.assertIn("STRIPE", res.content)
        self.assertIn("PAYPAL", res.content)

    def test_07_provider_specific_pending_payments(self):
        """'Show me pending Stripe payments' and 'Show me pending PayPal payments' filter correctly."""
        sid_s = f"test-c-stripe-pend-{uuid.uuid4().hex[:6]}"
        res_s = self.orchestrator.run_turn(sid_s, "Show me pending Stripe payments")
        tools_s = self._get_executed_tools(res_s)
        self.assertIn("payments_get_pending", tools_s)
        self.assertNotIn("jira_get_issue", tools_s)
        self.assertIn("STRIPE", res_s.content)

        sid_p = f"test-c-paypal-pend-{uuid.uuid4().hex[:6]}"
        res_p = self.orchestrator.run_turn(sid_p, "Show me pending PayPal payments")
        tools_p = self._get_executed_tools(res_p)
        self.assertIn("payments_get_pending", tools_p)
        self.assertNotIn("jira_get_issue", tools_p)
        self.assertIn("0 pending", res_p.content)

    def test_08_compare_payment_failures_across_gateways(self):
        """Cross-provider comparison evaluates failure rates between PayPal and Stripe."""
        sid = f"test-c-comp-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Compare payment failures across PayPal and Stripe")
        tools = self._get_executed_tools(res)

        self.assertIn("payments_compare_providers", tools)
        self.assertNotIn("jira_get_issue", tools)
        self.assertIn("PAYPAL", res.content)
        self.assertIn("STRIPE", res.content)
        self.assertIn("highest failure rate", res.content.lower())

    # --- 3. Multi-Hop Investigation: Evidence-Driven, Not Jira-First ---
    def test_09_investigation_starts_from_telemetry_not_jira(self):
        """Root cause triage starts with gateway failure telemetry, branching into Jira only after observation."""
        sid = f"test-c-inv-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "Investigate why checkout payments are failing")
        tools = self._get_executed_tools(res)

        # Proves first tool is payment telemetry, not Jira!
        self.assertEqual(tools[0], "paypal_get_incident_evidence", "First investigation step must be gateway telemetry")
        self.assertIn("jira_get_issue", tools)
        self.assertIn("notion_read_policy_page", tools)
        self.assertIn("slack_read_channel", tools)
        self.assertGreaterEqual(len(res.approvals), 1, "Must stage approval when policy threshold exceeded")

    # --- 4. Ambiguity, Tool Failure & Resilience ---
    def test_10_ambiguous_request_graceful_overview(self):
        """Ambiguous query returns operational overview without crashing."""
        sid = f"test-c-ambig-{uuid.uuid4().hex[:6]}"
        res = self.orchestrator.run_turn(sid, "What is our current operational status today?")
        tools = self._get_executed_tools(res)

        self.assertIn("payments_get_overview", tools)
        self.assertIn("Total Transactions Today", res.content)

    def test_11_tool_failure_resilience(self):
        """Tool failure returns error structure and does not crash orchestrator turn."""
        reg = self.orchestrator.tool_registry
        # Call with nonexistent tool or invalid param
        res = reg.execute_tool("paypal_get_order", order_id="NONEXISTENT-ORDER-XXXX")
        self.assertIsInstance(res, dict)

    # --- 5. Human-in-the-Loop Approvals Lifecycle ---
    def test_12_approval_staging_and_execution_lifecycle(self):
        """Test approval creation, rejection, and approval execution."""
        appr_mgr = self.orchestrator.approval_manager

        # Stage request
        req = appr_mgr.create_request(
            action_type="jira_add_comment",
            system="jira",
            target="KAN-4",
            title="Test Escalation Comment",
            explanation="Test threshold satisfied",
            proposed_payload={"issue_key": "KAN-4", "comment_text": "OpsDoctor Test Comment"},
        )
        self.assertEqual(req.status, ApprovalStatus.PENDING)

        # Rejection
        rejected = appr_mgr.reject_request(req.id)
        self.assertEqual(rejected.status, ApprovalStatus.REJECTED)

        # New request for approval execution
        req2 = appr_mgr.create_request(
            action_type="jira_add_comment",
            system="jira",
            target="KAN-4",
            title="Approved Test Comment",
            explanation="Approved by operator",
            proposed_payload={"issue_key": "KAN-4", "comment_text": "OpsDoctor Verified Comment"},
        )
        approved = appr_mgr.approve_and_execute(req2.id)
        self.assertEqual(approved.status, ApprovalStatus.EXECUTED)
        self.assertIsNotNone(approved.execution_result)

    # --- 6. Session Persistence & Multi-Turn ---
    def test_13_session_persistence_and_multi_turn(self):
        """Multi-turn conversation persists turns and history across separate orchestrator instances."""
        sid = f"test-c-multi-{uuid.uuid4().hex[:6]}"

        orch1 = OpsDoctorOrchestrator()
        turn1 = orch1.run_turn(sid, "What is the status of ticket KAN-1?")
        self.assertIn("KAN-1", turn1.content)

        # Instance 2 loads session from disk
        orch2 = OpsDoctorOrchestrator()
        restored = orch2.get_or_create_session(sid)
        self.assertEqual(len(restored.messages), 2)

        # Turn 2 in instance 2
        turn2 = orch2.run_turn(sid, "Any pending payments?")
        self.assertIn("2 transaction(s)", turn2.content)

        # Check total messages on disk
        orch3 = OpsDoctorOrchestrator()
        final_sess = orch3.get_or_create_session(sid)
        self.assertEqual(len(final_sess.messages), 4, "Must have 2 user messages and 2 assistant messages")


if __name__ == "__main__":
    unittest.main()
