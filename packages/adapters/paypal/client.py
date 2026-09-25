"""Swytchcode execution client for PayPal with authorization-header override."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .auth import PayPalSandboxTokenManager
from .exceptions import (
    MalformedResponseError,
    PayPalAPIError,
    SwytchcodeExecutionError,
)


def _find_swytchcode_bin() -> str:
    """Locate the Swytchcode CLI binary."""
    # 1. Explicit env var
    env_bin = os.getenv("SWYTCHCODE_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin

    # 2. Standard Windows default install location
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        win_path = Path(local_app_data) / "Programs" / "swytchcode" / "bin" / "swytchcode.exe"
        if win_path.exists():
            return str(win_path)

    # 3. In PATH
    which_bin = shutil.which("swytchcode") or shutil.which("swy")
    if which_bin:
        return which_bin

    # Fallback to name in PATH
    return "swytchcode"


class PayPalSwytchcodeClient:
    """Delegates PayPal tool execution to Swytchcode with transparent auth injection."""

    def __init__(
        self,
        token_manager: Optional[PayPalSandboxTokenManager] = None,
        workspace_dir: Optional[str] = None,
        swytchcode_bin: Optional[str] = None,
    ):
        self.token_manager = token_manager or PayPalSandboxTokenManager()
        self.workspace_dir = workspace_dir or str(Path(__file__).resolve().parents[3])
        self.swytchcode_bin = swytchcode_bin or _find_swytchcode_bin()

    def execute(
        self,
        canonical_id: str,
        args: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a PayPal canonical method via Swytchcode."""
        payload_args = dict(args or {})

        # Obtain access token from token manager (unless in dry-run with mock token)
        if "Authorization" not in payload_args:
            token = self.token_manager.get_access_token()
            payload_args["Authorization"] = f"Bearer {token}"

        result = self._run_swytchcode(canonical_id, payload_args, dry_run=dry_run)

        # Handle 401 Unauthorized by retrying once with an invalidated/refreshed token
        if not dry_run and result.get("status_code") == 401:
            self.token_manager.invalidate_token()
            refreshed_token = self.token_manager.get_access_token()
            payload_args["Authorization"] = f"Bearer {refreshed_token}"
            result = self._run_swytchcode(canonical_id, payload_args, dry_run=False)

        # In dry run, return the planned request data
        if dry_run:
            return result

        # Check for API-level errors
        status_code = result.get("status_code", 200)
        if status_code >= 400:
            error_data = result.get("data", {})
            message = error_data.get("message") or error_data.get("error_description") or f"HTTP {status_code}"
            raise PayPalAPIError(status_code=status_code, message=message, details=error_data)

        return result.get("data", {})

    def _run_swytchcode(
        self,
        canonical_id: str,
        args: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Invoke Swytchcode CLI via subprocess with JSON stdin."""
        cmd = [self.swytchcode_bin, "exec"]
        if dry_run:
            cmd.append("--dry-run")
        else:
            cmd.append("--json")

        stdin_payload = json.dumps({"tool": canonical_id, "args": args})

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.workspace_dir,
                env=os.environ.copy(),
            )
            stdout, stderr = process.communicate(input=stdin_payload, timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            raise SwytchcodeExecutionError("Swytchcode execution timed out after 30 seconds.") from None
        except Exception as e:
            raise SwytchcodeExecutionError(f"Failed to spawn Swytchcode process: {e}") from e

        if process.returncode != 0:
            # Parse structured JSON error from stderr if available
            parsed_err: Dict[str, Any] = {}
            for line in stderr.splitlines():
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        parsed_err = json.loads(line)
                        break
                    except Exception:
                        pass

            err_msg = parsed_err.get("error") or stderr.strip() or f"Process exited with code {process.returncode}"
            raise SwytchcodeExecutionError(
                f"Swytchcode execution failed for {canonical_id}: {err_msg}",
                details={"returncode": process.returncode, "stderr": stderr, "parsed_error": parsed_err},
            )

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            raise MalformedResponseError(
                f"Failed to decode Swytchcode output as JSON: {stdout.strip()[:200]}"
            ) from e
