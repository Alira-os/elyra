"""
GitHub MCP Tool Interface — Documentation Only

**DEPRECATED:** This module is kept for reference only.

As of Phase 1, GitHub operations go through Kilo with deploy_specialist persona.
Kilo has GitHub MCP connected natively — no direct `gh` CLI wrapper needed.

The Python orchestration layer (github_strategy_agent.py, promotion_pipeline.py)
builds prompts for Kilo and parses JSON output. Kilo handles the MCP tool
invocations internally.

If you need to call GitHub tools directly, use Kilo:

    from tools.kilo import invoke_kilo

    result = invoke_kilo(
        prompt="Create a GitHub repo 'my-org/my-repo' under Alira-os org",
        context={},
        working_dir="."
    )

For the GitHub MCP tool interface documentation, see the MCP server configuration
in kilo.json or the GitHub MCP provider docs.

---

Historical Interface (deprecated):

    from tools.mcp.github import create_repo, push_files

    # DO NOT USE — goes through Kilo now
    result = create_repo(name="my-repo", org="Alira-os", description="My site")
    success = push_files(repo_full_name="Alira-os/my-repo", files={...})

---

Tool Interface (for Kilo MCP documentation):

    GitHub MCP Tools:
    - github_search_repositories: Search GitHub repos
    - github_list_issues: List repository issues
    - github_create_issue: Create an issue
    - github_update_issue: Update an issue
    - github_add_issue_comment: Add comment to issue
    - github_search_issues: Search issues and PRs
    - github_get_issue: Get specific issue
    - github_create_repository: Create a new repository
    - github_fork_repository: Fork a repository
    - github_list_commits: List commits on a branch
    - github_push_files: Push files to a repo
    - github_create_branch: Create a branch
    - github_create_pull_request: Create a PR
    - github_get_pull_request: Get PR details
    - github_list_pull_requests: List PRs
    - github_merge_pull_request: Merge a PR
    - github_get_pull_request_files: Get files changed in PR
    - github_get_pull_request_status: Get PR status checks
    - github_create_pull_request_review: Create a PR review
    - github_search_code: Search code across repos
    - github_search_users: Search users
    - github_get_file_contents: Get repo file contents
    - github_create_or_update_file: Create or update file
    - github_official_push_files: Push multiple files
    - github_list_pull_request_comments: List PR review comments
    - github_get_pull_request_reviews: Get PR reviews

    All GitHub operations are invoked via Kilo's MCP integration.
    Direct gh CLI usage is deprecated in favor of Kilo + MCP.
"""

# No implementation — Kilo handles GitHub MCP internally
# Kept as documentation reference only