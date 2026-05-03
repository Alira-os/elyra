"""
Fly.io MCP Client Stub

**Phase 0 Status:** STUB — Interface only, returns mock data.
**Phase 1+ Target:** Replace with official MCP client using mcp Python SDK.

Purpose:
    Client site deployment to Fly.io.

Phase 0 Behavior:
    All functions return mock DeployResult objects.
    Functions print "[Fly.io MCP Stub]" to show what would be called.

Phase 1+ Behavior:
    Connect to Fly.io MCP server via mcp.ClientSession.
    Real operations: create_app, deploy, scale, logs, etc.

Example (Phase 1+):
    from mcp import ClientSession, StdioServerParameters

    async def deploy_site(project_dir: str) -> DeployResult:
        async with ClientSession(StdioServerParameters(
            command="npx",
            args=["-y", "@flyio/mcp-server"]
        )) as session:
            result = await session.call_tool("deploy", {"dir": project_dir})
            return DeployResult(**result)
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class FlyApp:
    id: str
    name: str
    url: str
    status: str
    created_at: str


@dataclass
class DeployResult:
    id: str
    url: str
    status: str
    deploy_url: str


class FlyMCP:
    """
    Fly.io MCP client stub.
    Phase 0: Stub implementation.
    """

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token

    async def create_app(
        self,
        name: str,
        org: str = "personal"
    ) -> FlyApp:
        """
        Create a new Fly.io app.

        Args:
            name: App name (will be subdomain)
            org: Organization (default: personal)

        Returns:
            FlyApp object
        """
        print(f"[Fly.io MCP Stub] Would create app: {name} in org: {org}")
        return FlyApp(
            id=f"stub-{name}-{hash(name) % 10000}",
            name=name,
            url=f"https://{name}.fly.dev",
            status="created",
            created_at="2026-05-02T00:00:00Z"
        )

    async def deploy(
        self,
        project_dir: str,
        app_name: Optional[str] = None
    ) -> DeployResult:
        """
        Deploy a site to Fly.io.

        Args:
            project_dir: Local directory to deploy
            app_name: Fly.io app name (creates new if not provided)

        Returns:
            DeployResult with URLs
        """
        print(f"[Fly.io MCP Stub] Would deploy {project_dir} to Fly.io")
        app_id = app_name or f"staging-{hash(project_dir) % 10000}"
        return DeployResult(
            id=f"deploy-{hash(project_dir) % 100000}",
            url=f"https://{app_id}.fly.dev",
            status="ready",
            deploy_url=f"https://{app_id}.fly.dev"
        )

    async def get_app(self, app_name: str) -> Optional[FlyApp]:
        """Get app details by name."""
        return FlyApp(
            id=f"app-{app_name}",
            name=app_name,
            url=f"https://{app_name}.fly.dev",
            status="running",
            created_at="2026-05-01T00:00:00Z"
        )

    async def scale(self, app_name: str, count: int = 1) -> bool:
        """Scale app to specified count."""
        print(f"[Fly.io MCP Stub] Would scale {app_name} to {count} instances")
        return True

    async def logs(self, app_name: str, limit: int = 100) -> list[str]:
        """Get recent logs for an app."""
        print(f"[Fly.io MCP Stub] Would fetch logs for {app_name}")
        return [f"[2026-05-02T00:00:00Z] Log entry {i}" for i in range(min(limit, 10))]


if __name__ == "__main__":
    import asyncio

    async def test():
        fly = FlyMCP()

        print("Creating app...")
        app = await fly.create_app("test-migration")
        print(f"App: {app.url}")

        print("\nDeploying...")
        result = await fly.deploy("./dist", "test-migration")
        print(f"Deploy: {result.url}")

    asyncio.run(test())