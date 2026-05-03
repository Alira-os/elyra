"""
GitHub MCP Client Stub

**Phase 0 Status:** STUB — Interface only, returns mock data.
**Phase 1+ Target:** Replace with official MCP client using mcp Python SDK.

Purpose:
    GitHub repository creation, file push, Actions workflow trigger.

Phase 0 Behavior:
    All functions return mock RepoInfo/WorkflowRun objects.
    Functions print "[GitHub MCP Stub]" to show what would be called.

Phase 1+ Behavior:
    Connect to GitHub MCP server via mcp.ClientSession.
    Real operations: create_repo, push_files, trigger_workflow, etc.

Example (Phase 1+):
    from mcp import ClientSession, StdioServerParameters

    async def create_repo(name: str) -> RepoInfo:
        async with ClientSession(StdioServerParameters(
            command="npx",
            args=["-y", "@github/mcp-server"]
        )) as session:
            result = await session.call_tool("create_repo", {"name": name})
            return RepoInfo(**result)
"""

import json
from typing import Optional
from dataclasses import dataclass


@dataclass
class RepoInfo:
    url: str
    name: str
    owner: str
    private: bool


@dataclass
class WorkflowRun:
    id: int
    status: str
    conclusion: Optional[str]
    url: str


class GitHubMCP:
    """
    GitHub MCP client stub.

    Phase 0: Stub implementation. Full MCP integration comes Phase 1.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"

    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = False
    ) -> RepoInfo:
        """
        Create a GitHub repository.

        Args:
            name: Repository name
            description: Repository description
            private: Whether repo should be private
            auto_init: Whether to initialize with README

        Returns:
            RepoInfo with repository details

        Stub returns mock data.
        """
        return RepoInfo(
            url=f"https://github.com/merimeesoftware/{name}",
            name=name,
            owner="merimeesoftware",
            private=private
        )

    async def push_files(
        self,
        repo_url: str,
        files: dict,
        branch: str = "main",
        message: str = "Initial commit via Elyra"
    ) -> bool:
        """
        Push files to a GitHub repository.

        Args:
            repo_url: Full repository URL
            files: Dict of {filename: content}
            branch: Branch to push to
            message: Commit message

        Returns:
            True if successful

        Stub always returns True.
        """
        print(f"[GitHub MCP Stub] Would push {len(files)} files to {repo_url}")
        return True

    async def protect_branch(
        self,
        repo_url: str,
        branch: str = "main",
        require_reviews: bool = True
    ) -> bool:
        """
        Enable branch protection.

        Args:
            repo_url: Repository URL
            branch: Branch name
            require_reviews: Require PR reviews

        Returns:
            True if successful
        """
        return True

    async def trigger_workflow(
        self,
        repo_url: str,
        workflow_name: str
    ) -> WorkflowRun:
        """
        Trigger a GitHub Actions workflow.

        Args:
            repo_url: Repository URL
            workflow_name: Name of workflow file (without .yml)

        Returns:
            WorkflowRun object
        """
        return WorkflowRun(
            id=12345,
            status="queued",
            conclusion=None,
            url=f"{repo_url}/actions/runs/12345"
        )

    async def wait_for_workflow(
        self,
        run_id: int,
        timeout: int = 600
    ) -> WorkflowRun:
        """
        Wait for workflow to complete.

        Args:
            run_id: Workflow run ID
            timeout: Timeout in seconds

        Returns:
            WorkflowRun with final status
        """
        return WorkflowRun(
            id=run_id,
            status="completed",
            conclusion="success",
            url=f"https://github.com/actions/runs/{run_id}"
        )

    async def get_workflow_status(self, repo_url: str, run_id: int) -> WorkflowRun:
        """Get workflow run status."""
        return WorkflowRun(
            id=run_id,
            status="completed",
            conclusion="success",
            url=f"{repo_url}/actions/runs/{run_id}"
        )


if __name__ == "__main__":
    import asyncio

    async def test():
        gh = GitHubMCP()

        print("Creating repo...")
        repo = await gh.create_repo("test-site", "Test migration")
        print(f"Repo: {repo.url}")

        print("\nPushing files...")
        result = await gh.push_files(repo.url, {"index.html": "<html></html>"})
        print(f"Push result: {result}")

        print("\nTriggering workflow...")
        wf = await gh.trigger_workflow(repo.url, "deploy")
        print(f"Workflow: {wf.url}")

    asyncio.run(test())