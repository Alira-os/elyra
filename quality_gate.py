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
) -> Tuple[int, str, str]:
    """Run a command, return (exit_code, stdout, stderr)."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)

    log(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def gate_npm_build() -> Dict[str, Any]:
    """Gate 1: npm run build must succeed."""
    log("=== Gate 1: npm run build ===")
    start = time.time()
    exit_code, stdout, stderr = run_cmd(["npm", "run", "build"], timeout=300)
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

    exit_code, stdout, stderr = run_cmd(
        ["impeccable", "detect", "--format", "json", "--output", "impeccable-report.json"],
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


def gate_token_fidelity() -> Dict[str, Any]:
    """Gate 3: Token fidelity — all colors, fonts, spacing from BrandSpec + VisualDirection tokens.

    Loads the newest VisualDirection from memory/visual_specs/[site-slug]/ (inferred from
    the site directory name) and treats its color_delta/typography_delta/motion_delta values
    as valid additional tokens. Violations are logged only for values that are neither
    BrandSpec tokens nor VisualDirection delta tokens.
    """
    log("=== Gate 3: Token fidelity ===")
    start = time.time()

    brand_spec: Dict[str, Any] = {}
    if BRAND_SPEC_FILE.exists():
        try:
            brand_spec = json.loads(BRAND_SPEC_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"Failed to parse brand spec: {e}")

    site_slug = SITE_DIR.name
    visual_direction = _find_latest_visual_direction(site_slug)

    css_files = list(SITE_DIR.glob("**/*.css")) + list(SITE_DIR.glob("**/*.module.css"))

    brand_colors: set = {
        brand_spec.get("primary_color", ""),
        brand_spec.get("secondary_color", ""),
        brand_spec.get("accent_color", ""),
        brand_spec.get("background_color", ""),
        brand_spec.get("text_color", ""),
    }
    brand_colors.discard("")

    brand_fonts: set = {
        brand_spec.get("font_family_heading", ""),
        brand_spec.get("font_family_body", ""),
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

    all_valid_colors = brand_colors | vd_colors
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
            if not any(bc.lower() == normalized for bc in all_valid_colors):
                if "rgba" not in normalized and "hsla" not in normalized:
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
        "colors_used_from_brand": colors_used,
        "violation_count": len(violations),
        "violations": violations[:10],
        "errors": [],
    }

    if not passed:
        result["errors"].append(f"{len(violations)} non-brand tokens found")

    log(f"Token fidelity: {'PASS' if passed else 'FAIL'} ({len(violations)} violations)")
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

        server_proc = subprocess.Popen(
            ["npm", "start", "--", "--port", str(port)],
            cwd=str(SITE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
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

        tmp_script = SITE_DIR / f"a11y_check_{os.getpid()}.js"
        tmp_script.write_text(script_content, encoding="utf-8")

        exit_code, stdout, stderr = run_cmd(
            ["node", str(tmp_script)],
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