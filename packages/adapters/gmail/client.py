"""Gmail adapter using Swytchcode for all operations."""

from typing import Any, Dict, List, Optional
from packages.adapters.base import BaseSwytchcodeClient


class GmailSwytchcodeClient(BaseSwytchcodeClient):
    """Client for Gmail operations executed exclusively via Swytchcode."""

    def get_profile(self, user_id: str = "me") -> Dict[str, Any]:
        """Get authenticated user profile."""
        return self.execute("gmail.user.profile.get", {"userId": user_id})

    def list_messages(self, q: str = "", max_results: int = 50, user_id: str = "me") -> List[Dict[str, Any]]:
        """List/search messages in the mailbox."""
        args: Dict[str, Any] = {"userId": user_id, "maxResults": max_results}
        if q:
            args["q"] = q
        res = self.execute("gmail.user.messages.get", args)
        return res.get("messages", [])

    def get_message(self, message_id: str, format: str = "full", user_id: str = "me") -> Dict[str, Any]:
        """Retrieve details of a specific email message."""
        return self.execute("gmail.user.messages.get1", {"userId": user_id, "id": message_id, "format": format})
