"""Base Swytchcode execution client for OpsDoctor adapters."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


def find_swytchcode_bin() -> str:
    """Locate the Swytchcode CLI binary."""
    env_bin = os.getenv("SWYTCHCODE_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin

    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        win_path = Path(local_app_data) / "Programs" / "swytchcode" / "bin" / "swytchcode.exe"
        if win_path.exists():
            return str(win_path)

    which_bin = shutil.which("swytchcode") or shutil.which("swy")
    if which_bin:
        return which_bin

    return "swytchcode"


class BaseSwytchcodeClient:
    """Base class for executing Swytchcode tools with JSON I/O and robust output parsing."""

    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        swytchcode_bin: Optional[str] = None,
    ):
        self.workspace_dir = workspace_dir or str(Path(__file__).resolve().parents[2])
        self.swytchcode_bin = swytchcode_bin or find_swytchcode_bin()

    def execute(
        self,
        canonical_id: str,
        args: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Execute a canonical Swytchcode method via subprocess."""
        payload_args = dict(args or {})
        if canonical_id.startswith("stripe.") and "Authorization" not in payload_args:
            stripe_key = os.getenv("STRIPE_API_KEY")
            if stripe_key:
                payload_args["Authorization"] = f"Bearer {stripe_key}"

        cmd = [self.swytchcode_bin, "exec", "--json"]
        stdin_payload = json.dumps({"tool": canonical_id, "args": payload_args})

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
            stdout, stderr = process.communicate(input=stdin_payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError(f"Swytchcode execution timed out after {timeout} seconds for {canonical_id}") from None
        except Exception as e:
            raise RuntimeError(f"Failed to spawn Swytchcode process: {e}") from e

        if process.returncode != 0:
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
            raise RuntimeError(f"Swytchcode execution failed for {canonical_id}: {err_msg}")

        # Extract JSON from stdout (ignoring any CLI banner / log lines)
        s_idx = stdout.find("{")
        e_idx = stdout.rfind("}")
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            try:
                result = json.loads(stdout[s_idx : e_idx + 1])
                status_code = result.get("status_code", 200)
                if status_code >= 400:
                    err_data = result.get("data", {})
                    raise RuntimeError(f"Swytchcode API error (HTTP {status_code}): {err_data}")
                return result.get("data", result)
            except json.JSONDecodeError as err:
                raise RuntimeError(f"Failed to decode Swytchcode output as JSON: {stdout[:200]}") from err

        raise RuntimeError(f"No JSON object found in Swytchcode stdout: {stdout[:200]}")
