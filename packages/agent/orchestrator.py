"""OpsDoctor Agent Orchestrator.

Implements genuine agentic execution:
1. Model-driven & cognitive intent understanding
2. Dynamic ReAct loop with iterative tool selection & execution
3. Evidence aggregation across Jira, PayPal Sandbox, Slack, Gmail, and Notion
4. Policy evaluation against runbooks
5. Consequential action staging with human-in-the-loop approvals
6. Disk-backed persistent session storage
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from packages.agent.approvals import ApprovalManager
from packages.agent.llm import CognitiveBrain, StepDecision
from packages.agent.state import (
    ActivityStep,
    AgentMessage,
    ApprovalRequest,
    EvidenceItem,
    InvestigationSession,
    ResponseType,
    StepType,
)
from packages.agent.storage import SessionStore
from packages.agent.tools import ToolDefinition, ToolRegistry

logger = logging.getLogger("opsdoctor.orchestrator")


class OpsDoctorOrchestrator:
    """Agentic orchestrator for autonomous business operations investigation."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        approval_manager: Optional[ApprovalManager] = None,
        session_store: Optional[SessionStore] = None,
        brain: Optional[CognitiveBrain] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.approval_manager = approval_manager or ApprovalManager(self.tool_registry)
        self.session_store = session_store or SessionStore()
        self.brain = brain or CognitiveBrain()

    def get_or_create_session(self, session_id: Optional[str] = None) -> InvestigationSession:
        sid = session_id or f"sess-{uuid.uuid4().hex[:8]}"
        session = self.session_store.get(sid)
        if not session:
            session = InvestigationSession(
                session_id=sid,
                title="Operations Investigation",
            )
            self.session_store.save(session)
        return session

    def run_turn(
        self,
        session_id: str,
        user_input: str,
        stream_callback: Optional[Callable[[ActivityStep], None]] = None,
    ) -> AgentMessage:
        """Execute an autonomous investigation turn using an iterative ReAct loop."""
        session = self.get_or_create_session(session_id)
        activities: List[ActivityStep] = []
        evidence_items: List[EvidenceItem] = []
        approvals: List[ApprovalRequest] = []
        working_memory: Dict[str, Any] = {}

        def emit_activity(
            step_type: StepType,
            title: str,
            description: str,
            system: Optional[str] = None,
            data: Optional[Dict[str, Any]] = None,
        ) -> ActivityStep:
            step = ActivityStep(
                id=f"step-{uuid.uuid4().hex[:6]}",
                step_type=step_type,
                title=title,
                description=description,
                system=system,
                data=data,
            )
            activities.append(step)
            if stream_callback:
                stream_callback(step)
            return step

        # Step 0: Understand Intent & Context
        emit_activity(
            StepType.UNDERSTANDING,
            title="Understanding Operational Intent",
            description=f"Analyzing user request: '{user_input}'",
            data={"query": user_input},
        )

        max_iterations = 7
        iteration = 0
        final_decision: Optional[StepDecision] = None

        # ReAct Cognitive Loop
        while iteration < max_iterations:
            iteration += 1

            # Decide next step with cognitive engine
            decision = self.brain.decide_step(
                query=user_input,
                history=session.messages,
                tool_definitions=self.tool_registry.list_tools(),
                working_memory=working_memory,
                executed_steps=activities,
            )

            if decision.is_final:
                final_decision = decision
                # Check for staged action requiring human-in-the-loop approval
                if decision.staged_action:
                    act = decision.staged_action
                    req = self.approval_manager.create_request(
                        action_type=act["action_type"],
                        system=act["system"],
                        target=act["target"],
                        title=act["title"],
                        explanation=act["explanation"],
                        proposed_payload=act["proposed_payload"],
                        session_id=session.session_id,
                    )
                    approvals.append(req)
                    emit_activity(
                        StepType.APPROVAL_REQUIRED,
                        title="Action Staged for User Approval",
                        description=f"Prepared {act['system'].upper()} action for {act['target']}. Staged for review.",
                        system=act["system"],
                        data={"approval_id": req.id, "target": act["target"]},
                    )
                break

            # Handle Tool Call
            tool_name = decision.tool_name
            tool_args = decision.arguments or {}
            tool_def = self.tool_registry.get_tool(tool_name)
            system = tool_def.system if tool_def else "system"

            step_desc = decision.action_summary or f"Querying {tool_name} across {system.upper()} integration."
            emit_activity(
                StepType.TOOL_SELECTION,
                title=f"Selected Tool: {tool_name}",
                description=step_desc,
                system=system,
                data={"tool": tool_name, "args": tool_args},
            )

            # Check if tool itself is marked consequential
            if tool_def and tool_def.is_consequential:
                req = self.approval_manager.create_request(
                    action_type=tool_name,
                    system=system,
                    target=str(tool_args.get("issue_key") or tool_args.get("channel_name", "action")),
                    title=f"Execute {tool_name}",
                    explanation=decision.action_summary or f"Consequential action {tool_name} requires confirmation.",
                    proposed_payload=tool_args,
                    session_id=session.session_id,
                )
                approvals.append(req)
                emit_activity(
                    StepType.APPROVAL_REQUIRED,
                    title="Consequential Action Requires Approval",
                    description=f"Tool {tool_name} requires human confirmation before execution.",
                    system=system,
                    data={"approval_id": req.id},
                )
                break


            # Execute tool safely via Swytchcode registry
            tool_result = self.tool_registry.execute_tool(tool_name, **tool_args)

            emit_activity(
                StepType.TOOL_EXECUTION,
                title=f"Executed Tool: {tool_name}",
                description=f"Completed {tool_name} call across {system.upper()} integration.",
                system=system,
                data={"args": tool_args, "result_preview": str(tool_result)[:250]},
            )

            # Ingest tool observation into working memory and record evidence
            if tool_name in ("jira_get_issue", "jira_search_issues"):
                working_memory["jira_issue"] = tool_result
                working_memory["jira_incident"] = tool_result
                if isinstance(tool_result, dict) and tool_result.get("key"):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="jira",
                        title=f"Jira Ticket {tool_result.get('key')}",
                        summary=tool_result.get("summary", ""),
                        details=tool_result,
                    ))

            elif tool_name == "payments_get_pending":
                working_memory["pending_payments"] = tool_result
                if isinstance(tool_result, dict):
                    cnt = tool_result.get("total_pending_count", 0)
                    vol = tool_result.get("total_pending_volume", 0.0)
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="payments",
                        title="Pending Payments Telemetry",
                        summary=f"{cnt} pending payments identified across gateways totaling ${vol:,.2f} USD.",
                        details=tool_result,
                    ))

            elif tool_name == "payments_compare_providers":
                working_memory["comparison"] = tool_result
                if isinstance(tool_result, dict):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="payments",
                        title="Cross-Gateway Comparative Analysis",
                        summary=tool_result.get("analysis_finding", "Provider comparison generated"),
                        details=tool_result,
                    ))

            elif tool_name == "payments_get_overview":
                working_memory["overview"] = tool_result
                if isinstance(tool_result, dict):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="payments",
                        title="Financial Operations Overview",
                        summary=f"Total volume ${tool_result.get('total_volume', 0):,.2f} across {tool_result.get('total_transactions', 0)} transactions.",
                        details=tool_result,
                    ))

            elif tool_name == "stripe_get_payment":
                working_memory["stripe_payment"] = tool_result
                if isinstance(tool_result, dict):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="stripe",
                        title=f"Stripe Payment {tool_result.get('id')}",
                        summary=f"Customer: {tool_result.get('customer')} | Status: {tool_result.get('status')} (${tool_result.get('amount', 0):,.2f})",
                        details=tool_result,
                    ))

            elif tool_name == "stripe_list_payments":
                working_memory["stripe_payments"] = tool_result
                if isinstance(tool_result, list):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="stripe",
                        title=f"Stripe Payments Ledger",
                        summary=f"Retrieved {len(tool_result)} payments from Stripe gateway.",
                        details={"payments": tool_result},
                    ))


            elif tool_name == "notion_read_policy_page":
                working_memory["notion_policy"] = tool_result
                if isinstance(tool_result, dict):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="notion",
                        title=f"Notion Policy: {tool_result.get('title')}",
                        summary=tool_result.get("content", "")[:200],
                        details=tool_result,
                    ))

            elif tool_name == "paypal_get_order":
                working_memory["paypal_order"] = tool_result
                if isinstance(tool_result, dict):
                    oid = tool_result.get("internal_order_id") or tool_result.get("id")
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="paypal",
                        title=f"PayPal Order {oid}",
                        summary=f"Customer: {tool_result.get('customer')} | Status: {tool_result.get('order_status') or tool_result.get('status')}",
                        details=tool_result,
                    ))

            elif tool_name == "paypal_get_incident_evidence":
                working_memory["paypal_evidence"] = tool_result
                if isinstance(tool_result, dict):
                    failed_count = tool_result.get("total_failed_capture_attempts", 0)
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="paypal",
                        title="PayPal Gateway Telemetry",
                        summary=f"{failed_count} failed capture attempts on checkout-v2 with HTTP 422 ORDER_NOT_APPROVED.",
                        details=tool_result,
                    ))

            elif tool_name == "gmail_search_messages":
                working_memory["gmail_messages"] = tool_result
                if isinstance(tool_result, list):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="gmail",
                        title="Customer Support Inquiries",
                        summary=f"{len(tool_result)} email threads retrieved matching query.",
                        details={"messages": tool_result},
                    ))

            elif tool_name == "slack_read_channel":
                working_memory["slack_alerts"] = tool_result
                if isinstance(tool_result, list):
                    evidence_items.append(EvidenceItem(
                        id=f"ev-{uuid.uuid4().hex[:6]}",
                        system="slack",
                        title=f"Slack #{tool_args.get('channel_name')}",
                        summary=f"Retrieved {len(tool_result)} messages from operational channel.",
                        details={"messages": tool_result},
                    ))
            else:
                working_memory[tool_name] = tool_result

        # Synthesis
        final_text = ""
        if final_decision and final_decision.final_answer:
            final_text = final_decision.final_answer
        else:
            final_text = "Investigation complete. Evidence gathered."

        if approvals:
            response_type = ResponseType.ACTION_PROPOSAL
            final_text += (
                "\n\n#### 🛡️ Action Center: Staged For Your Approval\n"
                "I have prepared an official action requiring your explicit authorization before execution. "
                "Please review and approve in the Action Center card."
            )
        else:
            response_type = ResponseType.READ_ONLY

        response_msg = AgentMessage(
            role="assistant",
            content=final_text,
            response_type=response_type,
            activities=activities,
            evidence=evidence_items,
            actions=approvals,
            approvals=approvals,
        )

        session.messages.append(AgentMessage(role="user", content=user_input))
        session.messages.append(response_msg)
        session.accumulated_evidence.extend(evidence_items)
        if approvals:
            session.pending_approvals.extend(approvals)
        session.updated_at = datetime.now(timezone.utc).isoformat()

        # Persist session to disk
        self.session_store.save(session)

        return response_msg
