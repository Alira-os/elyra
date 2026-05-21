"""
ui_polish.py — Phase 3 UI Polish Skill

A reusable visual quality pass that inspects generated component and page files,
directly modifies them for visual excellence, and logs every change with a specific
reason tracing back to the BrandSpec.

This is a callable skill (not an agent). It expects file paths and a BrandSpec as input
and returns a list of PolishChange objects.

Usage:
    from skills.ui_polish import polish_directory
    changes = polish_directory("output/", brand_spec)
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import re

from models.site_schemas import BrandSpec, PolishChange


MOTION_MAPPING = {
    "monastic": {
        "duration": "200ms",
        "easing": "ease-out",
        "allowed_transforms": ["opacity", "translateY"],
        "scale_on_hover": False,
        "description": "very restrained: opacity + translateY only, 200-300ms ease-out, no scale transforms",
    },
    "classical": {
        "duration": "400ms",
        "easing": "ease-out",
        "allowed_transforms": ["opacity", "translateY", "scale"],
        "scale_on_hover": 1.02,
        "description": "elegant: 400ms ease-out, subtle scale(1.02) on hover, gentle spring on modals",
    },
    "energetic": {
        "duration": "150ms",
        "easing": "ease-in-out",
        "allowed_transforms": ["opacity", "translateY", "scale", "box-shadow"],
        "scale_on_hover": 1.05,
        "description": "bolder: 150ms, scale(1.05) + shadow elevation, micro-bounce on CTAs",
    },
    "subtle": {
        "duration": "150-200ms",
        "easing": "ease",
        "allowed_transforms": ["opacity"],
        "scale_on_hover": False,
        "description": "minimal tasteful motion: 150-200ms ease, small opacity fades",
    },
}


def get_motion_spec(philosophy: str) -> Dict[str, Any]:
    """Get motion specification for a given philosophy."""
    return MOTION_MAPPING.get(philosophy, MOTION_MAPPING["subtle"])


def check_spacing_consistency(content: str, brand_spec: BrandSpec) -> List[str]:
    """Check for hardcoded spacing that doesn't match BrandSpec spacing_scale."""
    issues = []
    spacing = brand_spec.spacing_scale or {}

    hardcoded_gaps = re.findall(r"\bgap-(?:px|[0-9]+)\b", content)
    if spacing and hardcoded_gaps:
        for gap in set(hardcoded_gaps):
            issues.append(f"Hardcoded spacing '{gap}' found — should use BrandSpec spacing_scale tokens")

    return issues


def check_color_tokens(content: str, brand_spec: BrandSpec) -> List[str]:
    """Check for hardcoded hex values that should be CSS variables."""
    issues = []
    tokens = brand_spec.semantic_tokens or {}

    hex_pattern = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
    hardcoded_colors = hex_pattern.findall(content)
    if tokens and hardcoded_colors:
        for color in set(hardcoded_colors):
            if color not in tokens.values():
                issues.append(f"Hardcoded color '{color}' found — should use BrandSpec semantic token")

    return issues


def check_motion_philosophy(content: str, brand_spec: BrandSpec) -> List[str]:
    """Check that transition values match the motion philosophy."""
    issues = []
    philosophy = brand_spec.motion_philosophy or "subtle"
    spec = get_motion_spec(philosophy)

    duration_match = re.search(r"transition-duration:\s*([0-9]+)ms", content)
    if duration_match:
        duration_ms = int(duration_match.group(1))
        min_ms = int(spec["duration"].split("-")[0].replace("ms", ""))
        max_ms = int(spec["duration"].split("-")[1].replace("ms", "")) if "-" in spec["duration"] else min_ms

        if not (min_ms <= duration_ms <= max_ms + 50):
            issues.append(
                f"Transition duration {duration_ms}ms doesn't match '{philosophy}' philosophy "
                f"(expected ~{spec['duration']})"
            )

    if spec["scale_on_hover"] is False:
        if "scale(" in content and "hover" in content:
            issues.append(
                f"scale() transform on hover found but motion philosophy is '{philosophy}' "
                f"which should not use scale transforms"
            )

    return issues


