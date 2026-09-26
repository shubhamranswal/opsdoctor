"""Audit & Verification Test Suite for OpsDoctor Tool Selection & Execution Layer.

Covers:
- Test A: "what payment gateway is having more payment fails?" -> Read-only comparative analysis, no actions.
- Test B: "show me pending payments" -> Read-only pending payment breakdown, no actions.
- Test C: "investigate the PayPal checkout failures" -> Read-only PayPal root cause & evidence recording, no actions.
- Test D: "check whether this violates any operational policy" -> Read-only Notion policy retrieval & assessment, no actions.
- Test E: "Escalate it" -> Stages Jira comment action proposal (PENDING), no auto-execution.
- Test F: Approve staged action -> approve_and_execute runs Jira comment via Swytchcode, transitions to EXECUTED.
- Test G: Follow-up "what payment gateway is having more payment fails?" -> Read-only, actions=[], does not leak previous action card.
- Slack Tools Test: Capability query vs actionable Slack post proposal & approval execution.
- Diagnostic API Verification: GET /api/agent/tools reports all 19 tools with schemas and access classifications.
"""

import unittest
import uuid
from packages.agent.orchestrator import OpsDoctorOrchestrator
from packages.agent.state import ResponseType, ApprovalStatus
from packages.agent.tools import ToolRegistry


