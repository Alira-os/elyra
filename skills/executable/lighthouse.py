import json
import subprocess
import tempfile
import os
import hashlib


def run_lighthouse(url: str, preset: str = "desktop") -> dict:
    """
    Run Lighthouse CI on a URL.

    Args:
        url: The URL to audit
        preset: "desktop" or "mobile" (default: desktop)

    Returns:
        {
            "performance": 0.0 - 1.0,
            "accessibility": 0.0 - 1.0,
            "best_practices": 0.0 - 1.0,
            "seo": 0.0 - 1.0,
            "final_score": 0.0 - 1.0,
            "passed": True | False,
            "issues": list of issue descriptions,
            "details_url": str or None
        }
    """
    lighthouse_config = {
        "ci": {
            "collect": {
                "settings": {
                    "url": [url],
                    "numberOfRuns": 3,
                    "preset": preset,
                    "staticDistDir": None
                }
            },
            "assert": {
                "preset": "desktop",
                "assertions": {
                    "categories:performance": ["error", {"minScore": 0.85}],
                    "categories:accessibility": ["error", {"minScore": 0.90}],
                    "categories:best-practices": ["error", {"minScore": 0.85}],
                    "categories:seo": ["error", {"minScore": 0.85}]
                }
            }
        }
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "lighthouserc.json")
        with open(config_path, "w") as f:
            json.dump(lighthouse_config, f)

        result = subprocess.run(
            ["npx", "@lhci/cli", "autorun", "--config=" + config_path],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=300
        )

        output = result.stdout + result.stderr

        try:
            json_match_pos = output.rfind("{")
            json_match_end = output.rfind("}") + 1
            if json_match_pos >= 0 and json_match_end > json_match_pos:
                json_str = output[json_match_pos:json_match_end]
                lhr = json.loads(json_str)
            else:
                lhr = _parse_text_output(output)
        except (json.JSONDecodeError, ValueError):
            lhr = _parse_text_output(output)

        scores = {
            "performance": lhr.get("categories", {}).get("performance", {}).get("score", 0),
            "accessibility": lhr.get("categories", {}).get("accessibility", {}).get("score", 0),
            "best_practices": lhr.get("categories", {}).get("best-practices", {}).get("score", 0),
            "seo": lhr.get("categories", {}).get("seo", {}).get("score", 0),
        }

        final_score = (scores["performance"] + scores["accessibility"] +
                       scores["best_practices"] + scores["seo"]) / 4

        issues = []
        audits = lhr.get("audits", {})
        for audit_id, audit in audits.items():
            if audit.get("score") is not None and audit["score"] < 0.5:
                issues.append(f"{audit.get('title', audit_id)}: {audit.get('displayValue', audit.get('description', ''))}")

        passed = (
            scores["performance"] >= 0.85 and
            scores["accessibility"] >= 0.90 and
            scores["best_practices"] >= 0.85 and
            scores["seo"] >= 0.85
        )

        return {
            "performance": round(scores["performance"], 2),
            "accessibility": round(scores["accessibility"], 2),
            "best_practices": round(scores["best_practices"], 2),
            "seo": round(scores["seo"], 2),
            "final_score": round(final_score, 2),
            "passed": passed,
            "issues": issues[:10],
            "details_url": None,
            "raw_output": output[:1000] if len(output) > 1000 else output
        }


def _parse_text_output(output: str) -> dict:
    """Parse Lighthouse text output to extract scores."""
    categories = {}
    lines = output.split("\n")

    for line in lines:
        line = line.strip()
        for cat in ["performance", "accessibility", "best-practices", "seo"]:
            if cat in line.lower() and ":" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        score_str = parts[-1].strip().replace("%", "").replace("/100", "")
                        score = float(score_str) / 100 if float(score_str) > 1 else float(score_str)
                        categories[cat] = {"score": score}
                    except ValueError:
                        pass

    if not categories:
        for cat in ["performance", "accessibility", "best-practices", "seo"]:
            categories[cat] = {"score": 0.0}

    return {"categories": categories, "audits": {}}


def _generate_mock_result(url: str) -> dict:
    """Generate mock result when Lighthouse cannot run."""
    url_hash = int(hashlib.md5(url.encode()).hexdigest()[:8], 16) % 100
    perf = 0.70 + (url_hash % 30) / 100
    a11y = 0.75 + (url_hash % 25) / 100
    bp = 0.80 + (url_hash % 20) / 100
    seo = 0.78 + (url_hash % 22) / 100

    return {
        "performance": round(perf, 2),
        "accessibility": round(a11y, 2),
        "best_practices": round(bp, 2),
        "seo": round(seo, 2),
        "final_score": round((perf + a11y + bp + seo) / 4, 2),
        "passed": perf >= 0.85 and a11y >= 0.90 and bp >= 0.85 and seo >= 0.85,
        "issues": [],
        "details_url": None,
        "mock": True
    }


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    result = run_lighthouse(url)
    print(json.dumps(result, indent=2))