"""Approvals management API routes."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from packages.agent.approvals import ApprovalManager
from packages.agent.state import ApprovalRequest, ApprovalStatus

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

# Shared singleton approval manager
_approval_manager: Optional[ApprovalManager] = None

def get_approval_manager() -> ApprovalManager:
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = ApprovalManager()
    return _approval_manager

def set_approval_manager(mgr: ApprovalManager):
    global _approval_manager
    _approval_manager = mgr


class RejectPayload(BaseModel):
    reason: Optional[str] = "User requested cancellation"


@router.get("", response_model=List[ApprovalRequest])
def list_approvals(status: Optional[str] = None, session_id: Optional[str] = None):
    mgr = get_approval_manager()
    status_filter = None
    if status:
        try:
            status_filter = ApprovalStatus(status.upper())
        except ValueError:
            pass
    return mgr.list_requests(status=status_filter, session_id=session_id)


@router.post("/{approval_id}/approve")
def approve_action(approval_id: str):
    mgr = get_approval_manager()
    try:
        req = mgr.approve_and_execute(approval_id)
        exec_id = "N/A"
        if req.execution_result and isinstance(req.execution_result, dict):
            exec_id = req.execution_result.get("comment_id") or req.execution_result.get("id") or req.id
        return {
            "status": "success",
            "response_type": "ACTION_COMPLETED",
            "message": f"Action {req.action_type} executed successfully on {req.target} via Swytchcode.",
            "execution_id": exec_id,
            "execution_result": req.execution_result,
            "approval": req,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{approval_id}/reject")
def reject_action(approval_id: str, payload: RejectPayload):
    mgr = get_approval_manager()
    try:
        req = mgr.reject(approval_id, reason=payload.reason or "")
        return {
            "status": "rejected",
            "response_type": "ACTION_REJECTED",
            "message": f"Action {req.action_type} was rejected.",
            "approval": req,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
