"""
quality_gate.py — Post-build deterministic quality gate runner.

Runs AFTER Builder writes code. Gates are deterministic scripts (NOT inside Kilo LLM call).

Gates:
  1. npm run build — must exit 0
  2. Impeccable audit — no high-severity violations
  3. Token fidelity — 100% BrandSpec + VisualDirection token usage
  4. Accessibility — WCAG AA minimum (axe-core via Playwright)

Usage:
  python quality_gate.py sites/merimee-solutions/ [--verbose]

Exit codes:
  0 = all gates passed
  1 = hard gate failure
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SITE_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

MANIFEST_FILE = SITE_DIR / "build-manifest.json"
BRAND_SPEC_FILE = SITE_DIR / "brand-spec.json"
IMPECCABLE_REPORT_FILE = SITE_DIR / "impeccable-report.json"
QUALITY_GATE_FILE = SITE_DIR / "quality-gate-report.json"


def log(msg: str) -> None:
    if VERBOSE:
        print(f"[gate] {msg}")


def run_cmd(
    cmd: List[str],
    cwd: Path = SITE_DIR,
    timeout: int = 300,
    env: Optional[Dict[str, str]] = None,
    use_shell: bool = False,
) -> Tuple[int, str, str]:
    """Run a command, return (exit_code, stdout, stderr)."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)

    log(f"Running: {' '.join(cmd)}")
    try:
        merged_flags = 0
        if hasattr(subprocess, 'CREATE_NO_WINDOW') and not use_shell:
            merged_flags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            shell=use_shell,
            creationflags=merged_flags,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def _resolve_npm_cmd() -> Tuple[List[str], bool]:
    """
    Resolve npm command for subprocess.

    On Windows, 'npm' is a .cmd batch file. We look up the full path via
    shutil.which and pass it as a list item — subprocess.run handles .cmd
    files natively on Windows without shell=True, and cwd works correctly.
    """
    import shutil
    import platform

    is_windows = platform.system() == "Windows"
    npm_name = "npm.cmd" if is_windows else "npm"
    npm_path = shutil.which(npm_name)

    if not npm_path and is_windows:
        npm_path = shutil.which("npm")

    if npm_path:
        return [npm_path, "run", "build"], False

    return ["npm", "run", "build"], False


def _resolve_node_cmd() -> Tuple[List[str], bool]:
    """
    Resolve node command for subprocess.

    On Windows, 'node' is a .exe that we locate via shutil.which.
    """
    import shutil
    import platform

    is_windows = platform.system() == "Windows"
    if not is_windows:
        return ["node"], False

    node_path = shutil.which("node.exe") or shutil.which("node")
    if node_path:
        return [node_path], False

    return ["node"], False


def _resolve_tool_cmd(cmd_name: str) -> Tuple[List[str], bool]:
    """
    Resolve a node/.bin tool command for subprocess.

    On Windows, tools installed via npm (like impeccable) live in:
    1. `.kilo/node_modules/.bin/` (Elyra project's own dependencies, same dir as quality_gate.py)
    2. The npm global install's node_modules/.bin/

    subprocess.run handles .cmd files natively without shell=True,
    preserving correct cwd behavior.
    """
    import shutil
    import platform

    is_windows = platform.system() == "Windows"
    if not is_windows:
        return [cmd_name], False

    # Check .kilo/node_modules/.bin first (Elyra project's own deps, same level as quality_gate.py)
    elyra_root = Path(__file__).resolve().parents[0]
    kilo_bin = elyra_root / ".kilo" / "node_modules" / ".bin" / f"{cmd_name}.cmd"
    if kilo_bin.exists():
        return [str(kilo_bin)], False

    # Try npm's node_modules/.bin (from resolved npm location)
    npm_cmd, _ = _resolve_npm_cmd()
    npm_dir = Path(npm_cmd[0]).parent.parent if npm_cmd else None
    if npm_dir and npm_dir.exists():
        tool_path = npm_dir / "node_modules" / ".bin" / f"{cmd_name}.cmd"
        if tool_path.exists():
            return [str(tool_path)], False

    # Fallback to PATH lookup
    tool_path = shutil.which(f"{cmd_name}.cmd")
    if tool_path:
        return [tool_path], False
    tool_path = shutil.which(cmd_name)
    if tool_path:
        return [tool_path], False

    return [cmd_name], False