class TestToolSelectionAndExecutionLayer(unittest.TestCase):
    def setUp(self):
        self.orchestrator = OpsDoctorOrchestrator()
        self.session_id = f"test-audit-layer-{uuid.uuid4().hex[:8]}"

    def _get_executed_tools(self, res):
        tools = []
        for a in res.activities:
            if a.data and "tool" in a.data:
                tools.append(a.data["tool"])
        return tools

    def test_01_diagnostic_tool_registry(self):
        """Verify that all 19 tools are registered with schemas, categories, and safety tags."""
        registry = ToolRegistry()
        inventory = registry.get_diagnostic_inventory()

        self.assertEqual(len(inventory), 19)
        read_tools = [t for t in inventory if t["type"] == "READ"]
        action_tools = [t for t in inventory if t["type"] == "ACTION"]
        self.assertEqual(len(read_tools), 16)
        self.assertEqual(len(action_tools), 3)

        tool_names = [t["name"] for t in inventory]
        # Verify critical previously unrouted tools are present
        self.assertIn("payments_get_failed", tool_names)
        self.assertIn("slack_post_message", tool_names)
        self.assertIn("slack_list_channels", tool_names)
        self.assertIn("slack_read_channel", tool_names)
        self.assertIn("notion_search_policies", tool_names)
        self.assertIn("notion_read_policy_page", tool_names)
        self.assertIn("jira_search_issues", tool_names)
        self.assertIn("gmail_get_message", tool_names)

        # Check action tools
        action_names = [t["name"] for t in action_tools]
        self.assertIn("jira_add_comment", action_names)
        self.assertIn("jira_update_issue", action_names)
        self.assertIn("slack_post_message", action_names)

    def test_02_sequential_tests_a_through_g(self):
        """Execute the exact sequential conversation workflow Tests A through G."""
        sid = self.session_id

        # TEST A: "what payment gateway is having more payment fails?"
        print("\n--- Running Test A: what payment gateway is having more payment fails? ---")
        turn_a = self.orchestrator.run_turn(sid, "what payment gateway is having more payment fails?")
        tools_a = self._get_executed_tools(turn_a)
        self.assertIn("payments_compare_providers", tools_a)
        self.assertEqual(turn_a.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(turn_a.actions), 0, "Test A must not propose actions")
        self.assertEqual(len(turn_a.approvals), 0)
        self.assertIn("PAYPAL", turn_a.content.upper())
        self.assertIn("STRIPE", turn_a.content.upper())

        # TEST B: "show me pending payments"
        print("\n--- Running Test B: show me pending payments ---")
        turn_b = self.orchestrator.run_turn(sid, "show me pending payments")
        tools_b = self._get_executed_tools(turn_b)
        self.assertIn("payments_get_pending", tools_b)
        self.assertEqual(turn_b.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(turn_b.actions), 0, "Test B must not propose actions")
        self.assertEqual(len(turn_b.approvals), 0)
        self.assertIn("Pending Payments Status Overview", turn_b.content)

        # TEST C: "investigate the PayPal checkout failures"
        print("\n--- Running Test C: investigate the PayPal checkout failures ---")
        turn_c = self.orchestrator.run_turn(sid, "investigate the PayPal checkout failures")
        tools_c = self._get_executed_tools(turn_c)
        self.assertIn("paypal_get_incident_evidence", tools_c)
        self.assertEqual(turn_c.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(turn_c.actions), 0, "Test C must not propose actions")
        self.assertTrue("PAYPAL" in turn_c.content.upper() or "CHECKOUT" in turn_c.content.upper())

        # TEST D: "check whether this violates any operational policy"
        print("\n--- Running Test D: check whether this violates any operational policy ---")
        turn_d = self.orchestrator.run_turn(sid, "check whether this violates any operational policy")
        tools_d = self._get_executed_tools(turn_d)
        self.assertTrue("notion_read_policy_page" in tools_d or "notion_search_policies" in tools_d)
        self.assertEqual(turn_d.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(turn_d.actions), 0, "Test D must not propose actions")
        self.assertIn("Policy Assessment", turn_d.content)

        # TEST E: "Escalate it"
        print("\n--- Running Test E: Escalate it ---")
        turn_e = self.orchestrator.run_turn(sid, "Escalate it")
        self.assertEqual(turn_e.response_type, ResponseType.ACTION_PROPOSAL)
        self.assertEqual(len(turn_e.actions), 1, "Test E must stage exactly 1 action proposal")
        self.assertEqual(len(turn_e.approvals), 1)
        action_card = turn_e.actions[0]
        self.assertEqual(action_card.status, ApprovalStatus.PENDING)
        self.assertEqual(action_card.system, "jira")
        self.assertIn("comment_text", action_card.proposed_payload)
        approval_id = turn_e.approvals[0].id

        # TEST F: Approve staged action
        print("\n--- Running Test F: Approve staged action ---")
        appr_mgr = self.orchestrator.approval_manager
        executed_appr = appr_mgr.approve_and_execute(approval_id)
        self.assertEqual(executed_appr.status, ApprovalStatus.EXECUTED)
        self.assertIsNotNone(executed_appr.execution_result)
        self.assertEqual(executed_appr.execution_result.get("status"), "success")
        self.assertIn("comment_id", executed_appr.execution_result)

        # TEST G: Follow-up "what payment gateway is having more payment fails?"
        print("\n--- Running Test G: Follow-up what payment gateway is having more payment fails? ---")
        turn_g = self.orchestrator.run_turn(sid, "what payment gateway is having more payment fails?")
        tools_g = self._get_executed_tools(turn_g)
        self.assertIn("payments_compare_providers", tools_g)
        self.assertEqual(turn_g.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(turn_g.actions), 0, "Test G must NOT carry over previously executed action card")
        self.assertEqual(len(turn_g.approvals), 0)

    def test_03_slack_tool_selection_and_execution(self):
        """Verify Slack capability exploration and actionable message posting via Swytchcode."""
        sid = f"test-slack-{uuid.uuid4().hex[:6]}"

        # Slack capability inquiry
        res_info = self.orchestrator.run_turn(sid, "can i make it post something on slack?")
        tools_info = self._get_executed_tools(res_info)
        self.assertIn("slack_list_channels", tools_info)
        self.assertEqual(res_info.response_type, ResponseType.READ_ONLY)
        self.assertEqual(len(res_info.actions), 0)
        self.assertIn("Yes, OpsDoctor Can Post to Slack", res_info.content)
        self.assertIn("ops-incidents", res_info.content)

        # Direct instruction to post on Slack -> stages ACTION_PROPOSAL
        res_post = self.orchestrator.run_turn(sid, "Post an update to #ops-incidents saying 'OpsDoctor health check verified.'")
        self.assertEqual(res_post.response_type, ResponseType.ACTION_PROPOSAL)
        self.assertEqual(len(res_post.actions), 1)
        action_card = res_post.actions[0]
        self.assertEqual(action_card.system, "slack")
        self.assertEqual(action_card.action_type, "slack_post_message")
        self.assertIn("OpsDoctor health check verified", action_card.proposed_payload.get("message", ""))
        self.assertEqual(action_card.status, ApprovalStatus.PENDING)

        # Approve and execute Slack post via Swytchcode
        appr_id = res_post.approvals[0].id
        executed = self.orchestrator.approval_manager.approve_and_execute(appr_id)
        self.assertEqual(executed.status, ApprovalStatus.EXECUTED)
        self.assertIsNotNone(executed.execution_result)
        self.assertEqual(executed.execution_result.get("status"), "success")
        self.assertIn("ts", executed.execution_result)


if __name__ == "__main__":
    unittest.main()
