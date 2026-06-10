"""
test_devops_engineer_hardening.py

Phase 1.1 hardening tests for the devops_engineer persona:
  - Uses the new small `deploy_engineer.md` persona (not the legacy
    GitHub-strategy `deploy_specialist.md`).
  - Prompt stays under a sane budget (well under the 40K refuse-line).
  - Lenient-parse recovers common Kilo output pathologies.
  - design_deploy_spec end-to-end with a stubbed Kilo.

Run:
    python -m pytest tests/test_devops_engineer_hardening.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _site():
    from models.site_schemas import SiteUnderstanding
    return SiteUnderstanding(
        url="https://example.com",
        platform="wix",
        platform_confidence=0.9,
        site_name="example",
        total_pages_discovered=1,
        pages=[],
        global_assets={},
        contact_info={},
        navigation_structure=[],
        estimated_fidelity=0.7,
    )


def _arch():
    from models.site_schemas import SiteArchitecture
    return SiteArchitecture(source_url="https://example.com")


def test_devops_uses_purpose_built_persona():
    from skills.agentic.devops_engineer import build_devops_prompt
    prompt = build_devops_prompt(_site(), _arch())
    assert "DeploySpec" in prompt
    assert '"fly"' in prompt
    assert '"cloudflare_pages"' in prompt
    assert "Tier-1 Triggers" not in prompt
    assert "wrangler" not in prompt.lower()
    assert "wait_for_approval" not in prompt


def test_deploy_engineer_markdown_exists():
    p = Path("registry/personas/deploy_engineer.md")
    assert p.exists(), f"missing {p}"
    text = p.read_text(encoding="utf-8")
    assert len(text) < 10_000, f"deploy_engineer.md is {len(text)} bytes (too big)"
    assert "DeploySpec" in text


def test_deploy_specialist_markdown_unchanged():
    p = Path("registry/personas/deploy_specialist.md")
    text = p.read_text(encoding="utf-8")
    assert "Tier-1 Triggers" in text
    assert "wrangler" in text.lower()


def test_devops_prompt_under_budget():
    from skills.agentic.devops_engineer import build_devops_prompt
    prompt = build_devops_prompt(_site(), _arch())
    assert len(prompt) < 20_000, f"prompt is {len(prompt)} chars"


def test_lenient_parse_strict_json():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    out = _lenient_parse_deploy_spec('{"platform": "fly", "site_slug": "x"}')
    assert out == {"platform": "fly", "site_slug": "x"}


def test_lenient_parse_fenced_block():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    out = _lenient_parse_deploy_spec(
        "Here is the spec:\n```json\n"
        '{"platform": "vercel", "site_slug": "x"}\n'
        "```\nDone."
    )
    assert out == {"platform": "vercel", "site_slug": "x"}


def test_lenient_parse_truncated_mid_object():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    truncated = (
        '{"platform": "cloudflare_pages", "site_slug": "example", '
        '"target_spec": {"region": "auto"}, "scaling": '
        '{"min_instances": 0, "max_instances": 1}, "monitoring": '
        '["uptime_check"], "security": ["https_only"], "ci_cd": '
        '["github_actions"]'
    )
    out = _lenient_parse_deploy_spec(truncated)
    assert out is not None
    assert out["platform"] == "cloudflare_pages"
    assert out["site_slug"] == "example"
    assert "uptime_check" in out["monitoring"]


def test_lenient_parse_truncated_mid_string():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    truncated = (
        '{"platform": "fly", "site_slug": "x", "notes": "this site is'
    )
    out = _lenient_parse_deploy_spec(truncated)
    assert out is not None
    assert out["platform"] == "fly"
    assert "notes" in out


def test_lenient_parse_prose_wrapped():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    out = _lenient_parse_deploy_spec(
        'I picked cloudflare_pages. Spec: {"platform": '
        '"cloudflare_pages", "site_slug": "blog"}'
    )
    assert out is not None
    assert out["platform"] == "cloudflare_pages"


def test_lenient_parse_returns_none_for_garbage():
    from skills.agentic.devops_engineer import _lenient_parse_deploy_spec
    assert _lenient_parse_deploy_spec("") is None
    assert _lenient_parse_deploy_spec("not json at all") is None
    assert _lenient_parse_deploy_spec("[1, 2, 3]") is None


def test_design_deploy_spec_happy_path(monkeypatch):
    from models.site_schemas import DeploySpec
    from skills.agentic import devops_engineer

    valid = {
        "migration_id": "m1",
        "site_slug": "example",
        "platform": "cloudflare_pages",
        "target_spec": {},
        "scaling": {"min_instances": 0, "max_instances": 1},
        "monitoring": ["uptime_check"],
        "security": ["https_only", "hsts_enabled", "secrets_in_env"],
        "ci_cd": ["github_actions", "prod_deploy_on_main"],
        "notes": "Static site, edge cached.",
        "reasoning_trace": ["Static brochure; no CMS."],
    }

    monkeypatch.setattr(
        devops_engineer, "save_artifact_to_dir", lambda *a, **kw: "20260608_180000"
    )
    with patch.object(
        devops_engineer, "invoke_kilo_for_persona", return_value=(json.dumps(valid), None)
    ):
        spec = devops_engineer.design_deploy_spec(
            _site(), _arch(), migration_id="m1", site_slug="example"
        )
    assert isinstance(spec, DeploySpec)
    assert spec.platform == "cloudflare_pages"
    assert spec.produced_by == "deploy_engineer"
    assert "https_only" in spec.security


def test_design_deploy_spec_recovers_from_truncated_output(monkeypatch):
    from models.site_schemas import DeploySpec
    from skills.agentic import devops_engineer

    truncated = (
        '{"migration_id": "m1", "platform": "cloudflare_pages", '
        '"site_slug": "example", '
        '"target_spec": {"region": "auto"}, "scaling": '
        '{"min_instances": 0, "max_instances": 1}, "monitoring": '
        '["uptime_check"], "security": ["https_only"], "ci_cd": '
        '["github_actions"]'
    )

    call_count = {"n": 0}

    def fake_invoke(*args, **kwargs):
        call_count["n"] += 1
        return (truncated, None)

    monkeypatch.setattr(
        devops_engineer, "save_artifact_to_dir", lambda *a, **kw: "20260608_180000"
    )
    with patch.object(devops_engineer, "invoke_kilo_for_persona", side_effect=fake_invoke):
        spec = devops_engineer.design_deploy_spec(
            _site(), _arch(), migration_id="m1", site_slug="example"
        )
    assert isinstance(spec, DeploySpec), f"got {spec!r}, call_count={call_count['n']}"
    assert spec.platform == "cloudflare_pages"
    assert call_count["n"] == 1


def test_design_deploy_spec_retries_on_garbage(monkeypatch):
    from models.site_schemas import DeploySpec
    from skills.agentic import devops_engineer

    valid = {
        "migration_id": "m1",
        "site_slug": "example",
        "platform": "vercel",
        "target_spec": {"framework": "nextjs"},
        "scaling": {"min_instances": 0, "max_instances": 4},
        "monitoring": ["uptime_check", "lighthouse_on_deploy"],
        "security": ["https_only", "hsts_enabled", "secrets_in_env"],
        "ci_cd": ["github_actions", "preview_env_on_pr", "prod_deploy_on_main"],
        "notes": "Next.js app on Vercel.",
    }

    responses = [("not json at all", None), (json.dumps(valid), None)]

    def fake_invoke(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(
        devops_engineer, "save_artifact_to_dir", lambda *a, **kw: "20260608_180000"
    )
    with patch.object(devops_engineer, "invoke_kilo_for_persona", side_effect=fake_invoke):
        spec = devops_engineer.design_deploy_spec(
            _site(), _arch(), migration_id="m1", site_slug="example"
        )
    assert isinstance(spec, DeploySpec)
    assert spec.platform == "vercel"


def test_design_deploy_spec_returns_none_when_both_calls_fail(monkeypatch):
    from skills.agentic import devops_engineer

    def fake_invoke(*args, **kwargs):
        return (None, None)

    gaps = []

    def fake_gap(**kwargs):
        gaps.append(kwargs)

    monkeypatch.setattr(
        devops_engineer, "save_artifact_to_dir", lambda *a, **kw: "20260608_180000"
    )
    monkeypatch.setattr(
        devops_engineer, "make_failed_invocation_gap", fake_gap
    )
    with patch.object(devops_engineer, "invoke_kilo_for_persona", side_effect=fake_invoke):
        spec = devops_engineer.design_deploy_spec(
            _site(), _arch(), migration_id="m1", site_slug="example"
        )
    assert spec is None
    assert len(gaps) == 1
    assert gaps[0]["persona"] == "deploy_engineer"
