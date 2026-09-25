"""Approval manager for consequential agent actions in OpsDoctor."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from packages.agent.state import ApprovalRequest, ApprovalStatus
from packages.agent.tools import ToolRegistry


class ApprovalManager:
    """Manages pending and executed approvals for consequential actions."""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self.tool_registry = tool_registry or ToolRegistry()
        self._approvals: Dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        action_type: str,
        system: str,
        target: str,
        title: str,
        explanation: str,
        proposed_payload: Dict[str, Any],
    ) -> ApprovalRequest:
        """Create a new pending approval request."""
        req_id = f"appr-{uuid.uuid4().hex[:8]}"
        req = ApprovalRequest(
            id=req_id,
            action_type=action_type,
            system=system,
            target=target,
            title=title,
            explanation=explanation,
            proposed_payload=proposed_payload,
            status=ApprovalStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._approvals[req_id] = req
        return req

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        return self._approvals.get(approval_id)

    def list_requests(self, status: Optional[ApprovalStatus] = None) -> List[ApprovalRequest]:
        if status:
            return [a for a in self._approvals.values() if a.status == status]
        return list(self._approvals.values())

    def approve_and_execute(self, approval_id: str) -> ApprovalRequest:
        """Approve a request and execute the consequential action via Swytchcode."""
        req = self._approvals.get(approval_id)
        if not req:
            raise ValueError(f"Approval request {approval_id} not found.")

        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request {approval_id} is already in status {req.status}.")

        req.status = ApprovalStatus.APPROVED
        try:
            result = self.tool_registry.execute_tool(req.action_type, **req.proposed_payload)
            req.status = ApprovalStatus.EXECUTED
            req.executed_at = datetime.now(timezone.utc).isoformat()
            req.execution_result = result
        except Exception as e:
            req.status = ApprovalStatus.PENDING
            raise RuntimeError(f"Failed to execute approved action {req.action_type}: {e}") from e

        return req

    def reject(self, approval_id: str, reason: str = "") -> ApprovalRequest:
        """Reject a pending approval request."""
        req = self._approvals.get(approval_id)
        if not req:
            raise ValueError(f"Approval request {approval_id} not found.")
        req.status = ApprovalStatus.REJECTED
        req.explanation = f"{req.explanation} [REJECTED: {reason}]" if reason else req.explanation
        return req
