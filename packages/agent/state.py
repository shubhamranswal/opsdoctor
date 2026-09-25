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


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


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


class AgentMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    activities: List[ActivityStep] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
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
