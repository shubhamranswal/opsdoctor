"""Notion adapter using Swytchcode for all operations."""

from typing import Any, Dict, List, Optional
from packages.adapters.base import BaseSwytchcodeClient


class NotionSwytchcodeClient(BaseSwytchcodeClient):
    """Client for Notion operations executed exclusively via Swytchcode."""

    def get_me(self) -> Dict[str, Any]:
        """Verify Notion workspace bot and user identity."""
        return self.execute("notion.me.list", {})

    def search(self, query: str = "") -> List[Dict[str, Any]]:
        """Search pages and databases in the workspace."""
        body: Dict[str, Any] = {}
        if query:
            body["query"] = query
        res = self.execute("notion.search.create", {"body": body})
        return res.get("results", [])

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """Retrieve page metadata."""
        return self.execute("notion.page.get", {"page_id": page_id})

    def get_block_children(self, block_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
        """Retrieve child blocks for a page or block container."""
        res = self.execute("notion.children.get", {"block_id": block_id, "page_size": page_size})
        return res.get("results", [])

    def extract_page_text(self, page_id: str) -> str:
        """Fetch all blocks for a page and convert to readable text."""
        blocks = self.get_block_children(block_id=page_id)
        lines = []
        for b in blocks:
            b_type = b.get("type", "")
            type_obj = b.get(b_type, {})
            text = ""
            if isinstance(type_obj, dict):
                rich_text = type_obj.get("rich_text", [])
                if rich_text:
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                elif "title" in type_obj:
                    text = type_obj.get("title", "")
            if text:
                if b_type.startswith("heading"):
                    lines.append(f"\n### {text}")
                elif b_type == "bulleted_list_item":
                    lines.append(f"• {text}")
                elif b_type == "numbered_list_item":
                    lines.append(f"- {text}")
                else:
                    lines.append(text)
        return "\n".join(lines).strip()
