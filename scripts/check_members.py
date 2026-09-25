import json
import subprocess
from pathlib import Path

swy = r"C:\Users\shubh\AppData\Local\Programs\swytchcode\bin\swytchcode.exe"
channels = {
    "all-acmeflow-operations": "C0C43R6TS15",
    "general": "C0C4D0KH9C3",
    "ops-alerts": "C0C4E4BERRB",
    "ops-incidents": "C0C4D0G4H1R",
    "payments": "C0C4D0HSLF5",
    "social": "C0C4K2WG6LS",
}

for name, cid in channels.items():
    p = subprocess.Popen(
        [swy, "exec", "--json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out, err = p.communicate(json.dumps({"tool": "slack.conversations.info.list", "args": {"channel": cid}}))
    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("{") and "channel" in line:
            try:
                data = json.loads(line)
                ch_info = data.get("data", {}).get("channel", {})
                print(f"#{name:<25} ID: {cid}  is_member: {ch_info.get('is_member')}")
            except Exception as e:
                pass
