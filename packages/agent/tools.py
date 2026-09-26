"""Tool definitions and Swytchcode bindings for OpsDoctor agent."""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.adapters.jira import JiraSwytchcodeClient
from packages.adapters.paypal import PayPalSwytchcodeClient
from packages.adapters.slack import SlackSwytchcodeClient
from packages.adapters.gmail import GmailSwytchcodeClient
from packages.adapters.notion import NotionSwytchcodeClient
from packages.adapters.payments.manager import UnifiedPaymentManager
from packages.domain.payment import PaymentStatus


class ToolParam(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    system: str  # "payments", "paypal", "stripe", "jira", "slack", "gmail", "notion"
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
        self.payment_manager = UnifiedPaymentManager()
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
        try:
            return handler(**kwargs)
        except Exception as e:
            return {"error": str(e), "tool": name, "status": "failed"}

    def get_diagnostic_inventory(self) -> List[Dict[str, Any]]:
        """Return diagnostic inventory of all registered tools and their agent exposure metadata."""
        inventory = []
        for tool in self.list_tools():
            inventory.append({
                "name": tool.name,
                "system": tool.system,
                "type": "ACTION" if tool.is_consequential else "READ",
                "is_consequential": tool.is_consequential,
                "requires_approval": tool.is_consequential,
                "registered": True,
                "exposed_to_agent": True,
                "description": tool.description,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                        "default": p.default,
                    }
                    for p in tool.parameters
                ],
            })
        return inventory

    def _register_default_tools(self):
        # 1. Unified Payment Domain Tools (READ)
        self.register(
            ToolDefinition(
                name="payments_get_pending",
                description="Retrieve current pending payment transactions awaiting clearance or settlement across connected payment gateways (PayPal, Stripe). Use this when the user asks about pending payments, unsettled transactions, transactions requiring action, or pending volume. Do NOT use this for completed, refunded, or failed payment inquiries (use payments_get_failed). This is READ-ONLY and does not mutate payment state. Touches the payments domain.",
                system="payments",
                parameters=[
                    ToolParam(name="provider", type="string", description="Optional provider filter ('paypal' or 'stripe')", required=False, default=None)
                ],
                is_consequential=False,
            ),
            self._handle_payments_get_pending,
        )

        self.register(
            ToolDefinition(
                name="payments_get_failed",
                description="Retrieve failed and declined payment transactions, error codes, and capture failure records across connected payment gateways (PayPal, Stripe). Use this when the user asks about payment failures, checkout drop-offs, declined cards, or gateway error spikes. Do NOT use this for pending or successful transaction questions. This is READ-ONLY and does not mutate payment state. Touches the payments domain.",
                system="payments",
                parameters=[
                    ToolParam(name="provider", type="string", description="Optional provider filter ('paypal' or 'stripe')", required=False, default=None)
                ],
                is_consequential=False,
            ),
            self._handle_payments_get_failed,
        )

        self.register(
            ToolDefinition(
                name="payments_compare_providers",
                description="Perform comparative side-by-side performance analysis between connected payment gateways (PayPal and Stripe), evaluating failure rates, transaction volumes, and gateway health. Use this when the user asks to compare providers/gateways, asks which gateway has more failures or higher failure rates, or asks for provider breakdown comparisons. Do NOT use this for single-transaction lookups. This is READ-ONLY and does not mutate payment state. Touches the payments domain.",
                system="payments",
                parameters=[],
                is_consequential=False,
            ),
            self._handle_payments_compare_providers,
        )

        self.register(
            ToolDefinition(
                name="payments_get_overview",
                description="Retrieve unified executive financial summary and high-level health metrics across all active payment gateways, including total volume, transaction counts, and settlement rates. Use this when the user requests an overall payments overview, general operations health, or financial telemetry summary. Do NOT use this when specific transaction-level or gateway-comparison details are requested. This is READ-ONLY and does not mutate payment state. Touches the payments domain.",
                system="payments",
                parameters=[],
                is_consequential=False,
            ),
            self._handle_payments_get_overview,
        )

        # 2. Stripe Specific Tools (READ)
        self.register(
            ToolDefinition(
                name="stripe_get_payment",
                description="Retrieve complete object details, customer metadata, and lifecycle status for a specific Stripe PaymentIntent by its ID (e.g., pi_...). Use this when investigating a specific Stripe transaction or looking up a PaymentIntent ID mentioned by the user or discovered in evidence. Do NOT use for PayPal orders or general provider listings. REQUIRED: payment_id (string, e.g. pi_...). This is READ-ONLY and does not mutate payment state. Touches the Stripe gateway.",
                system="stripe",
                parameters=[
                    ToolParam(name="payment_id", type="string", description="Stripe PaymentIntent ID (e.g. pi_...)")
                ],
                is_consequential=False,
            ),
            self._handle_stripe_get_payment,
        )

        self.register(
            ToolDefinition(
                name="stripe_list_payments",
                description="List recent Stripe payment transactions filtered optionally by status (succeeded, pending, failed) from the connected Stripe account. Use this when inspecting recent Stripe transactions or locating transactions for a specific Stripe customer. Do NOT use for PayPal queries or cross-provider comparisons. This is READ-ONLY and does not mutate payment state. Touches the Stripe gateway.",
                system="stripe",
                parameters=[
                    ToolParam(name="status", type="string", description="Optional status filter ('succeeded', 'pending', 'failed')", required=False, default=None),
                    ToolParam(name="limit", type="integer", description="Max transactions to return (default 20)", required=False, default=20),
                ],
                is_consequential=False,
            ),
            self._handle_stripe_list_payments,
        )

        # 3. PayPal Specific Tools (READ)
        self.register(
            ToolDefinition(
                name="paypal_get_incident_evidence",
                description="Retrieve PayPal checkout telemetry, failed capture attempts, and transaction error records for a specific payment flow. Use this when investigating checkout failures, HTTP 422 capture errors, or evaluating incident telemetry. Do NOT use for Stripe-specific inquiries. This is READ-ONLY and does not mutate payment state. Touches the PayPal sandbox integration.",
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
                description="Retrieve detailed status, purchase units, and customer information for a specific PayPal order by PayPal order ID or internal order reference (ORD-...). Use this when investigating a specific PayPal order. Do NOT use for Stripe PaymentIntents. REQUIRED: order_id (string). This is READ-ONLY and does not mutate payment state. Touches the PayPal integration.",
                system="paypal",
                parameters=[
                    ToolParam(name="order_id", type="string", description="PayPal Order ID (e.g. 1LL009468F308113M) or internal custom ID (ORD-...)")
                ],
                is_consequential=False,
            ),
            self._handle_paypal_get_order,
        )

        # 4. Jira Tools (READ & ACTION)
        self.register(
            ToolDefinition(
                name="jira_get_issue",
                description="Retrieve full issue fields, summary, status, description, priority, and reporter for a specific Jira ticket (e.g., KAN-4, KAN-1). Use this when the user asks about an issue, ticket, or incident tracking item, or during incident correlation. Do NOT use for payment telemetry lookups. REQUIRED: issue_key (string). This is READ-ONLY and does not mutate Jira state. Touches the Jira integration.",
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
                description="Search Jira issues using JQL (Jira Query Language) to locate tickets by project, status, label, or summary text. Use this when searching for unresolved issues, incident tickets, or tickets matching criteria. Do NOT use when a specific issue key is already known (use jira_get_issue). REQUIRED: jql (string). This is READ-ONLY and does not mutate Jira state. Touches the Jira integration.",
                system="jira",
                parameters=[
                    ToolParam(name="jql", type="string", description="JQL search expression (e.g. 'project = KAN order by created desc')")
                ],
                is_consequential=False,
            ),
            self._handle_jira_search_issues,
        )

        self.register(
            ToolDefinition(
                name="jira_add_comment",
                description="Add an official comment or investigation findings to an existing Jira issue. This MUTATES Jira state. Use this ONLY after preparing an explicit action proposal and receiving operator approval. Do NOT invoke for read-only ticket lookups or inquiries. REQUIRED: issue_key (string), comment_text (string). Touches the Jira integration.",
                system="jira",
                parameters=[
                    ToolParam(name="issue_key", type="string", description="The Jira issue key (e.g. KAN-4)"),
                    ToolParam(name="comment_text", type="string", description="Plain text comment content formatted professionally without markdown asterisks")
                ],
                is_consequential=True,
            ),
            self._handle_jira_add_comment,
        )

        self.register(
            ToolDefinition(
                name="jira_update_issue",
                description="Update summary, description, or field values on an existing Jira issue. This MUTATES Jira state. Use this ONLY after preparing an explicit action proposal and receiving operator approval. Do NOT invoke for read-only inquiries. REQUIRED: issue_key (string). Touches the Jira integration.",
                system="jira",
                parameters=[
                    ToolParam(name="issue_key", type="string", description="The Jira issue key (e.g. KAN-4)"),
                    ToolParam(name="summary", type="string", description="Optional new summary", required=False),
                ],
                is_consequential=True,
            ),
            self._handle_jira_update_issue,
        )

        # 5. Slack Tools (READ & ACTION)
        self.register(
            ToolDefinition(
                name="slack_list_channels",
                description="List all available public and private operational channels in the AcmeFlow Operations Slack workspace. Use this when discovering channels or checking where alerts/incidents are posted. Do NOT use for reading message history or posting messages. This is READ-ONLY and does not mutate Slack state. Touches the Slack integration.",
                system="slack",
                parameters=[],
                is_consequential=False,
            ),
            self._handle_slack_list_channels,
        )

        self.register(
            ToolDefinition(
                name="slack_read_channel",
                description="Read recent messages, alerts, and operational discussions from a specified Slack channel (e.g., ops-alerts, ops-incidents, payments). Use this when reviewing incident timelines, deployment notices, or team communications. Do NOT use to post messages. REQUIRED: channel_name (string). This is READ-ONLY and does not mutate Slack state. Touches the Slack integration.",
                system="slack",
                parameters=[
                    ToolParam(name="channel_name", type="string", description="Channel name or ID (e.g. 'ops-alerts', 'payments', 'ops-incidents')"),
                    ToolParam(name="limit", type="integer", description="Number of recent messages to retrieve (default 20)", required=False, default=20)
                ],
                is_consequential=False,
            ),
            self._handle_slack_read_channel,
        )

        self.register(
            ToolDefinition(
                name="slack_post_message",
                description="Post an operational announcement, incident update, or alert to a designated Slack channel. This MUTATES Slack workspace state by publishing an external message. Use this ONLY after preparing an explicit action proposal and receiving operator approval. Do NOT invoke for read-only channel history lookups. REQUIRED: channel_name (string), message (string). Touches the Slack integration.",
                system="slack",
                parameters=[
                    ToolParam(name="channel_name", type="string", description="Target Slack channel name (e.g. 'ops-incidents', 'ops-alerts')"),
                    ToolParam(name="message", type="string", description="Message text to post to the channel")
                ],
                is_consequential=True,
            ),
            self._handle_slack_post_message,
        )

        # 6. Gmail Tools (READ)
        self.register(
            ToolDefinition(
                name="gmail_search_messages",
                description="Search customer support and operational emails in Gmail matching a search query (e.g., customer complaints, order references, billing alerts). Use this when gathering customer impact evidence or checking reported complaints. Do NOT use for reading policy documents or payment telemetry. REQUIRED: query (string). This is READ-ONLY and does not mutate Gmail state. Touches the Gmail integration.",
                system="gmail",
                parameters=[
                    ToolParam(name="query", type="string", description="Search query string (e.g. 'ORD-88219', 'payment failed', 'BrightPath')")
                ],
                is_consequential=False,
            ),
            self._handle_gmail_search_messages,
        )

        self.register(
            ToolDefinition(
                name="gmail_get_message",
                description="Retrieve complete email headers, sender, recipient, subject, and full message body of a specific email by message ID. Use this when inspecting full details of an email discovered via search. Do NOT use for general mailbox searching. REQUIRED: message_id (string). This is READ-ONLY and does not mutate Gmail state. Touches the Gmail integration.",
                system="gmail",
                parameters=[
                    ToolParam(name="message_id", type="string", description="Gmail message ID string")
                ],
                is_consequential=False,
            ),
            self._handle_gmail_get_message,
        )

        # 7. Notion Tools (READ)
        self.register(
            ToolDefinition(
                name="notion_search_policies",
                description="Search the AcmeFlow Operations Notion workspace for policy documents, runbooks, SOPs, and operational guidelines. Use this when the exact policy page title or ID is unknown and needs to be discovered. Do NOT use when the policy page name is already known (use notion_read_policy_page). This is READ-ONLY and does not mutate Notion state. Touches the Notion integration.",
                system="notion",
                parameters=[
                    ToolParam(name="query", type="string", description="Search query for runbooks/policies (e.g. 'Payment', 'Escalation', 'Incident')", required=False, default="")
                ],
                is_consequential=False,
            ),
            self._handle_notion_search_policies,
        )

        self.register(
            ToolDefinition(
                name="notion_read_policy_page",
                description="Retrieve and extract the complete text content and procedures from a specific Notion policy page (e.g., 'Payment Procedures', 'Refund Policy', 'Escalation Rules'). Use this when evaluating operational thresholds, escalation rules, or SOP compliance. Do NOT use for general search across unknown titles. REQUIRED: page_name_or_id (string). This is READ-ONLY and does not mutate Notion state. Touches the Notion integration.",
                system="notion",
                parameters=[
                    ToolParam(name="page_name_or_id", type="string", description="Page title (e.g. 'Payment Procedures') or Notion page ID")
                ],
                is_consequential=False,
            ),
            self._handle_notion_read_policy_page,
        )

    # Handlers: Payments
    def _handle_payments_get_pending(self, provider: Optional[str] = None) -> Dict[str, Any]:
        return self.payment_manager.get_pending_payments(provider_name=provider)

    def _handle_payments_get_failed(self, provider: Optional[str] = None) -> Dict[str, Any]:
        return self.payment_manager.get_failed_payments(provider_name=provider)

    def _handle_payments_compare_providers(self) -> Dict[str, Any]:
        return self.payment_manager.compare_providers()

    def _handle_payments_get_overview(self) -> Dict[str, Any]:
        return self.payment_manager.get_overview().model_dump()

    def _handle_stripe_get_payment(self, payment_id: str) -> Dict[str, Any]:
        p = self.payment_manager.find_transaction(payment_id)
        if p and p.provider == "stripe":
            return p.model_dump()
        stripe_provider = self.payment_manager.get_provider("stripe")
        if stripe_provider:
            tx = stripe_provider.get_transaction(payment_id)
            if tx:
                return tx.model_dump()
        return {"error": f"Stripe payment '{payment_id}' not found"}

    def _handle_stripe_list_payments(self, status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        stripe_provider = self.payment_manager.get_provider("stripe")
        if not stripe_provider:
            return []
        p_status = PaymentStatus(status.lower()) if status else None
        txs = stripe_provider.list_transactions(status=p_status, limit=limit)
        return [t.model_dump() for t in txs]

    # Handlers: Jira
    def _handle_jira_get_issue(self, issue_key: str) -> Dict[str, Any]:
        data = self.jira.get_issue(issue_key) or {}
        fields = data.get("fields") or {}
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}
        project = fields.get("project") or {}
        return {
            "key": data.get("key", issue_key),
            "summary": fields.get("summary"),
            "status": status.get("name") if isinstance(status, dict) else str(status),
            "priority": priority.get("name") if isinstance(priority, dict) else (str(priority) if priority else "Normal"),
            "labels": fields.get("labels") or [],
            "created": fields.get("created"),
            "description": str(fields.get("description")) if fields.get("description") else "",
            "project": project.get("name") if isinstance(project, dict) else str(project),
        }

    def _handle_jira_search_issues(self, jql: str) -> List[Dict[str, Any]]:
        raw_issues = self.jira.search_issues(jql)
        results = []
        for issue in raw_issues:
            issue_id = issue.get("id")
            if issue_id:
                try:
                    full = self.jira.get_issue(issue_id) or {}
                    fields = full.get("fields") or {}
                    status = fields.get("status") or {}
                    results.append({
                        "key": full.get("key"),
                        "summary": fields.get("summary"),
                        "status": status.get("name") if isinstance(status, dict) else str(status),
                        "labels": fields.get("labels") or [],
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

    # Handlers: PayPal
    def _handle_paypal_get_incident_evidence(self, flow: str = "checkout-v2") -> Dict[str, Any]:
        manifest_path = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "paypal_orders_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        manifest_path = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "paypal_orders_manifest.json"
        mapped_paypal_id = order_id
        meta: Dict[str, Any] = {}
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                for o in manifest.get("orders", []):
                    if o.get("order_id") == order_id or o.get("paypal_order_id") == order_id:
                        mapped_paypal_id = o.get("paypal_order_id", order_id)
                        meta = o
                        break
            except Exception:
                pass
        try:
            live = self.paypal.execute("orders.checkout.orders.get", {"id": mapped_paypal_id})
            if isinstance(live, dict) and not live.get("error"):
                res = {**meta, **live, "paypal_order_id": mapped_paypal_id}
                if meta.get("order_id"):
                    res["internal_order_id"] = meta["order_id"]
                return res
        except Exception as e:
            if meta:
                return {**meta, "live_query_note": f"Retrieved from local manifest fixture (live query returned {e})"}
            raise e
        return meta or self.paypal.execute("orders.checkout.orders.get", {"id": mapped_paypal_id})

    # Handlers: Slack
    def _resolve_channel_id(self, channel_name: str) -> str:
        clean_name = channel_name.lstrip("#").lower().strip()
        ch_map = {
            "all-acmeflow-operations": "C0C43R6TS15",
            "general": "C0C4D0KH9C3",
            "ops-alerts": "C0C4E4BERRB",
            "ops-incidents": "C0C4D0G4H1R",
            "payments": "C0C4D0HSLF5",
            "social": "C0C4K2WG6LS",
            "new-channel": "C0C4E48431T",
        }
        if clean_name in ch_map:
            return ch_map[clean_name]
        if clean_name.startswith("c0") or (clean_name.startswith("c") and len(clean_name) > 8):
            return channel_name
        # Fallback to dynamic lookup from live Slack workspace
        try:
            for ch in self.slack.list_channels():
                if ch.get("name", "").lower() == clean_name:
                    return ch.get("id")
        except Exception:
            pass
        return channel_name

    def _handle_slack_list_channels(self) -> List[Dict[str, Any]]:
        channels = self.slack.list_channels()
        return [{"id": c.get("id"), "name": c.get("name"), "topic": c.get("topic", {}).get("value")} for c in channels]

    def _handle_slack_read_channel(self, channel_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        cid = self._resolve_channel_id(channel_name)
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
        cid = self._resolve_channel_id(channel_name)
        res = self.slack.post_message(channel_id=cid, text=message)
        ts_val = res.get("ts")
        return {"status": "success", "channel": channel_name, "ts": ts_val, "id": ts_val}

    # Handlers: Gmail
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

    # Handlers: Notion
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
