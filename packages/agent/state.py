"""Data models and state structures for OpsDoctor agent."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepType(str, Enum):
    UNDERSTANDING = "understanding"
    TOOL_SELECTION = "tool_selection"
    TOOL_EXECUTION = "tool_execution"
    EVIDENCE = "evidence"
    EVALUATION = "evaluation"
    DECISION = "decision"
    APPROVAL_REQUIRED = "approval_required"
    ACTION_TAKEN = "action_taken"


class ResponseType(str, Enum):
    """Explicit response types governing whether actions/approvals should be displayed."""
    READ_ONLY = "READ_ONLY"
    ACTION_PROPOSAL = "ACTION_PROPOSAL"
    ACTION_EXECUTING = "ACTION_EXECUTING"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    ACTION_FAILED = "ACTION_FAILED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, ApprovalStatus):
            return self.value.upper() == other.value.upper()
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value.upper())


class ActivityStep(BaseModel):
    id: str
    step_type: StepType
    title: str
    description: str
    system: Optional[str] = None  # jira, paypal, slack, gmail, notion
    data: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EvidenceItem(BaseModel):
    id: str
    system: str  # jira, paypal, slack, gmail, notion
    title: str
    summary: str
    details: Dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ApprovalRequest(BaseModel):
    id: str
    action_type: str  # e.g., "jira_add_comment", "jira_update_issue", "slack_post_message"
    system: str  # "jira", "slack"
    target: str  # e.g., "KAN-4", "#ops-incidents"
    title: str
    explanation: str
    proposed_payload: Dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    executed_at: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class AgentMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    response_type: ResponseType = ResponseType.READ_ONLY
    activities: List[ActivityStep] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    actions: List[ApprovalRequest] = Field(default_factory=list)
    approvals: List[ApprovalRequest] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvestigationSession(BaseModel):
    session_id: str
    title: str
    messages: List[AgentMessage] = Field(default_factory=list)
    accumulated_evidence: List[EvidenceItem] = Field(default_factory=list)
    pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
