"""Tool definitions and Swytchcode bindings for OpsDoctor agent."""

import json
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.adapters.jira import JiraSwytchcodeClient
from packages.adapters.paypal import PayPalSwytchcodeClient
from packages.adapters.slack import SlackSwytchcodeClient
from packages.adapters.gmail import GmailSwytchcodeClient
from packages.adapters.notion import NotionSwytchcodeClient


class ToolParam(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    system: str  # "jira", "paypal", "slack", "gmail", "notion"
    parameters: List[ToolParam]
    is_consequential: bool = False  # If True, requires user approval before execution


class ToolRegistry:
    """Registry managing tool schemas and Swytchcode execution bindings."""

    def __init__(self):
        self.jira = JiraSwytchcodeClient()
        self.paypal = PayPalSwytchcodeClient()
        self.slack = SlackSwytchcodeClient()
        self.gmail = GmailSwytchcodeClient()
        self.notion = NotionSwytchcodeClient()
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._register_default_tools()

    def register(self, definition: ToolDefinition, handler: Callable[..., Any]):
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def execute_tool(self, name: str, **kwargs) -> Any:
        handler = self._handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**kwargs)

    def _register_default_tools(self):
        # 1. Jira Tools
        self.register(
            ToolDefinition(
                name="jira_get_issue",
                description="Fetch full details of a Jira issue by its key (e.g. KAN-4, KAN-1).",
                system="jira",
                parameters=[
                    ToolParam(name="issue_key", type="string", description="The Jira issue key (e.g. KAN-4)")
                ],
                is_consequential=False,
            ),
            self._handle_jira_get_issue,
        )

        self.register(
            ToolDefinition(
                name="jira_search_issues",
                description="Search Jira issues using JQL (e.g. 'project = KAN', 'labels = INC-2026-042').",
                system="jira",
                parameters=[
                    ToolParam(name="jql", type="string", description="JQL search expression")
                ],
                is_consequential=False,
            ),
            self._handle_jira_search_issues,
        )

        self.register(
            ToolDefinition(
                name="jira_add_comment",
                description="Add an investigation finding or escalation comment to a Jira issue.",
                system="jira",
                parameters=[
                    ToolParam(name="issue_key", type="string", description="The Jira issue key (e.g. KAN-4)"),
                    ToolParam(name="comment_text", type="string", description="Markdown/Plain text comment content")
                ],
                is_consequential=True,
            ),
            self._handle_jira_add_comment,
        )

        self.register(
            ToolDefinition(
                name="jira_update_issue",
                description="Update issue fields or state on a Jira issue.",
                system="jira",
                parameters=[
                    ToolParam(name="issue_key", type="string", description="The Jira issue key (e.g. KAN-4)"),
                    ToolParam(name="summary", type="string", description="Optional new summary", required=False),
                ],
                is_consequential=True,
            ),
            self._handle_jira_update_issue,
        )

        # 2. PayPal Tools
        self.register(
            ToolDefinition(
                name="paypal_get_incident_evidence",
                description="Retrieve PayPal Sandbox orders, transaction statuses, and capture failure records.",
                system="paypal",
                parameters=[
                    ToolParam(name="flow", type="string", description="Payment flow name (e.g. 'checkout-v2')", required=False, default="checkout-v2")
                ],
                is_consequential=False,
            ),
            self._handle_paypal_get_incident_evidence,
        )

        self.register(
            ToolDefinition(
                name="paypal_get_order",
                description="Get detailed status and purchase units of a specific PayPal order by PayPal ID or Custom ID.",
                system="paypal",
                parameters=[
                    ToolParam(name="order_id", type="string", description="PayPal Order ID (e.g. 1LL009468F308113M) or custom ID")
                ],
                is_consequential=False,
            ),
            self._handle_paypal_get_order,
        )

        # 3. Slack Tools
        self.register(
            ToolDefinition(
                name="slack_list_channels",
                description="List available operational Slack channels in AcmeFlow Operations.",
                system="slack",
                parameters=[],
                is_consequential=False,
            ),
            self._handle_slack_list_channels,
        )

        self.register(
            ToolDefinition(
                name="slack_read_channel",
                description="Read recent operational discussions, alerts, and deployment logs from a Slack channel (e.g. 'ops-alerts', 'payments', 'ops-incidents').",
                system="slack",
                parameters=[
                    ToolParam(name="channel_name", type="string", description="Channel name or ID (e.g. 'ops-alerts', 'payments', 'ops-incidents')"),
                    ToolParam(name="limit", type="integer", description="Number of recent messages to retrieve", required=False, default=20)
                ],
                is_consequential=False,
            ),
            self._handle_slack_read_channel,
        )

        self.register(
            ToolDefinition(
                name="slack_post_message",
                description="Post an incident status update or alert to a Slack channel.",
                system="slack",
                parameters=[
                    ToolParam(name="channel_name", type="string", description="Channel name (e.g. 'ops-incidents')"),
                    ToolParam(name="message", type="string", description="Message text to post")
                ],
                is_consequential=True,
            ),
            self._handle_slack_post_message,
        )

        # 4. Gmail Tools
        self.register(
            ToolDefinition(
                name="gmail_search_messages",
                description="Search AcmeFlow emails for customer complaints, billing alerts, or incident references.",
                system="gmail",
                parameters=[
                    ToolParam(name="query", type="string", description="Search query (e.g. 'ORD-88219', 'payment failed', 'PayPal')")
                ],
                is_consequential=False,
            ),
            self._handle_gmail_search_messages,
        )

        self.register(
            ToolDefinition(
                name="gmail_get_message",
                description="Retrieve full headers, subject, sender, and body of a specific email by its ID.",
                system="gmail",
                parameters=[
                    ToolParam(name="message_id", type="string", description="Gmail message ID")
                ],
                is_consequential=False,
            ),
            self._handle_gmail_get_message,
        )

        # 5. Notion Tools
        self.register(
            ToolDefinition(
                name="notion_search_policies",
                description="Search AcmeFlow Operations Notion workspace for runbooks, SOPs, and policy documents.",
                system="notion",
                parameters=[
                    ToolParam(name="query", type="string", description="Search query (e.g. 'Payment', 'Escalation', 'Incident')", required=False, default="")
                ],
                is_consequential=False,
            ),
            self._handle_notion_search_policies,
        )

        self.register(
            ToolDefinition(
                name="notion_read_policy_page",
                description="Retrieve and read the full text content and blocks of a specific Notion policy page (e.g. 'Payment Procedures', 'Escalation Rules').",
                system="notion",
                parameters=[
                    ToolParam(name="page_name_or_id", type="string", description="Page title (e.g. 'Payment Procedures') or Notion page ID")
                ],
                is_consequential=False,
            ),
            self._handle_notion_read_policy_page,
        )

    # Handlers
    def _handle_jira_get_issue(self, issue_key: str) -> Dict[str, Any]:
        data = self.jira.get_issue(issue_key)
        fields = data.get("fields", {})
        return {
            "key": data.get("key", issue_key),
            "summary": fields.get("summary"),
            "status": fields.get("status", {}).get("name"),
            "priority": fields.get("priority", {}).get("name"),
            "labels": fields.get("labels", []),
            "created": fields.get("created"),
            "description": fields.get("description"),
            "project": fields.get("project", {}).get("name"),
        }

    def _handle_jira_search_issues(self, jql: str) -> List[Dict[str, Any]]:
        raw_issues = self.jira.search_issues(jql)
        results = []
        for issue in raw_issues:
            # If issue only contains id, fetch key/summary
            issue_id = issue.get("id")
            if issue_id:
                try:
                    full = self.jira.get_issue(issue_id)
                    fields = full.get("fields", {})
                    results.append({
                        "key": full.get("key"),
                        "summary": fields.get("summary"),
                        "status": fields.get("status", {}).get("name"),
                        "labels": fields.get("labels", []),
                    })
                except Exception:
                    results.append(issue)
        return results

    def _handle_jira_add_comment(self, issue_key: str, comment_text: str) -> Dict[str, Any]:
        res = self.jira.add_comment(issue_key, comment_text)
        return {"status": "success", "comment_id": res.get("id"), "issue_key": issue_key}

    def _handle_jira_update_issue(self, issue_key: str, summary: Optional[str] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        if summary:
            fields["summary"] = summary
        res = self.jira.update_issue(issue_key, fields)
        return {"status": "success", "issue_key": issue_key, "updated_fields": list(fields.keys())}

    def _handle_paypal_get_incident_evidence(self, flow: str = "checkout-v2") -> Dict[str, Any]:
        # Reads live from fixture manifest or live orders in sandbox
        import os
        from pathlib import Path
        manifest_path = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "paypal_orders_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # filter for relevant flow
            incident_orders = [o for o in data.get("orders", []) if o.get("phase") == "incident" and (not flow or o.get("flow") == flow)]
            total_failed_captures = sum(len(o.get("capture_attempts", [])) for o in incident_orders)
            return {
                "incident_id": data.get("incident_id"),
                "flow": flow,
                "deployment": data.get("deployment_id"),
                "total_incident_orders": len(incident_orders),
                "total_failed_capture_attempts": total_failed_captures,
                "orders": incident_orders,
            }
        return {"error": "PayPal manifest not found"}

    def _handle_paypal_get_order(self, order_id: str) -> Dict[str, Any]:
        return self.paypal.execute("orders.checkout.orders.get", {"id": order_id})

    def _handle_slack_list_channels(self) -> List[Dict[str, Any]]:
        channels = self.slack.list_channels()
        return [{"id": c.get("id"), "name": c.get("name"), "topic": c.get("topic", {}).get("value")} for c in channels]

    def _handle_slack_read_channel(self, channel_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        # Resolve channel name to ID
        ch_map = {
            "all-acmeflow-operations": "C0C43R6TS15",
            "general": "C0C4D0KH9C3",
            "ops-alerts": "C0C4E4BERRB",
            "ops-incidents": "C0C4D0G4H1R",
            "payments": "C0C4D0HSLF5",
            "social": "C0C4K2WG6LS",
        }
        cid = ch_map.get(channel_name.lstrip("#"), channel_name)
        raw_msgs = self.slack.get_channel_history(channel_id=cid, limit=limit)
        results = []
        for m in raw_msgs:
            results.append({
                "user": m.get("user"),
                "text": m.get("text"),
                "ts": m.get("ts"),
            })
        return results

    def _handle_slack_post_message(self, channel_name: str, message: str) -> Dict[str, Any]:
        ch_map = {
            "all-acmeflow-operations": "C0C43R6TS15",
            "general": "C0C4D0KH9C3",
            "ops-alerts": "C0C4E4BERRB",
            "ops-incidents": "C0C4D0G4H1R",
            "payments": "C0C4D0HSLF5",
            "social": "C0C4K2WG6LS",
        }
        cid = ch_map.get(channel_name.lstrip("#"), channel_name)
        res = self.slack.post_message(channel_id=cid, text=message)
        return {"status": "success", "channel": channel_name, "ts": res.get("ts")}

    def _handle_gmail_search_messages(self, query: str) -> List[Dict[str, Any]]:
        raw_msgs = self.gmail.list_messages(q=query, max_results=10)
        results = []
        for m in raw_msgs:
            mid = m.get("id")
            if mid:
                try:
                    full = self.gmail.get_message(mid)
                    payload = full.get("payload", {})
                    headers = {h.get("name"): h.get("value") for h in payload.get("headers", [])}
                    results.append({
                        "id": mid,
                        "subject": headers.get("Subject"),
                        "from": headers.get("From"),
                        "to": headers.get("To"),
                        "date": headers.get("Date"),
                        "snippet": full.get("snippet"),
                    })
                except Exception:
                    results.append({"id": mid})
        return results

    def _handle_gmail_get_message(self, message_id: str) -> Dict[str, Any]:
        full = self.gmail.get_message(message_id)
        payload = full.get("payload", {})
        headers = {h.get("name"): h.get("value") for h in payload.get("headers", [])}
        return {
            "id": message_id,
            "subject": headers.get("Subject"),
            "from": headers.get("From"),
            "to": headers.get("To"),
            "date": headers.get("Date"),
            "snippet": full.get("snippet"),
        }

    def _handle_notion_search_policies(self, query: str = "") -> List[Dict[str, Any]]:
        results = self.notion.search(query)
        pages = []
        for r in results:
            if r.get("object") == "page":
                props = r.get("properties", {})
                title = "Untitled"
                for p_val in props.values():
                    if isinstance(p_val, dict) and p_val.get("type") == "title":
                        t_list = p_val.get("title", [])
                        if t_list:
                            title = "".join(t.get("plain_text", "") for t in t_list)
                        break
                pages.append({"id": r.get("id"), "title": title, "url": r.get("url")})
        return pages

    def _handle_notion_read_policy_page(self, page_name_or_id: str) -> Dict[str, Any]:
        # Search page ID if a name was passed
        page_id = page_name_or_id
        page_title = page_name_or_id
        if not ("-" in page_name_or_id and len(page_name_or_id) == 36):
            pages = self._handle_notion_search_policies(query=page_name_or_id)
            for p in pages:
                if page_name_or_id.lower() in p["title"].lower():
                    page_id = p["id"]
                    page_title = p["title"]
                    break

        content = self.notion.extract_page_text(page_id)
        return {"page_id": page_id, "title": page_title, "content": content}
