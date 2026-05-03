"""
Netlify MCP Client Stub

**Phase 0 Status:** STUB — Interface only, returns mock data.
**Phase 1+ Target:** Replace with official MCP client using mcp Python SDK.

Purpose:
    Netlify site creation, deployment, domain configuration.

Phase 0 Behavior:
    All functions return mock NetlifySite/DeployResult objects.
    Functions print "[Netlify MCP Stub]" to show what would be called.

Phase 1+ Behavior:
    Connect to Netlify MCP server via mcp.ClientSession.
    Real operations: create_site, deploy_site, configure_build, etc.

Example (Phase 1+):
    from mcp import ClientSession, StdioServerParameters

    async def deploy_site(project_dir: str) -> DeployResult:
        async with ClientSession(StdioServerParameters(
            command="npx",
            args=["-y", "@netlify/mcp-server"]
        )) as session:
            result = await session.call_tool("deploy", {"dir": project_dir})
            return DeployResult(**result)
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class NetlifySite:
    id: str
    name: str
    url: str
    state: str
    created_at: str


@dataclass
class DeployResult:
    id: str
    url: str
    status: str
    deploy_url: str


class NetlifyMCP:
    """
    Netlify MCP client stub.

    Phase 0: Stub implementation. Full MCP integration comes Phase 1.
    """

    def __init__(self, auth_token: Optional[str] = None, site_id: Optional[str] = None):
        self.auth_token = auth_token
        self.site_id = site_id
        self.base_url = "https://api.netlify.com/api/v1"

    async def create_site(
        self,
        name: str,
        team: str = "personal",
        plan: str = "starter"
    ) -> NetlifySite:
        """
        Create a new Netlify site.

        Args:
            name: Site name (subdomain)
            team: Team slug
            plan: Pricing plan

        Returns:
            NetlifySite object

        Stub returns mock data.
        """
        return NetlifySite(
            id=f"stub-{name}-{hash(name) % 10000}",
            name=name,
            url=f"https://{name}.netlify.app",
            state="created",
            created_at="2026-05-01T00:00:00Z"
        )

    async def configure_build(
        self,
        site_id: str,
        build_command: str = "npm run build",
        publish_dir: str = "out",
        node_version: str = "20"
    ) -> bool:
        """
        Configure build settings for a site.

        Args:
            site_id: Netlify site ID
            build_command: Build command
            publish_dir: Publish directory
            node_version: Node.js version

        Returns:
            True if successful
        """
        return True

    async def deploy_site(
        self,
        project_dir: str,
        site_id: Optional[str] = None,
        production: bool = False
    ) -> DeployResult:
        """
        Deploy a site to Netlify.

        Args:
            project_dir: Local directory to deploy
            site_id: Netlify site ID (creates new if not provided)
            production: Whether to deploy to production URL

        Returns:
            DeployResult with URLs
        """
        site_name = f"staging-{hash(project_dir) % 10000}"
        return DeployResult(
            id=f"deploy-{hash(project_dir) % 100000}",
            url=f"https://{site_name}.netlify.app",
            status="ready",
            deploy_url=f"https://{site_name}.netlify.app"
        )

    async def get_site(self, site_id: str) -> NetlifySite:
        """Get site details by ID."""
        return NetlifySite(
            id=site_id,
            name="site",
            url=f"https://{site_id}.netlify.app",
            state="ready",
            created_at="2026-05-01T00:00:00Z"
        )

    async def add_domain(self, site_id: str, domain: str) -> bool:
        """Add custom domain to a site."""
        return True

    async def setup_ssl(self, site_id: str, domain: str) -> bool:
        """Setup SSL for custom domain."""
        return True

    async def deploy_production(self, site_id: str) -> DeployResult:
        """Switch staging site to production."""
        return DeployResult(
            id=f"prod-{hash(site_id) % 100000}",
            url=f"https://{site_id}.netlify.app",
            status="ready",
            deploy_url=f"https://{site_id}.netlify.app"
        )


if __name__ == "__main__":
    import asyncio

    async def test():
        netlify = NetlifyMCP()

        print("Creating site...")
        site = await netlify.create_site("test-migration")
        print(f"Site: {site.url}")

        print("\nDeploying...")
        result = await netlify.deploy_site("./dist")
        print(f"Deploy: {result.url}")

    asyncio.run(test())