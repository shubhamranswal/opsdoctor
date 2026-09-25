"""Jira adapter using Swytchcode for all operations."""

from typing import Any, Dict, List, Optional
from packages.adapters.base import BaseSwytchcodeClient


class JiraSwytchcodeClient(BaseSwytchcodeClient):
    """Client for Jira operations executed exclusively via Swytchcode."""

    def get_myself(self) -> Dict[str, Any]:
        """Verify Jira identity."""
        return self.execute("jira.api.myself.list", {})

    def search_issues(self, jql: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Search issues using modern JQL search endpoint."""
        res = self.execute("jira.api.jql.list", {"jql": jql, "maxResults": max_results})
        return res.get("issues", [])

    def get_issue(self, issue_id_or_key: str) -> Dict[str, Any]:
        """Fetch details of a specific Jira issue."""
        return self.execute("jira.api.issue.get", {"issueIdOrKey": issue_id_or_key})

    def add_comment(self, issue_id_or_key: str, comment_text: str) -> Dict[str, Any]:
        """Add a comment to an issue in Atlassian Document Format (ADF)."""
        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment_text,
                            }
                        ],
                    }
                ],
            }
        }
        return self.execute("jira.api.comment.create", {"issueIdOrKey": issue_id_or_key, "body": body})

    def update_issue(self, issue_id_or_key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on a Jira issue."""
        return self.execute("jira.api.issue.update", {"issueIdOrKey": issue_id_or_key, "body": {"fields": fields}})

    def get_project(self, project_id_or_key: str) -> Dict[str, Any]:
        """Get project details."""
        return self.execute("jira.api.project.get2", {"projectIdOrKey": project_id_or_key})
