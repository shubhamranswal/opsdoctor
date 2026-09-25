"""FastAPI entry point for OpsDoctor Web Product."""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.web.routes.agent import router as agent_router
from apps.web.routes.approvals import router as approvals_router
from apps.web.routes.systems import router as systems_router
from apps.web.routes.timeline import router as timeline_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="OpsDoctor - AI Business Operations Agent",
    description="Autonomous cross-system business operations investigation agent powered by Swytchcode.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(agent_router)
app.include_router(approvals_router)
app.include_router(systems_router)
app.include_router(timeline_router)

# Mount static assets if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "OpsDoctor API is running. Static frontend not yet compiled."}


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "opsdoctor", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.web.main:app", host="127.0.0.1", port=8000, reload=True)
