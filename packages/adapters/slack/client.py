"""Slack adapter using Swytchcode for all operations."""

from typing import Any, Dict, List, Optional
from packages.adapters.base import BaseSwytchcodeClient


class SlackSwytchcodeClient(BaseSwytchcodeClient):
    """Client for Slack operations executed exclusively via Swytchcode."""

    def auth_test(self) -> Dict[str, Any]:
        """Verify connected Slack identity."""
        return self.execute("slack.auth.test.list", {})

    def list_channels(self, types: Optional[str] = None) -> List[Dict[str, Any]]:
        """List channels in the workspace."""
        args: Dict[str, Any] = {}
        if types:
            args["types"] = types
        res = self.execute("slack.conversations.list.list", args)
        return res.get("channels", [])

    def get_channel_history(self, channel_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent message history for a channel."""
        res = self.execute("slack.conversations.history.list", {"channel": channel_id, "limit": limit})
        return res.get("messages", [])

    def post_message(self, channel_id: str, text: str) -> Dict[str, Any]:
        """Post a message to a channel."""
        return self.execute("slack.chat.postmessage.create", {"body": {"channel": channel_id, "text": text}})

    def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get information about a specific channel."""
        res = self.execute("slack.conversations.info.list", {"channel": channel_id})
        return res.get("channel", {})