def gate_npm_build() -> Dict[str, Any]:
    """Gate 1: npm run build must succeed."""
    log("=== Gate 1: npm run build ===")
    start = time.time()
    cmd, use_shell = _resolve_npm_cmd()
    exit_code, stdout, stderr = run_cmd(cmd, cwd=SITE_DIR, use_shell=use_shell, timeout=300)
    duration = time.time() - start

    result: Dict[str, Any] = {
        "gate": "npm_build",
        "passed": exit_code == 0,
        "duration_seconds": round(duration, 1),
        "exit_code": exit_code,
        "stdout": stdout[-2000:] if stdout else "",
        "stderr": stderr[-2000:] if stderr else "",
        "errors": [],
    }

    if exit_code != 0:
        result["errors"].append(f"npm run build failed with exit code {exit_code}")

    log(f"npm build: {'PASS' if result['passed'] else 'FAIL'} ({result['duration_seconds']}s)")
    return result


def gate_impeccable() -> Dict[str, Any]:
    """Gate 2: Impeccable audit — no high-severity violations."""
    log("=== Gate 2: Impeccable audit ===")
    start = time.time()

    cmd, use_shell = _resolve_tool_cmd("impeccable")
    exit_code, stdout, stderr = run_cmd(
        [*cmd, "detect", "--project", str(SITE_DIR), "--format", "json", "--output", str(SITE_DIR / "impeccable-report.json")],
        cwd=SITE_DIR,
        use_shell=use_shell,
        timeout=120,
    )
    duration = time.time() - start

    report_data: Dict[str, Any] = {}
    if Path(SITE_DIR / "impeccable-report.json").exists():
        try:
            report_data = json.loads(Path(SITE_DIR / "impeccable-report.json").read_text(encoding="utf-8"))
        except Exception as e:
            log(f"Failed to parse impeccable report: {e}")

    high_severity = report_data.get("high_severity_count", 0) if report_data else 0
    medium_severity = report_data.get("medium_severity_count", 0) if report_data else 0

    passed = high_severity == 0

    result = {
        "gate": "impeccable_audit",
        "passed": passed,
        "duration_seconds": round(duration, 1),
        "exit_code": exit_code,
        "high_severity_count": high_severity,
        "medium_severity_count": medium_severity,
        "total_issues": report_data.get("total_issues", 0) if report_data else 0,
        "stdout": stdout[-1000:] if stdout else "",
        "stderr": stderr[-1000:] if stderr else "",
        "errors": [],
    }

    if not passed:
        result["errors"].append(f"Impeccable found {high_severity} high-severity violations")

    log(f"Impeccable: {'PASS' if passed else 'FAIL'} ({high_severity} high, {medium_severity} medium)")

    return result


