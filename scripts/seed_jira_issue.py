import json
import subprocess
import sys

swy = r"C:\Users\shubh\AppData\Local\Programs\swytchcode\bin\swytchcode.exe"

def run_swytchcode(tool_id, args):
    p = subprocess.Popen(
        [swy, "exec", "--json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.dumps({"tool": tool_id, "args": args})
    out, err = p.communicate(payload)
    if p.returncode != 0:
        print(f"Error executing {tool_id}: returncode {p.returncode}", file=sys.stderr)
        print(err, file=sys.stderr)
        return None
    s_idx = out.find("{")
    e_idx = out.rfind("}")
    if s_idx != -1 and e_idx != -1:
        try:
            return json.loads(out[s_idx:e_idx+1])
        except Exception as e:
            print(f"Failed to parse JSON: {e}", file=sys.stderr)
            print(out, file=sys.stderr)
            return None
    print("No JSON found in stdout:", out, file=sys.stderr)
    return None

def main():
    print("--- 1. Creating Incident Issue in Jira via Swytchcode ---")
    issue_payload = {
        "body": {
            "fields": {
                "project": {
                    "id": "10001"
                },
                "issuetype": {
                    "id": "10008"
                },
                "summary": "[INC-2026-042] Customer payment failures during checkout-v2 PayPal flow",
                "priority": {
                    "id": "2"
                },
                "labels": [
                    "INC-2026-042",
                    "checkout-v2",
                    "payments",
                    "paypal"
                ],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Incident INC-2026-042 opened following reports of customer payment failures during the checkout-v2 flow."
                                }
                            ]
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Deployment checkout-api-2026.09.25.3 was released shortly before initial customer failure reports and ops alert spikes. Multiple transaction capture failures have been observed in PayPal checkout."
                                }
                            ]
                        },
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Initial operational investigation underway across payment gateways, support tickets, and system logs to assess customer impact and triage."
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    create_res = run_swytchcode("jira.api.issue.create", issue_payload)
    if not create_res:
        print("Failed to create issue.")
        sys.exit(1)

    print("Create issue raw response:", json.dumps(create_res, indent=2))
    issue_data = create_res.get("data", {})
    created_key = issue_data.get("key")
    created_id = issue_data.get("id")
    print(f"Created Issue Key: {created_key} (ID: {created_id})")

    if not created_key:
        print("No issue key returned, cannot verify.")
        sys.exit(1)

    print("\n--- 2. Reading back created issue via Swytchcode ---")
    get_res = run_swytchcode("jira.api.issue.get", {"issueIdOrKey": created_key})
    if not get_res:
        print("Failed to read issue back.")
        sys.exit(1)

    fetched_data = get_res.get("data", {})
    fields = fetched_data.get("fields", {})

    key = fetched_data.get("key")
    summary = fields.get("summary")
    status_obj = fields.get("status", {})
    status_name = status_obj.get("name")
    proj_obj = fields.get("project", {})
    proj_name = proj_obj.get("name")
    proj_key = proj_obj.get("key")
    desc_obj = fields.get("description", {})

    print(f"Verified Issue Key: {key}")
    print(f"Verified Summary: {summary}")
    print(f"Verified Status: {status_name}")
    print(f"Verified Project: {proj_name} ({proj_key})")
    print(f"Verified Description Type: {desc_obj.get('type')}")

    manifest = {
        "incident_id": "INC-2026-042",
        "jira_key": key,
        "jira_id": created_id,
        "summary": summary,
        "status": status_name,
        "project": {
            "id": proj_obj.get("id"),
            "key": proj_key,
            "name": proj_name
        },
        "issue_type": fields.get("issuetype", {}).get("name"),
        "priority": fields.get("priority", {}).get("name"),
        "labels": fields.get("labels", []),
        "created_time": fields.get("created"),
        "url": f"https://acmeflow-ops.atlassian.net/browse/{key}"
    }

    with open("data/fixtures/jira_incident_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\nSuccessfully wrote data/fixtures/jira_incident_manifest.json")

if __name__ == "__main__":
    main()
