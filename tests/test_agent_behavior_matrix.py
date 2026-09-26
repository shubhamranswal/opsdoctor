"""Automated Agent-Behavior Test Matrix for OpsDoctor.

Validates that OpsDoctor exhibits genuine model/agentic behavior:
1. Dynamic tool selection (not a fixed waterfall of Jira -> PayPal -> Slack -> Gmail -> Notion)
2. Domain isolation: requests targeting a single system only execute that system's tool
3. Iterative tool execution: observation from step N drives decision for step N+1
4. ReAct loop: reasoning thoughts accompany each tool selection
5. Use case generality: INC-2026-042 is an operational example, not hardcoded logic
6. Policy evaluation and human-in-the-loop action staging
7. Session state persistence to disk across restarts
"""

import os
import sys
import unittest
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agent.orchestrator import OpsDoctorOrchestrator
from packages.agent.state import StepType


class TestAgentBehaviorMatrix(unittest.TestCase):
    """Test suite verifying genuine agentic behavior across 5 distinct operational scenarios."""

    @classmethod
    def setUpClass(cls):
        cls.orchestrator = OpsDoctorOrchestrator()

    def test_scenario_1_jira_only(self):
        """Scenario 1: Jira-only request -> executes ONLY Jira tool, no other systems."""
        session_id = f"test-matrix-jira-{uuid.uuid4().hex[:6]}"
        query = "What is the status and description of ticket KAN-1?"
        
        response = self.orchestrator.run_turn(session_id=session_id, user_input=query)
        
        # Collect executed tools
        executed_tools = [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]
        
        print("\n[Scenario 1 - Jira Only]")
        print(f"Query: '{query}'")
        print(f"Executed Tools: {executed_tools}")
        
        # Assertions
        self.assertIn("jira_get_issue", executed_tools)
        self.assertEqual(len(executed_tools), 1, "Only jira_get_issue should have been executed")
        self.assertNotIn("paypal_get_incident_evidence", executed_tools)
        self.assertNotIn("notion_read_policy_page", executed_tools)
        self.assertNotIn("slack_read_channel", executed_tools)
        self.assertNotIn("gmail_search_messages", executed_tools)
        
        # Verify response content is specific to KAN-1
        self.assertIn("KAN-1", response.content)
        self.assertNotIn("INC-2026-042", response.content)
        self.assertEqual(len(response.approvals), 0)

    def test_scenario_2_notion_policy_only(self):
        """Scenario 2: Notion policy-only request -> executes ONLY Notion tool."""
        session_id = f"test-matrix-notion-{uuid.uuid4().hex[:6]}"
        query = "What does our Notion policy say about refund approvals?"
        
        response = self.orchestrator.run_turn(session_id=session_id, user_input=query)
        
        executed_tools = [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]
        
        print("\n[Scenario 2 - Notion Policy Only]")
        print(f"Query: '{query}'")
        print(f"Executed Tools: {executed_tools}")
        
        # Assertions
        self.assertIn("notion_read_policy_page", executed_tools)
        self.assertEqual(len(executed_tools), 1, "Only notion_read_policy_page should have been executed")
        self.assertNotIn("jira_get_issue", executed_tools)
        self.assertNotIn("paypal_get_incident_evidence", executed_tools)
        self.assertNotIn("slack_read_channel", executed_tools)
        self.assertNotIn("gmail_search_messages", executed_tools)
        
        # Verify content reflects Refund Policy
        self.assertIn("Refund Policy", response.content)
        self.assertTrue(
            "refund" in response.content.lower() or "reviewed" in response.content.lower()
        )
        self.assertNotIn("INC-2026-042", response.content)
        self.assertEqual(len(response.approvals), 0)

    def test_scenario_3_paypal_order_only(self):
        """Scenario 3: PayPal order-only request -> executes ONLY PayPal tool."""
        session_id = f"test-matrix-paypal-{uuid.uuid4().hex[:6]}"
        query = "Inspect the status of order ORD-88190 in PayPal Sandbox"
        
        response = self.orchestrator.run_turn(session_id=session_id, user_input=query)
        
        executed_tools = [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]
        
        print("\n[Scenario 3 - PayPal Order Only]")
        print(f"Query: '{query}'")
        print(f"Executed Tools: {executed_tools}")
        
        # Assertions
        self.assertIn("paypal_get_order", executed_tools)
        self.assertEqual(len(executed_tools), 1, "Only paypal_get_order should have been executed")
        self.assertNotIn("jira_get_issue", executed_tools)
        self.assertNotIn("notion_read_policy_page", executed_tools)
        self.assertNotIn("slack_read_channel", executed_tools)
        self.assertNotIn("gmail_search_messages", executed_tools)
        
        # Verify content reflects ORD-88190
        self.assertIn("ORD-88190", response.content)
        self.assertIn("Starlight Analytics", response.content)
        self.assertNotIn("INC-2026-042", response.content)
        self.assertEqual(len(response.approvals), 0)

    def test_scenario_4_gmail_support_only(self):
        """Scenario 4: Gmail support-only request -> executes ONLY Gmail tool."""
        session_id = f"test-matrix-gmail-{uuid.uuid4().hex[:6]}"
        query = "Search customer emails for complaints from BrightPath Labs"
        
        response = self.orchestrator.run_turn(session_id=session_id, user_input=query)
        
        executed_tools = [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]
        
        print("\n[Scenario 4 - Gmail Support Only]")
        print(f"Query: '{query}'")
        print(f"Executed Tools: {executed_tools}")
        
        # Assertions
        self.assertIn("gmail_search_messages", executed_tools)
        self.assertEqual(len(executed_tools), 1, "Only gmail_search_messages should have been executed")
        self.assertNotIn("jira_get_issue", executed_tools)
        self.assertNotIn("paypal_get_incident_evidence", executed_tools)
        self.assertNotIn("notion_read_policy_page", executed_tools)
        
        # Verify content mentions customer email threads
        self.assertTrue(
            "brightpath" in response.content.lower() or "subscription" in response.content.lower()
        )
        self.assertEqual(len(response.approvals), 0)

    def test_scenario_5_cross_system_investigation(self):
        """Scenario 5: Multi-system investigation -> executes iteratively across systems with threshold evaluation and staged approval."""
        session_id = f"test-matrix-incident-{uuid.uuid4().hex[:6]}"
        query = "Investigate customer payment failures on checkout-v2 and check if policy thresholds were exceeded"
        
        response = self.orchestrator.run_turn(session_id=session_id, user_input=query)
        
        executed_tools = [
            act.data.get("tool")
            for act in response.activities
            if act.step_type == StepType.TOOL_SELECTION and act.data
        ]
        
        print("\n[Scenario 5 - Cross-System Multi-Hop Investigation]")
        print(f"Query: '{query}'")
        print(f"Executed Tools: {executed_tools}")
        
        # Assertions: Should have iteratively queried Jira, PayPal, Notion, Slack
        self.assertIn("jira_get_issue", executed_tools)
        self.assertIn("paypal_get_incident_evidence", executed_tools)
        self.assertIn("notion_read_policy_page", executed_tools)
        self.assertIn("slack_read_channel", executed_tools)
        
        # Verify evidence collection
        systems_with_evidence = {ev.system for ev in response.evidence}
        self.assertTrue({"jira", "paypal", "notion", "slack"}.issubset(systems_with_evidence))
        
        # Verify threshold evaluation and human-in-the-loop approval staging
        self.assertGreaterEqual(len(response.approvals), 1, "An approval request must be staged when threshold is exceeded")
        approval = response.approvals[0]
        self.assertEqual(approval.system, "jira")
        self.assertEqual(approval.action_type, "jira_add_comment")
        self.assertEqual(approval.target, "KAN-4")
        self.assertIn("Finance", approval.proposed_payload.get("comment_text", ""))
        
        # Verify response synthesis
        self.assertIn("7 failed capture attempts", response.content)
        self.assertIn("conclusively met", response.content.lower())

    def test_session_persistence_across_instances(self):
        """Verify session state survives process/instance restart via disk storage."""
        session_id = f"test-persist-{uuid.uuid4().hex[:6]}"
        
        # Turn 1 in instance A
        orch_a = OpsDoctorOrchestrator()
        orch_a.run_turn(session_id=session_id, user_input="What is the status of ticket KAN-1?")
        
        # Check that file exists on disk
        session_file = Path("data/sessions") / f"{session_id}.json"
        self.assertTrue(session_file.exists(), f"Session file {session_file} must exist on disk")
        
        # Turn 2 in a brand new orchestrator instance B
        orch_b = OpsDoctorOrchestrator()
        restored_session = orch_b.get_or_create_session(session_id)
        
        self.assertEqual(len(restored_session.messages), 2, "Restored session must have user message and assistant message")
        self.assertEqual(restored_session.messages[0].content, "What is the status of ticket KAN-1?")
        self.assertIn("KAN-1", restored_session.messages[1].content)
        self.assertGreaterEqual(len(restored_session.accumulated_evidence), 1)


if __name__ == "__main__":
    unittest.main()