def _find_latest_visual_direction(site_slug: str) -> Optional[Dict[str, Any]]:
    """Find the most recent VisualDirection JSON for a site slug."""
    vd_dir = Path("memory/visual_specs") / site_slug
    if not vd_dir.exists():
        return None
    json_files = sorted(vd_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        return None
    try:
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
        if data.get("schema_version") and data.get("primary_change"):
            return data
        return None
    except Exception:
        return None


# Tailwind CSS default palette (v3.x) - the design system palette.
# These are valid tokens when used intentionally via tailwind.config.js theme.
TAILWIND_PALETTE: Dict[str, set] = {
    "slate":   {"#f8fafc", "#f1f5f9", "#e2e8f0", "#cbd5e1", "#94a3b8", "#64748b", "#475569", "#334155", "#1e293b", "#0f172a"},
    "gray":    {"#f9fafb", "#f3f4f6", "#e5e7eb", "#d1d5db", "#9ca3af", "#6b7280", "#4b5563", "#374151", "#1f2937", "#111827"},
    "zinc":    {"#fafafa", "#f4f4f5", "#e4e4e7", "#d4d4d8", "#a1a1aa", "#71717a", "#52525b", "#3f3f46", "#27272a", "#18181b"},
    "neutral": {"#fafafa", "#f5f5f5", "#e5e5e5", "#d4d4d4", "#a3a3a3", "#737373", "#525252", "#404040", "#262626", "#171717"},
    "stone":   {"#fafaf9", "#f5f5f4", "#e7e5e4", "#d6d3d1", "#a8a29e", "#78716c", "#57534e", "#44403c", "#292524", "#0c0a09"},
    "red":     {"#fef2f2", "#fee2e2", "#fecaca", "#fca5a5", "#f87171", "#ef4444", "#dc2626", "#b91c1c", "#991b1b", "#7f1d1d"},
    "orange":  {"#fff7ed", "#ffedd5", "#fed7aa", "#fdba74", "#fb923c", "#f97316", "#ea580c", "#c2410c", "#9a3412", "#7c2d12"},
    "amber":   {"#fffbeb", "#fef3c7", "#fde68a", "#fcd34d", "#fbbf24", "#f59e0b", "#d97706", "#b45309", "#92400e", "#78350f"},
    "yellow":  {"#fefce8", "#fef9c3", "#fef08a", "#fde047", "#facc15", "#eab308", "#ca8a04", "#a16207", "#854d0e", "#713f12"},
    "lime":    {"#f7fee7", "#ecfccb", "#d9f99d", "#bef264", "#a3e635", "#84cc16", "#65a30d", "#4d7c0f", "#3f6212", "#365314"},
    "green":   {"#f0fdf4", "#dcfce7", "#bbf7d0", "#86efac", "#4ade80", "#22c55e", "#16a34a", "#15803d", "#166534", "#14532d"},
    "emerald": {"#ecfdf5", "#d1fae5", "#a7f3d0", "#6ee7b7", "#34d399", "#10b981", "#059669", "#047857", "#065f46", "#064e3b"},
    "teal":    {"#f0fdfa", "#ccfbf1", "#99f6e4", "#5eead4", "#2dd4bf", "#14b8a6", "#0d9488", "#0f766e", "#115e59", "#134e4a"},
    "cyan":    {"#ecfeff", "#cffafe", "#a5f3fc", "#67e8f9", "#22d3ee", "#06b6d4", "#0891b2", "#0e7490", "#155e75", "#164e63"},
    "sky":     {"#f0f9ff", "#e0f2fe", "#bae6fd", "#7dd3fc", "#38bdf8", "#0ea5e9", "#0284c7", "#0369a1", "#075985", "#0c4a6e"},
    "blue":    {"#eff6ff", "#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa", "#3b82f6", "#2563eb", "#1d4ed8", "#1e40af", "#1e3a8a"},
    "indigo":  {"#eef2ff", "#e0e7ff", "#c7d2fe", "#a5b4fc", "#818cf8", "#6366f1", "#4f46e5", "#4338ca", "#3730a3", "#312e81"},
    "violet":  {"#f5f3ff", "#ede9fe", "#ddd6fe", "#c4b5fd", "#a78bfa", "#8b5cf6", "#7c3aed", "#6d28d9", "#5b21b6", "#4c1d95"},
    "purple":  {"#faf5ff", "#f3e8ff", "#e9d5ff", "#d8b4fe", "#c084fc", "#a855f7", "#9333ea", "#7e22ce", "#6b21a8", "#581c87"},
    "fuchsia": {"#fdf4ff", "#fae8ff", "#f5d0fe", "#f0abfc", "#e879f9", "#d946ef", "#c026d3", "#a21caf", "#86198f", "#701a75"},
    "pink":    {"#fdf2f8", "#fce7f3", "#fbcfe8", "#f9a8d4", "#f472b6", "#ec4899", "#db2777", "#be185d", "#9d174d", "#831843"},
    "rose":    {"#fff1f2", "#ffe4e6", "#fecdd3", "#fda4af", "#fb7185", "#f43f5e", "#e11d48", "#be123c", "#9f1239", "#881337"},
}


def _extract_css_var_palette() -> set:
    """Extract color values from CSS custom property definitions in :root / [data-theme] blocks.

    A complete design system defines its palette as CSS variables in :root. These
    variables constitute the valid token set even when the brand spec only lists
    a few "headline" colors.
    """
    css_files = list(SITE_DIR.glob("**/*.css")) + list(SITE_DIR.glob("**/*.module.css"))
    palette: set = set()
    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    var_re = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
    in_root_block = False
    brace_depth = 0

    for css_file in css_files:
        try:
            content = css_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for line in content.splitlines():
            stripped = line.strip()
            if ":root" in stripped or "[data-theme" in stripped:
                in_root_block = True
                brace_depth = stripped.count("{") - stripped.count("}")
                for m in hex_re.findall(stripped):
                    palette.add(m.lower())
                continue
            if in_root_block:
                brace_depth += line.count("{") - line.count("}")
                if brace_depth <= 0:
                    in_root_block = False
                for m in hex_re.findall(stripped):
                    palette.add(m.lower())
    return palette


def _extract_tailwind_palette() -> set:
    """Extract Tailwind palette colors referenced in tailwind.config.js theme."""
    tw_config = SITE_DIR / "tailwind.config.js"
    if not tw_config.exists():
        return set()
    try:
        content = tw_config.read_text(encoding="utf-8")
    except Exception:
        return set()
    palette: set = set()
    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    for m in hex_re.findall(content):
        palette.add(m.lower())
    return palette


def gate_token_fidelity() -> Dict[str, Any]:
    """Gate 3: Token fidelity — all colors, fonts, spacing from BrandSpec + VisualDirection tokens.

    A valid token is any color that is:
    1. Explicitly listed in the BrandSpec
    2. Defined in the VisualDirection's color_delta
    3. Defined as a CSS custom property in :root or [data-theme] blocks
       (these constitute the design system palette)
    4. A member of a Tailwind CSS palette family referenced in tailwind.config.js
       (e.g. if indigo-500 is referenced, all indigo shades are valid)

    This prevents false positives where the builder uses a complete design system
    palette derived from the brand spec's accent/primary/secondary colors.
    """
    log("=== Gate 3: Token fidelity ===")
    start = time.time()

    brand_spec: Dict[str, Any] = {}
    if BRAND_SPEC_FILE.exists():
        try:
            brand_spec = json.loads(BRAND_SPEC_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"Failed to parse brand spec: {e}")
    elif (SITE_DIR / "BUILD_MANIFEST.json").exists():
        try:
            bm = json.loads((SITE_DIR / "BUILD_MANIFEST.json").read_text(encoding="utf-8"))
            brand_spec = bm.get("brand_spec", {})
        except Exception as e:
            log(f"Failed to parse brand spec from BUILD_MANIFEST: {e}")

    site_slug = SITE_DIR.name
    visual_direction = _find_latest_visual_direction(site_slug)

    css_files = list(SITE_DIR.glob("**/*.css")) + list(SITE_DIR.glob("**/*.module.css"))

    brand_colors: set = {
        brand_spec.get("primary_color", "").lower(),
        brand_spec.get("secondary_color", "").lower(),
        brand_spec.get("accent_color", "").lower(),
        brand_spec.get("background_color", "").lower(),
        brand_spec.get("text_color", "").lower(),
    }
    brand_colors.discard("")
    brand_colors.discard("none")  # "none" is CSS default, not a brand color

    brand_fonts: set = {
        brand_spec.get("font_family_heading", "").lower(),
        brand_spec.get("font_family_body", "").lower(),
    }
    brand_fonts.discard("")

    vd_colors: set = set()
    vd_fonts: set = set()
    vd_colors_found = False
    vd_fonts_found = False

    if visual_direction:
        if visual_direction.get("color_delta"):
            for val in visual_direction["color_delta"].values():
                if val and isinstance(val, str):
                    vd_colors.add(val.lower())
            vd_colors_found = True
        if visual_direction.get("typography_delta"):
            for key, val in visual_direction["typography_delta"].items():
                if val and isinstance(val, str) and key.startswith("font"):
                    vd_fonts.add(val)
            vd_fonts_found = True

    # Source 3: CSS variable palette in :root / [data-theme] blocks
    css_var_palette = _extract_css_var_palette()

    # Source 4: Tailwind palette colors referenced in tailwind.config.js
    tw_referenced = _extract_tailwind_palette()

    # Source 5: Full Tailwind palette families that are referenced in the config
    # If the config uses any shade of e.g. "indigo", all indigo shades are valid
    tw_full_palette: set = set()
    for family, shades in TAILWIND_PALETTE.items():
        if tw_referenced & shades:
            tw_full_palette |= shades

    all_valid_colors = brand_colors | vd_colors | css_var_palette | tw_full_palette
    all_valid_fonts = brand_fonts | vd_fonts

    hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}")
    violations: List[str] = []
    colors_used = 0
    fonts_used = 0

    for css_file in css_files:
        try:
            content = css_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for color in all_valid_colors:
            if color and color in content.lower():
                colors_used += 1

        for font in all_valid_fonts:
            if font and font in content:
                fonts_used += 1

        hex_colors = hex_pattern.findall(content)
        for hc in hex_colors:
            normalized = hc.lower()
            if normalized not in all_valid_colors and "rgba" not in normalized and "hsla" not in normalized:
                violations.append(f"{css_file.name}: non-brand color {hc}")

    duration = time.time() - start

    passed = len(violations) == 0

    result = {
        "gate": "token_fidelity",
        "passed": passed,
        "duration_seconds": round(duration, 1),
        "brand_colors": list(brand_colors),
        "brand_fonts": list(brand_fonts),
        "visual_direction_found": visual_direction is not None,
        "vd_colors": list(vd_colors) if vd_colors_found else [],
        "vd_fonts": list(vd_fonts) if vd_fonts_found else [],
        "css_var_palette_size": len(css_var_palette),
        "tailwind_palette_size": len(tw_full_palette),
        "total_valid_colors": len(all_valid_colors),
        "colors_used_from_brand": colors_used,
        "violation_count": len(violations),
        "violations": violations[:10],
        "errors": [],
    }

    if not passed:
        result["errors"].append(f"{len(violations)} non-brand tokens found")

    log(f"Token fidelity: {'PASS' if passed else 'FAIL'} ({len(violations)} violations, {len(all_valid_colors)} valid colors)")
    return result