def check_focus_states(content: str) -> List[str]:
    """Check for visible focus states."""
    issues = []

    if "outline: none" in content or "outline: none" in content:
        if "focus-visible" not in content and ":focus" not in content:
            issues.append("'outline: none' found without focus-visible alternative — accessibility issue")

    if "<button" in content or "<a " in content:
        if "focus" not in content.lower() and "focus-visible" not in content.lower():
            issues.append("Interactive elements missing focus styles")

    return issues


def check_form_labels(content: str) -> List[str]:
    """Check that form fields have proper labels."""
    issues = []

    input_tags = re.findall(r"<input[^>]*>", content)
    for inp in input_tags:
        if "aria-label" not in inp and "aria-labelledby" not in inp and 'placeholder="' not in inp:
            issues.append(f"Input found without visible label or aria-label: {inp[:100]}")

    return issues


def check_semantic_html(content: str) -> List[str]:
    """Check for proper semantic HTML usage."""
    issues = []

    if "<div" in content and ("onClick" in content or "role=" in content):
        issues.append("div with onClick found — use <button> for interactive elements")

    return issues


def check_reduced_motion(content: str) -> List[str]:
    """Check for reduced motion media query."""
    issues = []

    if "transition" in content or "animation" in content:
        if "@media (prefers-reduced-motion" not in content:
            issues.append(
                "Motion found but no '@media (prefers-reduced-motion: reduce)' query — "
                "accessibility requirement"
            )

    return issues


def polish_directory(output_dir: Path, brand_spec: BrandSpec) -> List[PolishChange]:
    """
    Main entry point for the ui_polish skill.

    Scans all .tsx and .css files in the output directory for common visual issues,
    returns a list of PolishChange objects describing what should be fixed.

    Note: This skill is a static analyzer. It identifies issues and logs them.
    The actual code modification is done by the Builder persona (which calls this skill
    and applies the changes) or by a separate ui_polish agent pass.

    Args:
        output_dir: Path to the generated site output directory
        brand_spec: BrandSpec containing design tokens and motion philosophy

    Returns:
        List of PolishChange objects describing suggested fixes
    """
    if not output_dir.exists():
        return []

    changes = []
    tsx_files = list(output_dir.rglob("*.tsx"))
    css_files = list(output_dir.rglob("*.css"))

    for fpath in tsx_files + css_files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        rel_path = str(fpath.relative_to(output_dir))

        spacing_issues = check_spacing_consistency(content, brand_spec)
        for issue in spacing_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="spacing adjustment needed",
                    reason=issue,
                    brand_spec_reference="spacing_scale",
                )
            )

        color_issues = check_color_tokens(content, brand_spec)
        for issue in color_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="color token substitution needed",
                    reason=issue,
                    brand_spec_reference="semantic_tokens or primary_color",
                )
            )

        motion_issues = check_motion_philosophy(content, brand_spec)
        for issue in motion_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="motion duration/easing adjustment",
                    reason=issue,
                    brand_spec_reference=f"motion_philosophy: {brand_spec.motion_philosophy}",
                )
            )

        focus_issues = check_focus_states(content)
        for issue in focus_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="focus state fix",
                    reason=issue,
                    brand_spec_reference="accessibility",
                )
            )

        form_issues = check_form_labels(content)
        for issue in form_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="form label accessibility fix",
                    reason=issue,
                    brand_spec_reference="accessibility",
                )
            )

        semantic_issues = check_semantic_html(content)
        for issue in semantic_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="semantic HTML fix",
                    reason=issue,
                    brand_spec_reference="accessibility",
                )
            )

        reduced_motion_issues = check_reduced_motion(content)
        for issue in reduced_motion_issues:
            changes.append(
                PolishChange(
                    file=rel_path,
                    change="add reduced motion media query",
                    reason=issue,
                    brand_spec_reference="accessibility",
                )
            )

    return changes


if __name__ == "__main__":
    import sys
    from models.site_schemas import BrandSpec

    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output")
    if not output_dir.exists():
        print(f"Usage: python ui_polish.py <output_dir>")
        sys.exit(1)

    brand_spec = BrandSpec()
    changes = polish_directory(output_dir, brand_spec)

    if not changes:
        print("[POLISH] No issues found")
    else:
        print(f"[POLISH] {len(changes)} issues found:")
        for c in changes:
            print(f"  [{c.file}] {c.change} — {c.reason}")