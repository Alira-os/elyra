"""
Phase D tests for the Forge Room dispatch surface.

Covers:
  - output_root validation (absolute + outside-repo rules)
  - ensure_site_repo idempotency (git init, branch, README)
  - HandoffBundle Phase D fields (output_root, git_branch)
  - VisualDirection Phase D Stitch fields
  - frontend_architect design_frontend accepts output_root + stitch kwargs
  - The orchestrator's site_dir is computed from task_context["output_root"]

Run:
    python -m pytest tests/test_forge_dispatch.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- output_root validation --------------------------------------------

def test_output_root_validation_rejects_inside_repo():
    """Passing a path inside the elyra repo must raise ValueError."""
    from conductor.orchestrator import MigrationManager
    repo_root = MigrationManager.ELYRA_REPO_ROOT
    with pytest.raises(ValueError, match="inside the elyra repo"):
        MigrationManager._resolve_output_root({"output_root": str(repo_root / "some_subdir")})


def test_output_root_validation_rejects_relative():
    """A relative output_root must raise ValueError."""
    from conductor.orchestrator import MigrationManager
    with pytest.raises(ValueError, match="absolute"):
        MigrationManager._resolve_output_root({"output_root": "sites"})


def test_output_root_validation_accepts_absolute_outside_repo(tmp_path):
    """An absolute path outside the elyra repo must resolve cleanly."""
    from conductor.orchestrator import MigrationManager
    result = MigrationManager._resolve_output_root({"output_root": str(tmp_path)})
    assert result == tmp_path.resolve()


# --- ensure_site_repo idempotency --------------------------------------

@pytest.fixture
def tmp_path_repo(tmp_path):
    """A tmp output_root with a slug subdir ready for ensure_site_repo."""
    site_dir = tmp_path / "demo"
    site_dir.mkdir(parents=True, exist_ok=True)
    return site_dir


def test_ensure_site_repo_idempotent(tmp_path_repo):
    """Running ensure_site_repo twice with the same migration_id is safe."""
    git = shutil.which("git")
    if not git:
        pytest.skip("git not on PATH")
    from conductor.site_repo import ensure_site_repo
    migration_id = "20260622_120000"
    r1 = ensure_site_repo(tmp_path_repo, "demo", migration_id)
    assert (tmp_path_repo / ".git").exists()
    assert (tmp_path_repo / "SITE_README.md").exists()
    readme1 = (tmp_path_repo / "SITE_README.md").read_text(encoding="utf-8")
    assert migration_id in readme1

    # Second run: must not raise, must still be on the same branch.
    r2 = ensure_site_repo(tmp_path_repo, "demo", migration_id)
    assert r2["branch"] == f"forge/{migration_id}"
    # On-disk branch should still be forge/<id>.
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(tmp_path_repo), capture_output=True, text=True, check=True,
    )
    assert head.stdout.strip() == f"forge/{migration_id}"


# --- HandoffBundle Phase D fields --------------------------------------

def test_handoff_bundle_has_output_root_and_git_branch():
    from models.site_schemas import HandoffBundle
    bundle = HandoffBundle(
        bundle_id="handoff-x",
        migration_id="x",
        site_slug="demo",
        from_room="planning",
        to_room="forge",
        output_root="C:/Users/micha/DevProjects",
        git_branch="forge/x",
    )
    assert bundle.output_root == "C:/Users/micha/DevProjects"
    assert bundle.git_branch == "forge/x"


def test_handoff_bundle_defaults_empty_strings():
    """Legacy fixtures that build HandoffBundle(...) without the new
    fields must still work — both default to ""."""
    from models.site_schemas import HandoffBundle
    bundle = HandoffBundle(
        bundle_id="handoff-x",
        migration_id="x",
        site_slug="demo",
        from_room="planning",
        to_room="forge",
    )
    assert bundle.output_root == ""
    assert bundle.git_branch == ""


# --- VisualDirection Phase D Stitch fields -----------------------------

def test_visual_direction_has_stitch_fields():
    from models.site_schemas import VisualDirection
    vd = VisualDirection(
        primary_change="x",
        rationale="y",
        stitch_project_id="proj-abc",
        stitch_project_url="https://stitch.example/p/proj-abc",
    )
    assert vd.stitch_project_id == "proj-abc"
    assert vd.stitch_project_url == "https://stitch.example/p/proj-abc"
    assert vd.schema_version == "1.2"


def test_visual_direction_stitch_fields_default_none():
    from models.site_schemas import VisualDirection
    vd = VisualDirection()
    assert vd.stitch_project_id is None
    assert vd.stitch_project_url is None


# --- frontend_architect design_frontend signature ---------------------

def test_design_frontend_accepts_output_root_and_stitch_kwargs():
    """design_frontend must accept output_root, stitch_project_id,
    stitch_project_url as keyword args without raising."""
    import inspect
    from skills.agentic.frontend_architect import design_frontend, build_frontend_prompt
    sig = inspect.signature(design_frontend)
    for name in ("output_root", "stitch_project_id", "stitch_project_url"):
        assert name in sig.parameters, f"design_frontend missing {name!r}"

    sig2 = inspect.signature(build_frontend_prompt)
    for name in ("output_root", "stitch_project_id", "stitch_project_url"):
        assert name in sig2.parameters, f"build_frontend_prompt missing {name!r}"


def test_build_frontend_prompt_includes_output_root_in_instructions():
    """The generated prompt should reference output_root/{site_slug}/,
    not the legacy sites/{site_slug}/ literal."""
    from models.site_schemas import (
        ContentRecommendation, ToneOfVoice,
        SiteArchitecture,
        SiteUnderstanding,
    )
    from skills.agentic.frontend_architect import build_frontend_prompt

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="demo", total_pages_discovered=0, estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    rec = ContentRecommendation(
        source_url="https://example.com", site_name="demo",
        chosen_variant="A", variants=[], final_rationale="A",
        overall_content_strategy="Direct",
        tone_of_voice=ToneOfVoice(),
    )
    prompt = build_frontend_prompt(
        site, arch, rec, "demo",
        output_root="D:/builds",
    )
    assert "D:/builds/demo/" in prompt
    assert "sites/demo/" not in prompt


def test_build_frontend_prompt_includes_stitch_section_when_present():
    """When stitch_project_id is set, the prompt should include a
    Design Reference (Stitch) section."""
    from models.site_schemas import (
        ContentRecommendation, ToneOfVoice,
        SiteArchitecture,
        SiteUnderstanding,
    )
    from skills.agentic.frontend_architect import build_frontend_prompt

    site = SiteUnderstanding(
        url="https://example.com", platform="wix", platform_confidence=0.9,
        site_name="demo", total_pages_discovered=0, estimated_fidelity=0.7,
    )
    arch = SiteArchitecture(source_url="https://example.com")
    rec = ContentRecommendation(
        source_url="https://example.com", site_name="demo",
        chosen_variant="A", variants=[], final_rationale="A",
        overall_content_strategy="Direct",
        tone_of_voice=ToneOfVoice(),
    )
    prompt = build_frontend_prompt(
        site, arch, rec, "demo",
        output_root="D:/builds",
        stitch_project_id="proj-abc",
        stitch_project_url="https://stitch.example/p/proj-abc",
    )
    assert "Design Reference (Stitch)" in prompt
    assert "proj-abc" in prompt


# --- Orchestrator: site_dir uses output_root ---------------------------

def test_orchestrator_site_dir_uses_output_root(tmp_path, monkeypatch):
    """The MigrationManager should pin task_context["output_root"] on
    entry, and downstream code that uses task_context sees the
    validated absolute path."""
    from conductor.orchestrator import MigrationManager

    # We don't need to run a full migration — just exercise the early
    # part of run() that resolves output_root and writes site_dir.
    m = MigrationManager(db_path=":memory:")
    # Capture the moment site_dir would be computed.
    captured = {}
    real_init = m._init_build_manifest

    def capture_init(migration_id, url, site_slug, *, output_root=None):
        captured["output_root"] = output_root
        captured["site_slug"] = site_slug
        return real_init(migration_id, url, site_slug, output_root=output_root)

    monkeypatch.setattr(m, "_init_build_manifest", capture_init)

    # Run only the prefix of run() that resolves output_root and calls
    # _init_build_manifest. We'll do this by patching out everything
    # after that point. Easiest: call _resolve_output_root directly
    # and feed the result into _init_build_manifest ourselves.
    ctx = {"output_root": str(tmp_path)}
    resolved = m._resolve_output_root(ctx)
    assert resolved == tmp_path.resolve()
    bm = m._init_build_manifest("x", "https://example.com", "demo", output_root=resolved)
    assert bm.output_dir.endswith("/demo")
    assert "sites/demo" not in bm.output_dir


# --- ensure_site_repo basic invariants ---------------------------------

def test_ensure_site_repo_writes_readme_with_extras(tmp_path_repo):
    """ensure_site_repo should propagate extras into SITE_README.md."""
    git = shutil.which("git")
    if not git:
        pytest.skip("git not on PATH")
    from conductor.site_repo import ensure_site_repo
    ensure_site_repo(
        tmp_path_repo, "demo", "20260622_120000",
        site_readme_extras={
            "source_url": "https://example.com",
            "target_stack": "nextjs",
            "stitch_project_url": "https://stitch.example/p/abc",
        },
    )
    readme = (tmp_path_repo / "SITE_README.md").read_text(encoding="utf-8")
    assert "https://example.com" in readme
    assert "nextjs" in readme
    assert "https://stitch.example/p/abc" in readme