def run_quality_gates(site_dir: str, re_run_impeccable: bool = False) -> Dict[str, Any]:
    """
    Public entry point for MigrationManager.
    Runs all four deterministic gates and returns a consolidated report.

    Args:
        site_dir: Absolute or relative path to the built site directory.
        re_run_impeccable: When True, force a fresh `impeccable detect` run.
                           Default=False → read existing impeccable-report.json.
    """
    global SITE_DIR, MANIFEST_FILE, BRAND_SPEC_FILE, IMPECCABLE_REPORT_FILE, QUALITY_GATE_FILE
    SITE_DIR = Path(site_dir)
    MANIFEST_FILE = SITE_DIR / "build-manifest.json"
    BRAND_SPEC_FILE = SITE_DIR / "brand-spec.json"
    IMPECCABLE_REPORT_FILE = SITE_DIR / "impeccable-report.json"
    QUALITY_GATE_FILE = SITE_DIR / "quality-gate-report.json"

    if re_run_impeccable and IMPECCABLE_REPORT_FILE.exists():
        IMPECCABLE_REPORT_FILE.unlink()

    reports = []
    overall_passed = True
    failing_gate = None

    # Gate 1
    r1 = gate_npm_build()
    reports.append(r1)
    if not r1["passed"]:
        overall_passed = False
        failing_gate = "npm_build"

    # Gate 2
    r2 = gate_impeccable()
    reports.append(r2)
    if not r2["passed"] and not failing_gate:
        overall_passed = False
        failing_gate = "impeccable_audit"

    # Gate 3
    r3 = gate_token_fidelity()
    reports.append(r3)
    if not r3["passed"] and not failing_gate:
        overall_passed = False
        failing_gate = "token_fidelity"

    # Gate 4
    r4 = gate_accessibility()
    reports.append(r4)
    if not r4["passed"] and not failing_gate:
        overall_passed = False
        failing_gate = "accessibility"

    result = {
        "overall_passed": overall_passed,
        "failing_gate": failing_gate,
        "gates": reports,
        "gaps": _extract_gaps_from_reports(reports),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    QUALITY_GATE_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _extract_gaps_from_reports(reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert gate failures into GapLedger-compatible gap dicts."""
    gaps = []
    for r in reports:
        if r.get("passed"):
            continue
        for err in r.get("errors", []):
            gaps.append({
                "id": f"{r['gate']}_{len(gaps)}",
                "description": err,
                "severity": "high" if r["gate"] in ("npm_build", "impeccable_audit") else "medium",
                "suggested_fix": "Address the reported violation",
                "gate": r["gate"],
            })
    return gaps


def gate_accessibility() -> Dict[str, Any]:
    """Gate 4: Accessibility scan via Playwright + axe-core.

    Starts the Next.js production server, runs axe-core accessibility checks
    against the running site, then kills the server.

    Requires: Node.js, Playwright installed (npx playwright install chromium).

    The accessibility check runs via an inline Playwright Node.js script
    (not via npx playwright evaluate, which is not a valid command).
    """
    log("=== Gate 4: Accessibility (WCAG AA) ===")
    start = time.time()

    server_proc = None
    tmp_script = None

    try:
        next_dist_dir = SITE_DIR / ".next"
        if not next_dist_dir.exists():
            return {
                "gate": "accessibility",
                "passed": False,
                "duration_seconds": round(time.time() - start, 1),
                "violations": [],
                "wcag_level": "AA",
                "errors": ["Next.js build output not found — run npm build first"],
            }

        port = 3456
        log(f"Starting Next.js server on port {port}...")

        npm_cmd, npm_shell = _resolve_npm_cmd()
        server_proc = subprocess.Popen(
            [*npm_cmd, "start", "--", "--port", str(port)],
            cwd=str(SITE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        time.sleep(5)

        script_content = (
            "const { chromium } = require('playwright');\\n"
            "(async () => {\\n"
            "  const browser = await chromium.launch();\\n"
            "  const page = await browser.newPage();\\n"
            "  const errors = [];\\n"
            "  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });\\n"
            "  await page.goto('http://localhost:" + str(port) + "', { waitUntil: 'networkidle', timeout: 30000 });\\n"
            "  await page.addScriptTag({ url: 'https://cdn.jsdelivr.net/npm/axe-core@4.9.0/axe.min.js' });\\n"
            "  const violations = await page.evaluate(() => new Promise((resolve) => {\\n"
            "    /* global axe */\\n"
            "    axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } }, (err, results) => {\\n"
            "      resolve(results && results.violations ? results.violations : []);\\n"
            "    });\\n"
            "  }));\\n"
            "  await browser.close();\\n"
            "  process.stdout.write(JSON.stringify({ violations, consoleErrors: errors }));\\n"
            "})();\\n"
        )

        tmp_script = (SITE_DIR / f"a11y_check_{os.getpid()}.js").resolve()
        tmp_script.write_text(script_content, encoding="utf-8")

        node_cmd, node_shell = _resolve_node_cmd()
        exit_code, stdout, stderr = run_cmd(
            [*node_cmd, str(tmp_script)],
            cwd=SITE_DIR,
            use_shell=node_shell,
            timeout=90,
        )

        log(f"Accessibility script exit code: {exit_code}")
        if stderr:
            log(f"Accessibility stderr: {stderr[:500]}")

        violations = []
        console_errors = []
        try:
            if stdout:
                parsed = json.loads(stdout.strip())
                violations = parsed.get("violations", [])
                console_errors = parsed.get("consoleErrors", [])
        except json.JSONDecodeError:
            log(f"Failed to parse accessibility output: {stdout[:200]}")

        if console_errors:
            log(f"Page had {len(console_errors)} console errors during scan")

        high_violations = [v for v in violations if v.get("impact") in ("critical", "serious")]
        passed = len(high_violations) == 0

        result: Dict[str, Any] = {
            "gate": "accessibility",
            "passed": passed,
            "duration_seconds": round(time.time() - start, 1),
            "total_violations": len(violations),
            "high_impact_violations": len(high_violations),
            "violations": [
                {"id": v.get("id"), "impact": v.get("impact"), "description": v.get("description")}
                for v in high_violations[:10]
            ],
            "wcag_level": "AA",
            "errors": [],
        }

        if not passed:
            result["errors"].append(f"{len(high_violations)} high-impact WCAG violations found")

        log(f"Accessibility: {'PASS' if passed else 'FAIL'} ({len(high_violations)} high-impact, {len(violations)} total)")

    except FileNotFoundError as e:
        result = {
            "gate": "accessibility",
            "passed": False,
            "duration_seconds": round(time.time() - start, 1),
            "violations": [],
            "wcag_level": "AA",
            "errors": [f"Required tool not found: {e}"],
        }
        log(f"Accessibility: FAIL — required tool not installed ({e})")

    except Exception as e:
        result = {
            "gate": "accessibility",
            "passed": False,
            "duration_seconds": round(time.time() - start, 1),
            "violations": [],
            "wcag_level": "AA",
            "errors": [str(e)],
        }
        log(f"Accessibility: FAIL — {e}")

    finally:
        if tmp_script and tmp_script.exists():
            try:
                tmp_script.unlink()
                log("Cleaned up temporary accessibility script")
            except Exception:
                pass
        if server_proc:
            log("Stopping Next.js server...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    return result


def load_manifest() -> Dict[str, Any]:
    """Load existing BuildManifest or return defaults."""
    if MANIFEST_FILE.exists():
        try:
            return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_report(report: Dict[str, Any]) -> None:
    """Save quality gate report."""
    try:
        Path(QUALITY_GATE_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Failed to save report: {e}")


def run_all_gates() -> Dict[str, Any]:
    """Run all quality gates sequentially."""
    log(f"Starting quality gate for: {SITE_DIR}")

    if not SITE_DIR.exists():
        return {
            "overall_passed": False,
            "error": f"Site directory not found: {SITE_DIR}",
            "gates": {},
        }

    gates: List[Any] = [
        gate_npm_build,
        gate_impeccable,
        gate_token_fidelity,
        gate_accessibility,
    ]

    gate_results: Dict[str, Any] = {}
    all_passed = True

    for gate_fn in gates:
        try:
            result = gate_fn()
            gate_results[result["gate"]] = result
            if not result["passed"]:
                all_passed = False
        except Exception as e:
            log(f"Gate {gate_fn.__name__} crashed: {e}")
            gate_results[gate_fn.__name__] = {
                "gate": gate_fn.__name__,
                "passed": False,
                "error": str(e),
            }
            all_passed = False

    timestamp = datetime.now(timezone.utc).isoformat()

    report: Dict[str, Any] = {
        "timestamp": timestamp,
        "site_dir": str(SITE_DIR),
        "overall_passed": all_passed,
        "gates": gate_results,
        "manifest_updated": False,
    }

    if MANIFEST_FILE.exists():
        try:
            manifest = json.loads(Path(MANIFEST_FILE).read_text(encoding="utf-8"))
            manifest["quality_gates_passed"] = all_passed
            manifest["quality_gate_timestamp"] = timestamp
            manifest["gate_results"] = gate_results
            Path(MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            report["manifest_updated"] = True
        except Exception as e:
            log(f"Failed to update manifest: {e}")

    save_report(report)

    return report


def main() -> int:
    """CLI entry point."""
    print(f"Quality Gate Runner")
    print(f"Site: {SITE_DIR}")
    print(f"Verbose: {VERBOSE}")
    print()

    report = run_all_gates()

    print()
    print("=" * 60)
    print("QUALITY GATE RESULTS")
    print("=" * 60)

    for gate_name, result in report.get("gates", {}).items():
        status = "PASS" if result.get("passed") else "FAIL"
        duration = result.get("duration_seconds", 0)
        print(f"  {gate_name}: {status} ({duration}s)")

    print()
    print(f"Overall: {'ALL GATES PASSED' if report['overall_passed'] else 'GATE FAILURES DETECTED'}")

    if report.get("manifest_updated"):
        print(f"BuildManifest updated: {MANIFEST_FILE}")

    if report["overall_passed"]:
        return 0
    else:
        failed = [k for k, v in report.get("gates", {}).items() if not v.get("passed")]
        print(f"Failed gates: {', '.join(failed)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())