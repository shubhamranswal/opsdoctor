"""Persistent Session Storage for OpsDoctor Agent."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from packages.agent.state import InvestigationSession

logger = logging.getLogger("opsdoctor.storage")

DEFAULT_STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "sessions"


class SessionStore:
    """File-backed persistent storage for investigation sessions."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, InvestigationSession] = {}

    def _file_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return self.storage_dir / f"{safe_id}.json"

    def get(self, session_id: str) -> Optional[InvestigationSession]:
        if session_id in self._cache:
            return self._cache[session_id]

        file_path = self._file_path(session_id)
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                session = InvestigationSession.model_validate_json(content)
                self._cache[session_id] = session
                return session
            except Exception as e:
                logger.error("Failed to load session %s from %s: %s", session_id, file_path, e)

        return None

    def save(self, session: InvestigationSession) -> None:
        self._cache[session.session_id] = session
        file_path = self._file_path(session.session_id)
        try:
            temp_path = file_path.with_suffix(".tmp")
            temp_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(file_path)
        except Exception as e:
            logger.error("Failed to persist session %s: %s", session.session_id, e)

    def list_sessions(self) -> List[str]:
        sessions = []
        for p in self.storage_dir.glob("*.json"):
            sessions.append(p.stem)
        return sessions

    def delete(self, session_id: str) -> bool:
        self._cache.pop(session_id, None)
        file_path = self._file_path(session_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False
