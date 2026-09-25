"""Agent interaction and streaming routes."""

import asyncio
import json
import queue
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from packages.agent.orchestrator import OpsDoctorOrchestrator
from packages.agent.state import ActivityStep, AgentMessage
from apps.web.routes.approvals import get_approval_manager

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Shared orchestrator instance
_orchestrator: Optional[OpsDoctorOrchestrator] = None

def get_orchestrator() -> OpsDoctorOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OpsDoctorOrchestrator(approval_manager=get_approval_manager())
    return _orchestrator


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


@router.post("/chat", response_model=AgentMessage)
def chat_turn(req: ChatRequest):
    """Run an agent turn synchronously and return the structured response."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    orchestrator = get_orchestrator()
    sid = req.session_id or "default-session"
    return orchestrator.run_turn(session_id=sid, user_input=req.message)


@router.get("/session/{session_id}")
def get_session(session_id: str):
    """Retrieve full session state, history, and accumulated evidence."""
    orchestrator = get_orchestrator()
    session = orchestrator.get_or_create_session(session_id)
    return session


@router.get("/stream")
async def stream_turn(session_id: str, message: str):
    """Stream live activity steps and execution events using Server-Sent Events (SSE)."""
    orchestrator = get_orchestrator()
    event_queue: queue.Queue = queue.Queue()

    def callback(step: ActivityStep):
        event_queue.put({"type": "activity", "data": step.model_dump()})

    async def event_generator():
        # Run orchestrator in a background thread so we can yield SSE events in real-time
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            None,
            orchestrator.run_turn,
            session_id,
            message,
            callback,
        )

        while not future.done():
            while not event_queue.empty():
                evt = event_queue.get_nowait()
                yield f"data: {json.dumps(evt)}\n\n"
            await asyncio.sleep(0.05)

        # Catch remaining events
        while not event_queue.empty():
            evt = event_queue.get_nowait()
            yield f"data: {json.dumps(evt)}\n\n"

        try:
            final_msg: AgentMessage = await future
            yield f"data: {json.dumps({'type': 'final', 'data': final_msg.model_dump()})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
