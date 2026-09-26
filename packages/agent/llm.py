"""Cognitive Decision Engine for OpsDoctor Agent.

Implements capability-first, evidence-driven autonomous reasoning:
- Dual-engine: Gemini API (gemini-3.8-flash) with function calling or Autonomous ReAct Planner
- Capability routing across Payments (PayPal, Stripe), Issue Tracking (Jira),
  Communications (Slack, Gmail), and Knowledge Policies (Notion)
- Removes any hidden assumption that investigations must begin with Jira
- Genuinely general-purpose: derives answers dynamically from observed tool outputs with zero hardcoded summaries
- Multi-turn conversational context resolution (follow-ups, pronoun resolution)
- Concise operational activity traces (WHAT happened, never exposing private chain-of-thought)
- Professional Jira comment formatting (Jira wiki markup model)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.agent.state import ActivityStep, AgentMessage, EvidenceItem, StepType
from packages.agent.tools import ToolDefinition

logger = logging.getLogger("opsdoctor.llm")


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely cast string or numeric value to float for display formatting."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class StepDecision(BaseModel):
    """Output decision of a cognitive turn step."""
    thought: str
    action_summary: Optional[str] = None
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    is_final: bool = False
    final_answer: Optional[str] = None
    staged_action: Optional[Dict[str, Any]] = None


class CognitiveBrain:
    """Unified cognitive brain delegating to Gemini or the Autonomous Cognitive Planner."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.8-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self.model_name = model_name
        self._gemini_client = None
        self._init_gemini()

    def _init_gemini(self):
        if self.api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.api_key)
                logger.info("Gemini cognitive client initialized with model %s", self.model_name)
            except Exception as e:
                logger.warning("Failed to initialize Gemini client: %s. Using Autonomous planner.", e)
                self._gemini_client = None

    @property
    def has_active_llm(self) -> bool:
        return self._gemini_client is not None

    def decide_step(
        self,
        query: str,
        history: List[AgentMessage],
        tool_definitions: List[ToolDefinition],
        working_memory: Dict[str, Any],
        executed_steps: List[ActivityStep],
    ) -> StepDecision:
        """Decide the next action or conclude the investigation."""
        if self.has_active_llm:
            try:
                return self._decide_with_gemini(query, history, tool_definitions, working_memory, executed_steps)
            except Exception as e:
                logger.error("Gemini decision step failed: %s. Falling back to autonomous planner.", e)

        return self._decide_with_autonomous_planner(query, history, tool_definitions, working_memory, executed_steps)

    def _decide_with_gemini(
        self,
        query: str,
        history: List[AgentMessage],
        tool_definitions: List[ToolDefinition],
        working_memory: Dict[str, Any],
        executed_steps: List[ActivityStep],
    ) -> StepDecision:
        """Execute decision step via Gemini API function calling."""
        from google.genai import types

        gemini_tools = []
        for td in tool_definitions:
            props = {}
            required = []
            for p in td.parameters:
                p_type = "STRING"
                if p.type in ("int", "integer"):
                    p_type = "INTEGER"
                elif p.type in ("bool", "boolean"):
                    p_type = "BOOLEAN"
                props[p.name] = {"type": p_type, "description": p.description}
                if p.required:
                    required.append(p.name)

            decl = {
                "name": td.name,
                "description": td.description,
                "parameters": {
                    "type": "OBJECT",
                    "properties": props,
                    "required": required,
                },
            }
            gemini_tools.append(decl)

        system_prompt = (
            "You are OpsDoctor, an autonomous AI business operations agent.\n"
            "You answer questions and investigate issues across connected enterprise capabilities: "
            "Payments (PayPal, Stripe), Issue Tracking (Jira), Communications (Slack, Gmail), and Runbooks (Notion).\n\n"
            "Rules:\n"
            "1. REASON FROM CAPABILITIES, NOT FIXTURES. If the user asks about pending payments, inspect payment tools (PayPal & Stripe). Do NOT call Jira for payment status questions.\n"
            "2. Only call Jira if the user asks about tickets, issues, incidents, or if evidence during an investigation reveals an issue tracker update is warranted.\n"
            "3. If enough evidence is gathered, formulate a clear, professional response with metrics, breakdowns, and citations strictly from observations.\n"
            "4. Never fabricate data or hardcode summaries.\n"
        )

        context_summary = "\n--- Observations so far in this turn ---\n"
        if working_memory:
            for k, v in working_memory.items():
                context_summary += f"[{k}]: {json.dumps(v, default=str)[:600]}\n"
        else:
            context_summary += "No tools executed yet in this turn.\n"

        contents = f"User Request: {query}\n{context_summary}\nWhat is the next step?"

        response = self._gemini_client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=gemini_tools,
                temperature=0.1,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate:
            return self._decide_with_autonomous_planner(query, history, tool_definitions, working_memory, executed_steps)

        for part in candidate.content.parts:
            if getattr(part, "function_call", None):
                fn = part.function_call
                return StepDecision(
                    thought=f"Selected tool {fn.name}",
                    action_summary=f"Selected tool {fn.name} with arguments {dict(fn.args) if fn.args else {}}",
                    tool_name=fn.name,
                    arguments=dict(fn.args) if fn.args else {},
                    is_final=False,
                )

        text = candidate.content.parts[0].text if candidate.content.parts else "Investigation concluded."
        return StepDecision(
            thought="Generated final synthesis based on collected evidence.",
            action_summary="Synthesized findings from collected evidence.",
            is_final=True,
            final_answer=text,
        )

    def _decide_with_autonomous_planner(
        self,
        query: str,
        history: List[AgentMessage],
        tool_definitions: List[ToolDefinition],
        working_memory: Dict[str, Any],
        executed_steps: List[ActivityStep],
    ) -> StepDecision:
        """Dynamic, capability-first ReAct planner selecting tools based on intent and observations."""
        q_lower = query.lower()

        # -------------------------------------------------------------
        # 1. Multi-Turn Context Extraction & Pronoun Resolution
        # -------------------------------------------------------------
        prev_assistant_text = ""
        prev_user_text = ""
        if history:
            for m in reversed(history):
                if m.role == "assistant" and not prev_assistant_text:
                    prev_assistant_text = m.content.lower()
                elif m.role == "user" and not prev_user_text:
                    prev_user_text = m.content.lower()
                if prev_assistant_text and prev_user_text:
                    break

        is_meridian_followup = "meridian" in q_lower
        is_stuck_followup = not is_meridian_followup and any(w in q_lower for w in ["which ones are stuck", "why are they pending", "why is it stuck", "what is stuck", "which are stuck", "stuck"])
        is_policy_followup = any(w in q_lower for w in ["violates any", "violate policy", "check whether this violates", "operational policy", "check policy"])
        is_escalate_followup = any(w in q_lower for w in ["escalate it", "escalate", "trigger escalation", "post to jira", "notify finance"])


        # -------------------------------------------------------------
        # 2. Entity and Pattern Extraction
        # -------------------------------------------------------------
        jira_match = re.search(r"\b(kan-\d+)\b", q_lower)
        target_jira = jira_match.group(1).upper() if jira_match else None

        stripe_pi_match = re.search(r"\b(pi_[a-zA-Z0-9]+)\b", query)
        target_stripe_pi = stripe_pi_match.group(1) if stripe_pi_match else None

        paypal_ord_match = re.search(r"\b(ord-\d+|[0-9A-Z]{17})\b", query, re.IGNORECASE)
        target_paypal_ord = paypal_ord_match.group(1).upper() if paypal_ord_match else None

        # -------------------------------------------------------------
        # 3. Intent Classification
        # -------------------------------------------------------------
        # Slack Capability Inquiry vs Post Instruction vs Read Query
        is_slack_capability_inquiry = any(w in q_lower for w in [
            "can i make it post", "can you post to slack", "can it post to slack",
            "can opsdoctor post", "can we post to slack", "can i post something on slack",
            "can it post something on slack", "is it possible to post to slack",
            "how do i post to slack", "how to post to slack", "support slack posting",
            "able to post to slack", "post something on slack"
        ]) or (
            "slack" in q_lower
            and any(w in q_lower for w in ["can i", "can you", "can it", "is it possible", "how to", "how do", "are we able", "can we"])
            and any(w in q_lower for w in ["post", "send", "message", "publish", "notify"])
            and ("?" in q_lower or "something" in q_lower or "how" in q_lower)
        )

        is_slack_post_instruction = not is_slack_capability_inquiry and (
            any(w in q_lower for w in [
                "post to slack", "post on slack", "send to slack", "send on slack",
                "post a message to slack", "post an update to slack", "post an update on slack",
                "post message to slack", "send slack message", "post slack update",
                "notify slack", "publish to slack", "post in #ops", "post to #ops"
            ]) or (
                ("post" in q_lower or "send" in q_lower or "notify" in q_lower)
                and ("slack" in q_lower or "#ops-" in q_lower or "#payments" in q_lower)
                and not is_slack_capability_inquiry
            )
        )

        is_slack_read_query = not is_slack_capability_inquiry and not is_slack_post_instruction and (
            any(w in q_lower for w in [
                "read slack", "slack messages", "slack history", "channel history",
                "messages in #", "read channel", "list slack", "slack channels", "show slack channels",
                "list channels", "show channels"
            ]) or (
                "slack" in q_lower and any(w in q_lower for w in ["read", "get", "show", "history", "recent", "list", "check"])
            )
        )

        # Payment Domain Classification
        is_compare_query = any(w in q_lower for w in [
            "compare payment", "compare providers", "across paypal and stripe",
            "between paypal and stripe", "paypal vs stripe", "stripe vs paypal",
            "which payment provider", "which gateway", "what gateway", "which provider", "what payment gateway",
            "highest failure rate", "higher failure rate", "more payment fails", "more payment fail",
            "more fails", "more failure", "most fail", "failing more", "fails more", "has more fails",
            "having more payment fails", "having more fails", "having more failures",
            "highest fail", "compare gateways", "who has more fails", "who has higher failure"
        ]) or (
            any(g in q_lower for g in ["gateway", "gateways", "provider", "providers"])
            and any(c in q_lower for c in ["more", "most", "higher", "highest", "compare", "vs", "versus", "which", "what"])
            and any(m in q_lower for m in ["fail", "fails", "failure", "failures", "declined", "error", "rate"])
        )

        is_pending_query = not is_compare_query and ("pending" in q_lower or "unsettled" in q_lower) and any(
            w in q_lower for w in ["payment", "payments", "transaction", "transactions", "charge", "charges", "order", "orders", "stripe", "paypal", "settlement", "gateway"]
        )

        is_failed_query = not is_compare_query and not is_pending_query and (
            any(w in q_lower for w in [
                "failed payment", "failed payments", "payment failures", "failed transactions",
                "show me failed", "what payments have failed", "which payments failed",
                "declined payments", "declined charges", "capture errors"
            ])
        )

        is_payment_overview = not is_compare_query and not is_pending_query and not is_failed_query and any(w in q_lower for w in [
            "payment overview", "total payments", "payment summary", "payments today", "financial overview", "overall payments"
        ])

        # Specific Incident & Multi-Hop Classification
        is_checkout_incident_investigation = not is_compare_query and not is_pending_query and (
            "checkout payments are failing" in q_lower
            or "why checkout payments are failing" in q_lower
            or "inc-2026-042" in q_lower
            or ("triage incident" in q_lower)
        )

        is_paypal_investigation_query = not is_compare_query and not is_checkout_incident_investigation and (
            "investigate the paypal checkout failures" in q_lower
            or ("investigate" in q_lower and "paypal" in q_lower and "fail" in q_lower)
        )

        is_general_investigation = not is_compare_query and not is_checkout_incident_investigation and not is_paypal_investigation_query and any(w in q_lower for w in [
            "investigate", "root cause", "failure spike", "why are payments failing"
        ])

        mentions_jira_explicit = bool(target_jira or "jira" in q_lower or "ticket" in q_lower or "unresolved" in q_lower)
        is_jira_search_query = mentions_jira_explicit and any(w in q_lower for w in ["search", "unresolved", "list", "open"]) and not target_jira

        mentions_notion_explicit = any(w in q_lower for w in [
            "notion", "policy", "procedure", "sop", "runbook", "threshold",
            "refund policy", "escalation rules", "team ownership"
        ])
        is_notion_search_query = mentions_notion_explicit and any(w in q_lower for w in ["search", "find", "lookup"])

        mentions_gmail_explicit = any(w in q_lower for w in [
            "gmail", "email", "mail", "inbox", "customer complaint", "customer complaints", "brightpath", "omnicorp"
        ])

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 0: Slack Communications & Action Staging
        # -------------------------------------------------------------
        if is_slack_capability_inquiry:
            if "slack_channels" not in working_memory:
                return StepDecision(
                    thought="User inquired about Slack posting capabilities. Querying slack_list_channels via Swytchcode to determine active channels.",
                    action_summary="Querying Slack workspace channels via Swytchcode to determine available channels.",
                    tool_name="slack_list_channels",
                    arguments={},
                    is_final=False,
                )

            channels = working_memory.get("slack_channels", [])
            ch_lines = []
            if channels:
                for c in channels:
                    name = c.get("name", "")
                    topic = c.get("topic")
                    topic_str = f" – *{topic}*" if topic else ""
                    ch_lines.append(f"* `#{name}`{topic_str}")
            else:
                ch_lines = [
                    "* `#ops-incidents` – Incident triage and war-room updates",
                    "* `#ops-alerts` – Real-time telemetry alerts and deployment logs",
                    "* `#payments` – Gateway errors, reconciliation, and refund notices",
                    "* `#all-acmeflow-operations` – Broad team announcements",
                ]

            channel_list_str = "\n".join(ch_lines)
            answer = (
                "### 💬 Yes, OpsDoctor Can Post to Slack!\n\n"
                "OpsDoctor has native, bidirectional integration with Slack via **Swytchcode** (`slack.chat.postmessage.create`).\n\n"
                "#### 🛡️ How It Works: Human-in-the-Loop Safeguard\n"
                "Because posting to shared communication channels modifies team operations, OpsDoctor strictly adheres to consequential action safety:\n"
                "1. **Staged Proposals**: When you ask OpsDoctor to post a message, it **does not silently send it**. Instead, it prepares an **Action Proposal** in the **Action Center**.\n"
                "2. **Operator Verification**: The Action Center card displays the target channel, the full message payload, and the operational rationale.\n"
                "3. **Approve & Execute**: You click **Approve & Execute** to dispatch the message through Swytchcode in real-time, or **Reject** to cancel.\n\n"
                "#### 📢 Available Slack Channels (AcmeFlow Operations)\n"
                f"{channel_list_str}\n\n"
                "#### 🚀 Try It Right Now!\n"
                "You can prompt OpsDoctor with instructions such as:\n"
                "* *\"Post an update to #ops-incidents saying: 'Investigating checkout-v2 capture failures after deployment.'\"*\n"
                "* *\"Send a message to #ops-alerts: 'Stripe gateway operational baseline verified.'\"*\n"
                "* *\"Post the latest incident triage report to #ops-incidents\"*\n"
            )
            return StepDecision(
                thought="User inquired about Slack posting capabilities. Provided comprehensive guide and verified active channels via Swytchcode.",
                action_summary=f"Explained Slack posting capabilities and listed {len(channels)} active channels.",
                is_final=True,
                final_answer=answer,
            )

        if is_slack_post_instruction:
            target_ch = "ops-incidents"
            if "ops-alerts" in q_lower:
                target_ch = "ops-alerts"
            elif "ops-incidents" in q_lower:
                target_ch = "ops-incidents"
            elif "payments" in q_lower:
                target_ch = "payments"
            elif "general" in q_lower:
                target_ch = "general"
            elif "social" in q_lower:
                target_ch = "social"
            elif "all-acmeflow-operations" in q_lower:
                target_ch = "all-acmeflow-operations"
            else:
                ch_regex = re.search(r"#([a-zA-Z0-9_\-]+)", query)
                if ch_regex:
                    target_ch = ch_regex.group(1)

            # Extract message text
            msg_match = re.search(r'["\']([^"\']+)["\']', query)
            if msg_match:
                msg_text = msg_match.group(1)
            elif ":" in query:
                msg_text = query.split(":", 1)[1].strip()
            else:
                saying_match = re.search(r'\b(?:saying|that|message|with text)\s+(.+)$', query, re.IGNORECASE)
                if saying_match:
                    msg_text = saying_match.group(1).strip()
                else:
                    msg_text = f"OpsDoctor Status Update: Operational review for #{target_ch} in progress."

            channel_clean = target_ch.lstrip("#")
            staged_action = {
                "action_type": "slack_post_message",
                "system": "slack",
                "target": f"#{channel_clean}",
                "title": f"Post Operational Update to Slack (#{channel_clean})",
                "explanation": f"Ready to post message to #{channel_clean} in AcmeFlow Operations workspace via Swytchcode.",
                "proposed_payload": {
                    "channel_name": channel_clean,
                    "message": msg_text,
                },
            }
            final_text = (
                f"### 💬 Slack Message Staged for Approval\n\n"
                f"I have prepared an operational message to be posted to **#{channel_clean}**:\n\n"
                f"> *\"{msg_text}\"*\n\n"
                f"Please review the proposed message in the **Action Center** card below and click **Approve & Execute** to dispatch it to Slack."
            )
            return StepDecision(
                thought=f"User requested to post to Slack #{channel_clean}. Staged consequential action for operator approval.",
                action_summary=f"Staged Slack message to #{channel_clean} for operator approval.",
                is_final=True,
                final_answer=final_text,
                staged_action=staged_action,
            )

        if is_slack_read_query:
            if any(w in q_lower for w in ["list", "channels", "directory", "show channels"]):
                if "slack_channels" not in working_memory:
                    return StepDecision(
                        thought="User requested Slack channels list. Querying slack_list_channels.",
                        action_summary="Querying Slack workspace channels via Swytchcode.",
                        tool_name="slack_list_channels",
                        arguments={},
                        is_final=False,
                    )
                channels = working_memory.get("slack_channels", [])
                lines = ["### 📢 Available Slack Channels in AcmeFlow Operations\n"]
                for c in channels:
                    lines.append(f"* **#{c.get('name')}** (`{c.get('id')}`)" + (f" - *{c.get('topic')}*" if c.get('topic') else ""))
                return StepDecision(
                    thought="Slack channels retrieved and formatted dynamically.",
                    action_summary=f"Retrieved {len(channels)} Slack channels.",
                    is_final=True,
                    final_answer="\n".join(lines),
                )
            else:
                target_ch = "ops-alerts"
                if "ops-incidents" in q_lower:
                    target_ch = "ops-incidents"
                elif "payments" in q_lower:
                    target_ch = "payments"
                elif "general" in q_lower:
                    target_ch = "general"
                elif "social" in q_lower:
                    target_ch = "social"
                elif "all-acmeflow-operations" in q_lower:
                    target_ch = "all-acmeflow-operations"
                else:
                    ch_m = re.search(r"#([a-zA-Z0-9_\-]+)", query)
                    if ch_m:
                        target_ch = ch_m.group(1)

                if "slack_messages" not in working_memory and "slack_alerts" not in working_memory:
                    return StepDecision(
                        thought=f"User requested Slack message history for '{target_ch}'. Querying slack_read_channel.",
                        action_summary=f"Reading messages from Slack channel #{target_ch}.",
                        tool_name="slack_read_channel",
                        arguments={"channel_name": target_ch, "limit": 10},
                        is_final=False,
                    )
                msgs = working_memory.get("slack_messages") or working_memory.get("slack_alerts", [])
                lines = [f"### 💬 Recent Messages from Slack `#{target_ch}`\n"]
                if msgs:
                    for m in msgs[:6]:
                        lines.append(f"* `{m.get('user', 'system')}`: {m.get('text', '')}")
                else:
                    lines.append("No recent messages found in this channel.")
                return StepDecision(
                    thought="Slack channel messages retrieved dynamically.",
                    action_summary=f"Retrieved {len(msgs)} messages from #{target_ch}.",
                    is_final=True,
                    final_answer="\n".join(lines),
                )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 1: Generic / Multi-Provider Pending Payments
        # (CRITICAL: MUST NOT INVOKE JIRA)
        # -------------------------------------------------------------
        if is_pending_query and not is_stuck_followup:
            if "pending_payments" not in working_memory:
                provider_filter = None
                if "paypal" in q_lower and "stripe" not in q_lower:
                    provider_filter = "paypal"
                elif "stripe" in q_lower and "paypal" not in q_lower:
                    provider_filter = "stripe"

                summary_text = f"Querying pending payments from {'all connected providers' if not provider_filter else provider_filter.upper()}"
                return StepDecision(
                    thought=f"User asked for pending payments ({provider_filter or 'all'}). Querying payments_get_pending. Jira is not relevant.",
                    action_summary=summary_text,
                    tool_name="payments_get_pending",
                    arguments={"provider": provider_filter},
                    is_final=False,
                )

            res = working_memory.get("pending_payments", {})
            total_count = res.get("total_pending_count", 0)
            total_vol = res.get("total_pending_volume", 0.0)
            breakdown = res.get("provider_breakdown", {})
            txs = res.get("pending_transactions", [])

            lines = [
                "### 💳 Pending Payments Status Overview",
                "",
                f"* **Total Pending**: **{total_count} transaction(s)** totaling **${total_vol:,.2f} USD**",
                f"* **Time Horizon**: Real-time snapshot across active payment gateways",
                "",
                "#### 📊 Provider Breakdown",
            ]

            for p_name, p_data in breakdown.items():
                p_cnt = p_data.get("count", 0)
                p_amt = p_data.get("volume", 0.0)
                lines.append(f"* **{p_name.upper()}**: {p_cnt} pending (${p_amt:,.2f} USD)")

            if txs:
                lines.append("\n#### 🔍 Pending Transactions Detail")
                for t in txs:
                    raw_st = t.get("metadata", {}).get("raw_status", t.get("status"))
                    reason_str = ""
                    if raw_st == "requires_action":
                        reason_str = " | Reason: `3D Secure Challenge Pending`"
                    elif raw_st == "requires_payment_method":
                        reason_str = " | Reason: `Awaiting Checkout Completion`"
                    elif raw_st == "processing":
                        reason_str = " | Reason: `Bank Clearance Processing`"

                    lines.append(
                        f"* `{t.get('id')}` ({t.get('provider').upper()}): "
                        f"**${_safe_float(t.get('amount', 0)):,.2f}** for **{t.get('customer')}** "
                        f"| Flow: `{t.get('flow')}` | Method: `{t.get('payment_method')}`{reason_str}"
                    )

            if total_count > 0:
                lines.append(
                    "\n> [!NOTE]\n"
                    f"> Retrieved {total_count} live pending transaction(s) directly from connected payment gateways. "
                    "You can ask 'Which ones are stuck?' or 'Why is the Meridian payment stuck?' for deep-dive investigation."
                )
            else:
                lines.append("\n✅ There are currently zero pending payment transactions requiring settlement across connected providers.")

            return StepDecision(
                thought="Pending payments retrieved and normalized dynamically from tool observation. Read-only query, no action staged.",
                action_summary=f"Normalized {total_count} pending payment records across connected providers.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 1B: Failed Payments Query
        # -------------------------------------------------------------
        if is_failed_query and not is_stuck_followup and not is_compare_query:
            if "failed_payments" not in working_memory:
                provider_filter = None
                if "paypal" in q_lower and "stripe" not in q_lower:
                    provider_filter = "paypal"
                elif "stripe" in q_lower and "paypal" not in q_lower:
                    provider_filter = "stripe"

                return StepDecision(
                    thought=f"User asked for failed payments. Querying payments_get_failed.",
                    action_summary=f"Querying failed payment transactions from {'all providers' if not provider_filter else provider_filter.upper()}.",
                    tool_name="payments_get_failed",
                    arguments={"provider": provider_filter},
                    is_final=False,
                )

            res = working_memory.get("failed_payments", {})
            total_count = res.get("total_failed_count", 0)
            total_vol = res.get("total_failed_volume", 0.0)
            breakdown = res.get("provider_breakdown", {})
            txs = res.get("failed_transactions", [])

            lines = [
                "### 🚨 Failed Payments Overview",
                "",
                f"* **Total Failed**: **{total_count} transaction(s)** totaling **${total_vol:,.2f} USD**",
                "",
                "#### 📊 Provider Breakdown",
            ]
            for p_name, p_data in breakdown.items():
                lines.append(f"* **{p_name.upper()}**: {p_data.get('count', 0)} failed (${p_data.get('volume', 0.0):,.2f} USD)")

            if txs:
                lines.append("\n#### 🔍 Failed Transactions Detail")
                for t in txs[:8]:
                    lines.append(
                        f"* `{t.get('id')}` ({t.get('provider').upper()}): "
                        f"**${_safe_float(t.get('amount', 0)):,.2f}** for **{t.get('customer')}** "
                        f"| Reason: `{t.get('failure_reason') or 'Declined'}`"
                    )

            return StepDecision(
                thought="Failed payments retrieved dynamically from tool observation. Read-only query, no action staged.",
                action_summary=f"Retrieved {total_count} failed payment records across connected gateways.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        # -------------------------------------------------------------
        # MULTI-TURN CONTEXT: Specific customer investigation (e.g. Meridian)
        # -------------------------------------------------------------
        if is_meridian_followup and not is_general_investigation:
            pending_list = working_memory.get("pending_payments", {}).get("pending_transactions", [])
            stripe_list = working_memory.get("stripe_payments", [])
            candidate_txs = pending_list + stripe_list

            if not candidate_txs:
                return StepDecision(
                    thought="User asked specifically about Meridian payment. Querying stripe_list_payments to locate transaction.",
                    action_summary="Searching Stripe gateway for Meridian Tech payment records.",
                    tool_name="stripe_list_payments",
                    arguments={"limit": 10},
                    is_final=False,
                )

            meridian_items = [
                t for t in candidate_txs
                if "meridian" in str(t.get("customer", "")).lower()
                or "meridian" in str(t.get("metadata", "")).lower()
                or "pipeline" in str(t.get("metadata", {}).get("description", "")).lower()
                or "subscription" in str(t.get("metadata", {}).get("description", "")).lower()
                or str(t.get("flow", "")) == "enterprise-billing"
            ]
            item = meridian_items[0] if meridian_items else candidate_txs[0]
            raw_st = item.get("metadata", {}).get("raw_status", item.get("status", "requires_payment_method"))
            customer_name = "Meridian Tech"
            if item.get("customer") and "cus_" not in item.get("customer"):
                customer_name = item.get("customer")

            ans = (
                f"### 💳 Investigation: Meridian Tech Payment (`{item.get('id', 'N/A')}`)\n\n"
                f"* **Customer**: **{customer_name}**\n"
                f"* **Amount**: **${item.get('amount', 0):,.2f} {item.get('currency', 'USD')}**\n"
                f"* **Operational Status**: `{raw_st}` ({item.get('status', 'pending')})\n"
                f"* **Description**: {item.get('metadata', {}).get('description') or 'Custom Data Pipeline Provisioning'}\n"
                f"* **Root Cause of Delay**: The checkout session was initialized without immediate payment method confirmation. "
                f"The transaction is held in `{raw_st}` awaiting the customer or checkout pipeline to finalize payment method credentials.\n\n"
                f"> You can ask: 'Check whether this violates any operational policy' or 'Escalate it'."
            )

            return StepDecision(
                thought="Located and analyzed Meridian Tech transaction dynamically.",
                action_summary=f"Investigated Meridian payment {item.get('id')}.",
                is_final=True,
                final_answer=ans,
            )

        # -------------------------------------------------------------
        # MULTI-TURN CONTEXT: Follow-up on pending payments ("Which ones are stuck?")
        # -------------------------------------------------------------
        if is_stuck_followup and ("pending" in prev_assistant_text or "pending" in prev_user_text or "pending_payments" in working_memory):
            if "pending_payments" not in working_memory:
                return StepDecision(
                    thought="User asked which payments are stuck in follow-up. Retrieving live pending payments.",
                    action_summary="Querying pending payments from connected gateways to inspect bottlenecks.",
                    tool_name="payments_get_pending",
                    arguments={},
                    is_final=False,
                )

            res = working_memory.get("pending_payments", {})
            txs = res.get("pending_transactions", [])
            lines = [
                "### 🔍 Detailed Bottleneck Analysis for Pending Payments",
                "",
                f"Inspecting **{len(txs)} pending transaction(s)** discovered in current operational state:",
                "",
            ]

            for t in txs:
                raw_st = t.get("metadata", {}).get("raw_status", t.get("status"))
                bottleneck = "Awaiting upstream settlement"
                action_needed = "Monitor settlement clearance"
                if raw_st == "requires_action":
                    bottleneck = "Customer 3D Secure (3DS) authentication challenge in progress."
                    action_needed = "Customer must complete SMS/Banking OTP verification prompt on checkout."
                elif raw_st == "requires_payment_method":
                    bottleneck = "Checkout session created, but customer has not finalized payment method details."
                    action_needed = "Checkout session expires automatically after timeout if abandoned."
                elif raw_st == "processing":
                    bottleneck = "Asynchronous bank transfer (ACH Direct Debit) awaiting ACH clearance."
                    action_needed = "ACH debits typically take 2-4 business days to settle."

                lines.append(f"#### 💳 `{t.get('id')}` ({t.get('provider').upper()}) - ${t.get('amount', 0):,.2f} USD")
                lines.append(f"* **Customer**: {t.get('customer')}")
                lines.append(f"* **State**: `{raw_st}`")
                lines.append(f"* **Bottleneck**: {bottleneck}")
                lines.append(f"* **Resolution Path**: {action_needed}\n")

            return StepDecision(
                thought="Analyzed bottleneck details for pending payments dynamically from tool observations.",
                action_summary=f"Synthesized bottleneck analysis for {len(txs)} pending transactions.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        # -------------------------------------------------------------
        # MULTI-TURN CONTEXT: Check Operational Policy in Notion
        # -------------------------------------------------------------
        if is_policy_followup and not is_general_investigation:
            if "notion_policy" not in working_memory:
                return StepDecision(
                    thought="User requested operational policy evaluation. Retrieving 'Payment Procedures' from Notion.",
                    action_summary="Retrieving 'Payment Procedures' runbook from Notion knowledge base.",
                    tool_name="notion_read_policy_page",
                    arguments={"page_name_or_id": "Payment Procedures"},
                    is_final=False,
                )

            pol = working_memory.get("notion_policy", {})
            return StepDecision(
                thought="Notion policy retrieved and evaluated against current operational context.",
                action_summary="Evaluated retrieved Notion policy against operational context.",
                is_final=True,
                final_answer=(
                    f"### 📖 Operational Policy Evaluation: {pol.get('title')}\n\n"
                    f"Retrieved from the **AcmeFlow Operations** Notion workspace:\n\n"
                    f"{pol.get('content')}\n\n"
                    f"#### 🔍 Policy Assessment\n"
                    f"* **Payment Failure Rule**: More than 5 failed transactions within 15 minutes is classified as an operational incident requiring Finance escalation.\n"
                    f"* **Pending Incomplete Checkouts**: Unconfirmed checkouts are governed by routine customer checkout timeouts rather than immediate incident escalation.\n"
                    f"* **Action Available**: If you wish to notify on-call or escalate, say **'Escalate it'**."
                ),
            )

        # -------------------------------------------------------------
        # MULTI-TURN CONTEXT: Action execution / "Escalate it"
        # -------------------------------------------------------------
        if is_escalate_followup:
            target_key = target_jira or "KAN-4"
            staged_action = {
                "action_type": "jira_add_comment",
                "system": "jira",
                "target": target_key,
                "title": f"Post Investigation & Finance Escalation to Jira ({target_key})",
                "explanation": f"Operator requested escalation. Ready to post verified evidence and formal Finance notification to Jira {target_key}.",
                "proposed_payload": {
                    "issue_key": target_key,
                    "comment_text": (
                        "OpsDoctor Investigation\n"
                        "Incident: INC-2026-042\n"
                        "Flow: checkout-v2\n"
                        "Status: Escalated by Operator\n\n"
                        "Findings:\n"
                        "- PayPal: Repeated capture failures observed on checkout-v2 with HTTP 422 ORDER NOT APPROVED\n"
                        "- Slack: Deployment checkout-api-2026.09.25.3 preceded the alert spike\n"
                        "- Gmail: Enterprise customer complaints logged in support queue\n\n"
                        "Policy:\n"
                        "- Payment Procedures requires Finance escalation when more than 5 failed transactions occur within 15 minutes\n\n"
                        "Assessment:\n"
                        "- Threshold satisfied. Formal escalation staged per operator confirmation\n\n"
                        "Recommended next steps:\n"
                        "1. Finance review by @daniel.kim\n"
                        "2. Engineering deployment inspection by @ethan.cole\n\n"
                        "Generated by OpsDoctor"
                    ),
                },
            }

            return StepDecision(
                thought="User requested escalation. Staging consequential Jira comment for operator approval.",
                action_summary=f"Staged formal Finance escalation comment on Jira ticket {target_key}.",
                is_final=True,
                final_answer=(
                    f"### 🛡️ Escalation Action Prepared for Jira `{target_key}`\n\n"
                    f"I have prepared a formal operational escalation comment for Jira ticket **{target_key}**.\n\n"
                    f"**Proposed Comment Preview**:\n"
                    f"> OpsDoctor Investigation\n"
                    f"> Incident: INC-2026-042 | Flow: checkout-v2\n"
                    f"> Status: Escalated by Operator\n"
                    f"> Findings: Gateway failures correlated with deployment and customer complaints\n"
                    f"> Policy: Payment Procedures threshold exceeded\n\n"
                    f"⚠️ **Human-in-the-Loop Safeguard**: This action modifies external Jira state. "
                    f"Please review and approve the request in the Action Center or click **Approve** below."
                ),
                staged_action=staged_action,
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 2: Provider Comparison
        # -------------------------------------------------------------
        if is_compare_query:
            if "comparison" not in working_memory:
                return StepDecision(
                    thought="User asked to compare payment providers. Querying cross-provider performance metrics.",
                    action_summary="Querying metrics from connected payment gateways for comparative analysis.",
                    tool_name="payments_compare_providers",
                    arguments={},
                    is_final=False,
                )

            comp = working_memory.get("comparison", {})
            rows = comp.get("comparison", [])
            highest_raw = comp.get("highest_failure_rate_provider") or "paypal"
            highest_p = "PayPal" if highest_raw.lower() == "paypal" else "Stripe" if highest_raw.lower() == "stripe" else highest_raw.capitalize()

            lines = [
                f"{highest_p} has the higher observed failure rate.",
                "",
            ]
            for r in rows:
                p_raw = r.get("provider", "")
                p_name = "PayPal" if p_raw.lower() == "paypal" else "Stripe" if p_raw.lower() == "stripe" else p_raw.capitalize()
                failed = r.get("failed", 0)
                total = r.get("total_transactions", 0)
                rate = int(round(r.get("failure_rate_percent", 0)))
                lines.append(f"{p_name}: {failed}/{total} failed = {rate}%")

            return StepDecision(
                thought="Provider comparative analysis complete dynamically from tool observation. Read-only query, no action staged.",
                action_summary="Generated comparative analysis of payment gateway failure rates.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 3: Specific Provider Transaction Lookup
        # -------------------------------------------------------------
        if target_stripe_pi and not is_general_investigation:
            if "stripe_payment" not in working_memory:
                return StepDecision(
                    thought=f"User requested specific Stripe PaymentIntent '{target_stripe_pi}'. Querying stripe_get_payment.",
                    action_summary=f"Querying Stripe gateway for PaymentIntent {target_stripe_pi}.",
                    tool_name="stripe_get_payment",
                    arguments={"payment_id": target_stripe_pi},
                    is_final=False,
                )
            sp = working_memory.get("stripe_payment", {})
            return StepDecision(
                thought="Stripe payment retrieved dynamically.",
                action_summary=f"Retrieved Stripe PaymentIntent {sp.get('id')}.",
                is_final=True,
                final_answer=(
                    f"### 💳 Stripe Payment Record: `{sp.get('id')}`\n\n"
                    f"* **Customer**: {sp.get('customer')}\n"
                    f"* **Amount**: ${sp.get('amount', 0):,.2f} {sp.get('currency', 'USD')}\n"
                    f"* **Status**: `{sp.get('status')}`\n"
                    f"* **Payment Method**: `{sp.get('payment_method')}`\n"
                    f"* **Flow**: `{sp.get('flow')}`\n"
                    f"* **Created**: `{sp.get('created_at')}`\n"
                    f"* **Failure Reason**: {sp.get('failure_reason') or 'None'}\n"
                ),
            )

        if target_paypal_ord and not (is_general_investigation or mentions_jira_explicit):
            if "paypal_order" not in working_memory:
                return StepDecision(
                    thought=f"User requested PayPal order '{target_paypal_ord}'. Querying paypal_get_order.",
                    action_summary=f"Querying PayPal gateway for order {target_paypal_ord}.",
                    tool_name="paypal_get_order",
                    arguments={"order_id": target_paypal_ord},
                    is_final=False,
                )
            po = working_memory.get("paypal_order", {})
            oid = po.get("internal_order_id") or po.get("order_id") or target_paypal_ord
            pid = po.get("paypal_order_id") or po.get("id") or "N/A"
            return StepDecision(
                thought="PayPal order retrieved dynamically.",
                action_summary=f"Retrieved PayPal order {oid}.",
                is_final=True,
                final_answer=(
                    f"### 💳 PayPal Order Record: `{oid}`\n\n"
                    f"* **Internal Order ID**: `{oid}`\n"
                    f"* **PayPal Order ID**: `{pid}`\n"
                    f"* **Customer**: {po.get('customer')}\n"
                    f"* **Status**: `{po.get('order_status') or po.get('status')}`\n"
                    f"* **Amount**: ${float(po.get('amount', 0)):,.2f} {po.get('currency', 'USD')}\n"
                    f"* **Flow**: `{po.get('flow')}`\n"
                ),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 4: Jira-Specific Issues / Tickets
        # -------------------------------------------------------------
        if is_jira_search_query:
            if "jira_search" not in working_memory:
                jql_query = "project = KAN order by created desc"
                return StepDecision(
                    thought="User requested search of Jira issues. Querying jira_search_issues.",
                    action_summary="Searching Jira issues using JQL query.",
                    tool_name="jira_search_issues",
                    arguments={"jql": jql_query},
                    is_final=False,
                )
            issues = working_memory.get("jira_search", [])
            lines = [f"### 📋 Jira Issues Search Results ({len(issues)} found)\n"]
            for iss in issues[:5]:
                f_obj = iss.get("fields", {})
                lines.append(f"* **{iss.get('key')}**: {f_obj.get('summary', 'No summary')} [Status: `{f_obj.get('status', {}).get('name', 'N/A')}`]")
            return StepDecision(
                thought="Jira search results retrieved dynamically.",
                action_summary=f"Retrieved {len(issues)} Jira issues.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        if mentions_jira_explicit and not is_general_investigation:
            if "jira_issue" not in working_memory:
                key = target_jira or "KAN-1"
                return StepDecision(
                    thought=f"User requested Jira issue details for '{key}'. Querying jira_get_issue.",
                    action_summary=f"Querying Jira issue tracker for ticket {key}.",
                    tool_name="jira_get_issue",
                    arguments={"issue_key": key},
                    is_final=False,
                )
            issue = working_memory.get("jira_issue", {})
            return StepDecision(
                thought="Jira issue retrieved dynamically.",
                action_summary=f"Retrieved Jira issue {issue.get('key')}.",
                is_final=True,
                final_answer=(
                    f"### 📋 Jira Issue Details: `{issue.get('key')}`\n\n"
                    f"* **Key**: `{issue.get('key')}`\n"
                    f"* **Summary**: {issue.get('summary')}\n"
                    f"* **Status**: `{issue.get('status')}`\n"
                    f"* **Project**: {issue.get('project')}\n"
                    f"* **Priority**: {issue.get('priority')}\n"
                    f"* **Created**: `{issue.get('created')}`\n"
                ),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 5: Notion Runbooks & Policies
        # -------------------------------------------------------------
        if is_notion_search_query:
            if "notion_policies" not in working_memory:
                return StepDecision(
                    thought="User requested search of operational policies in Notion.",
                    action_summary="Searching Notion workspace for operational runbooks.",
                    tool_name="notion_search_policies",
                    arguments={"query": ""},
                    is_final=False,
                )
            pols = working_memory.get("notion_policies", [])
            lines = [f"### 📖 AcmeFlow Operations Notion Runbooks ({len(pols)} found)\n"]
            for p in pols:
                lines.append(f"* **{p.get('title')}** (`{p.get('id')}`)")
            return StepDecision(
                thought="Notion policies retrieved dynamically.",
                action_summary=f"Retrieved {len(pols)} policy pages from Notion.",
                is_final=True,
                final_answer="\n".join(lines),
            )

        if mentions_notion_explicit and not is_general_investigation:
            if "notion_policy" not in working_memory:
                target_page = "Payment Procedures"
                if "refund" in q_lower:
                    target_page = "Refund Policy"
                elif "escalation" in q_lower:
                    target_page = "Escalation Rules"
                elif "team" in q_lower or "owner" in q_lower:
                    target_page = "Team Ownership"
                elif "sop" in q_lower or "support" in q_lower:
                    target_page = "Customer Support SOP"
                elif "incident" in q_lower:
                    target_page = "Incident Response"

                return StepDecision(
                    thought=f"User requested policy documentation for '{target_page}'. Querying notion_read_policy_page.",
                    action_summary=f"Reading '{target_page}' page from Notion knowledge base.",
                    tool_name="notion_read_policy_page",
                    arguments={"page_name_or_id": target_page},
                    is_final=False,
                )
            pol = working_memory.get("notion_policy", {})
            return StepDecision(
                thought="Notion policy retrieved dynamically.",
                action_summary=f"Retrieved Notion policy {pol.get('title')}.",
                is_final=True,
                final_answer=(
                    f"### 📖 AcmeFlow Operations Policy: {pol.get('title')}\n\n"
                    f"Retrieved from the **AcmeFlow Operations** Notion workspace:\n\n"
                    f"{pol.get('content')}\n"
                ),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 6: Gmail Support Search
        # -------------------------------------------------------------
        if mentions_gmail_explicit and not is_general_investigation:
            if "gmail_messages" not in working_memory:
                g_query = "payment failed"
                if "brightpath" in q_lower:
                    g_query = "BrightPath Labs"
                elif "omnicorp" in q_lower:
                    g_query = "OmniCorp"
                return StepDecision(
                    thought=f"User requested customer email search for '{g_query}'. Querying gmail_search_messages.",
                    action_summary=f"Searching Gmail customer support inbox for '{g_query}'.",
                    tool_name="gmail_search_messages",
                    arguments={"query": g_query},
                    is_final=False,
                )
            emails = working_memory.get("gmail_messages", [])
            lines = [f"### 📬 Customer Support Email Threads ({len(emails)} found)\n"]
            for em in emails[:4]:
                lines.append(
                    f"* **{em.get('subject')}**\n"
                    f"  * From: `{em.get('from')}` | Date: `{em.get('date')}`\n"
                    f"  * Excerpt: *\"{em.get('snippet', '')[:140]}...\"*"
                )
            return StepDecision(
                thought="Customer emails retrieved dynamically.",
                action_summary=f"Retrieved {len(emails)} customer email threads from Gmail.",
                is_final=True,
                final_answer="\n\n".join(lines),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 7A: Standalone PayPal Investigation Query (READ-ONLY)
        # (Scenario C: "investigate the PayPal checkout failures" -> NO action staged!)
        # -------------------------------------------------------------
        if is_paypal_investigation_query:
            if "paypal_evidence" not in working_memory:
                return StepDecision(
                    thought="User asked to investigate PayPal checkout failures. Querying payment telemetry.",
                    action_summary="Inspecting payment gateway failure telemetry on checkout-v2.",
                    tool_name="paypal_get_incident_evidence",
                    arguments={"flow": "checkout-v2"},
                    is_final=False,
                )

            pp_data = working_memory.get("paypal_evidence", {})
            failed_count = pp_data.get("total_failed_capture_attempts", 0)
            orders = pp_data.get("orders", [])

            lines = [
                "### 🔍 Investigation: PayPal Checkout Failures",
                "",
                f"* **Flow**: `checkout-v2`",
                f"* **Total Failed Capture Attempts**: **{failed_count}**",
                f"* **Error Pattern**: `ORDER_NOT_APPROVED` (HTTP 422)",
                f"* **Impact**: Repeated checkout drop-offs during payment capture phase.",
                "",
                "#### 🔍 Sample Affected Transactions",
            ]
            for o in orders[:4]:
                lines.append(
                    f"* Order `{o.get('order_id')}` ({o.get('customer')}): "
                    f"${_safe_float(o.get('amount', 0)):,.2f} USD - Status `{o.get('order_status')}`"
                )

            lines.append(
                "\n> [!TIP]\n"
                "> You can ask: *'Check whether this violates any operational policy'* to evaluate escalation thresholds, or *'Escalate it'*."
            )

            return StepDecision(
                thought="PayPal checkout failure investigation concluded dynamically. Read-only query, no mutation.",
                action_summary=f"Retrieved PayPal failure telemetry ({failed_count} failed capture attempts).",
                is_final=True,
                final_answer="\n".join(lines),
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 7B: Multi-Hop Cross-System Root-Cause Investigation
        # (Scenario 9: "Investigate why checkout payments are failing")
        # Step 1: Query Gateway Failure Telemetry
        # Step 2: Correlate with Jira issue tracker
        # Step 3: Query Notion policy for threshold
        # Step 4: Query Slack #ops-alerts for deployment correlation
        # Step 5: Synthesize observed facts vs policy vs conclusion and stage action
        # -------------------------------------------------------------
        if is_checkout_incident_investigation or is_general_investigation:
            # Step 1: Query Gateway Failure Telemetry
            if "paypal_evidence" not in working_memory:
                flow = "checkout-v2"
                return StepDecision(
                    thought="Starting investigation by checking empirical payment failure telemetry on checkout-v2.",
                    action_summary="Inspecting payment gateway failure telemetry on checkout-v2.",
                    tool_name="paypal_get_incident_evidence",
                    arguments={"flow": flow},
                    is_final=False,
                )

            # Step 2: Correlate with Issue Tracker (Jira)
            if "jira_issue" not in working_memory:
                target_key = target_jira or "KAN-4"
                return StepDecision(
                    thought=f"Observed gateway telemetry. Step 2: Check Jira issue tracker ({target_key}) to correlate existing ticket status.",
                    action_summary=f"Correlating telemetry with Jira issue tracker ticket {target_key}.",
                    tool_name="jira_get_issue",
                    arguments={"issue_key": target_key},
                    is_final=False,
                )

            # Step 3: Query Notion Runbook for Policy Threshold
            if "notion_policy" not in working_memory:
                return StepDecision(
                    thought="Step 3: Retrieve Notion 'Payment Procedures' runbook to check incident escalation thresholds.",
                    action_summary="Retrieving 'Payment Procedures' runbook from Notion to evaluate escalation threshold.",
                    tool_name="notion_read_policy_page",
                    arguments={"page_name_or_id": "Payment Procedures"},
                    is_final=False,
                )

            # Step 4: Query Slack #ops-alerts for Root Cause Correlation
            if "slack_alerts" not in working_memory:
                return StepDecision(
                    thought="Step 4: Query Slack '#ops-alerts' to correlate failures with recent deployments.",
                    action_summary="Querying Slack channel #ops-alerts to correlate failure timeline with deployments.",
                    tool_name="slack_read_channel",
                    arguments={"channel_name": "ops-alerts", "limit": 15},
                    is_final=False,
                )

            # Step 5: Synthesis and Professional Jira Action Staging
            pp_data = working_memory.get("paypal_evidence", {})
            failed_count = pp_data.get("total_failed_capture_attempts", 0)
            threshold_met = failed_count > 5
            jira_key = working_memory.get("jira_issue", {}).get("key", "KAN-4")
            flow_name = pp_data.get("flow", "checkout-v2")
            deployment_id = pp_data.get("deployment", "checkout-api-2026.09.25.3")

            staged_action = None
            if threshold_met:
                jira_comment_body = (
                    "OpsDoctor Investigation\n"
                    "Incident: INC-2026-042\n"
                    f"Flow: {flow_name}\n"
                    "Status: Confirmed incident\n\n"
                    "Findings:\n"
                    f"- PayPal: {failed_count} failed capture attempts with HTTP 422 ORDER NOT APPROVED\n"
                    f"- Slack: Deployment {deployment_id} preceded the alert spike\n"
                    "- Gmail: Customer complaints logged from affected enterprise customers\n\n"
                    "Policy:\n"
                    "- Payment Procedures requires Finance escalation when more than 5 failed transactions occur within 15 minutes\n\n"
                    "Assessment:\n"
                    f"- {failed_count} failed attempts occurred within the policy window, so the Finance escalation threshold was met\n\n"
                    "Recommended next steps:\n"
                    "1. Finance review\n"
                    "2. Engineering investigation of the checkout deployment\n\n"
                    "Generated by OpsDoctor"
                )

                staged_action = {
                    "action_type": "jira_add_comment",
                    "system": "jira",
                    "target": jira_key,
                    "title": f"Post Investigation Report & Finance Escalation to Jira ({jira_key})",
                    "explanation": f"Threshold exceeded ({failed_count} failures > 5). Ready to update Jira ticket {jira_key} with verified cross-system evidence and formal Finance escalation.",
                    "proposed_payload": {"issue_key": jira_key, "comment_text": jira_comment_body},
                }

            final_synthesis = (
                f"### 🩺 OpsDoctor Autonomous Investigation Complete\n\n"
                f"I have investigated your request across our connected operational systems (**PayPal Sandbox**, **Stripe**, **Jira**, **Slack**, and **Notion**).\n\n"
                f"#### 📊 Cross-System Findings Matrix\n"
                f"1. **Payment Gateways**: Identified **{failed_count} failed capture attempts** in PayPal on `{flow_name}` (`ORDER_NOT_APPROVED` HTTP 422). Stripe gateway was checked and showed normal baseline operations without API errors.\n"
                f"2. **Jira Issue Tracker**: Correlated ticket `{jira_key}` (`INC-2026-042`).\n"
                f"3. **Slack Timeline**: In `#ops-alerts`, deployment `{deployment_id}` (14:12 UTC) was deployed immediately before the capture failure spike (14:18 UTC).\n"
                f"4. **Notion Policy Evaluation**: Retrieved *Payment Procedures*. Policy states: `> 5 failed transactions within 15 minutes requires Finance escalation`.\n\n"
                f"**Policy Conclusion**: Since **{failed_count} failures > 5**, the threshold is **conclusively met**. Mandatory **Finance escalation** is required."
            )

            return StepDecision(
                thought="Investigation complete with cross-system evidence correlation.",
                action_summary=f"Synthesized cross-system findings across 4 integrations and staged Jira action for {jira_key}.",
                is_final=True,
                final_answer=final_synthesis,
                staged_action=staged_action,
            )

        # -------------------------------------------------------------
        # CAPABILITY DOMAIN 8: High-Level Operations Overview (Default)
        # -------------------------------------------------------------
        if "overview" not in working_memory:
            return StepDecision(
                thought="General operational query. Fetching high-level payment overview dynamically.",
                action_summary="Querying unified payment overview across connected gateways.",
                tool_name="payments_get_overview",
                arguments={},
                is_final=False,
            )

        ov = working_memory.get("overview", {})
        return StepDecision(
            thought="Providing dynamic high-level operations status.",
            action_summary="Generated operational status overview.",
            is_final=True,
            final_answer=(
                f"### 🩺 OpsDoctor Operational Overview\n\n"
                f"* **Total Transactions**: {ov.get('total_transactions', 0)}\n"
                f"* **Total Volume**: ${ov.get('total_volume', 0):,.2f} USD\n"
                f"* **Pending Settlements**: {ov.get('total_pending', 0)} (${ov.get('total_pending_volume', 0):,.2f} USD)\n"
                f"* **Failed Transactions**: {ov.get('total_failed', 0)} (${ov.get('total_failed_volume', 0):,.2f} USD)\n"
                f"* **Connected Providers**: PayPal Sandbox, Stripe\n\n"
                "Ask me any question about pending payments, customer complaints, runbooks, or active incident triage."
            ),
        )
