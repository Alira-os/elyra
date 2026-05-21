"""
Fly.io MCP Tool Interface — Documentation Only

**DEPRECATED:** This module is kept for reference only.

As of Phase 1, Fly.io operations go through Kilo with deploy_specialist persona.
Kilo has Fly.io MCP connected natively — no direct `flyctl` CLI wrapper needed.

The Python orchestration layer (promotion_pipeline.py) builds prompts for Kilo
and parses JSON output. Kilo handles the MCP tool invocations internally.

If you need to call Fly.io tools directly, use Kilo:

    from tools.kilo import invoke_kilo

    result = invoke_kilo(
        prompt="Create a Fly.io app named 'my-app' in org=personal region=lax",
        context={},
        working_dir="."
    )

For the Fly.io MCP tool interface documentation, see the MCP server configuration
in kilo.json or the Fly.io MCP provider docs.

---

Historical Interface (deprecated):

    from tools.mcp.fly import create_app, deploy

    # DO NOT USE — goes through Kilo now
    app = create_app(name="my-app", org="personal", region="lax")
    result = deploy(app_name="my-app", project_dir="./build")

---

Tool Interface (for Kilo MCP documentation):

    Fly.io MCP Tools:
    - fly_apps_list: List all Fly.io apps
    - fly_apps_create: Create a new Fly app
    - fly_machine_list: List machines for an app
    - fly_machine_run: Run a machine
    - fly_machine_destroy: Destroy a machine
    - fly_ips_allocate_v4: Allocate IPv4 address
    - fly_ips_list: List IP addresses for an app
    - fly_secrets_set: Set app secrets
    - fly_secrets_list: List app secrets (names only)
    - fly_logs: Get app logs

    All Fly.io operations are invoked via Kilo's MCP integration.
    Direct flyctl CLI usage is deprecated in favor of Kilo + MCP.
"""

# No implementation — Kilo handles Fly.io MCP internally
# Kept as documentation reference only