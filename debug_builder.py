"""
Debug builder - run Kilo directly and capture raw output for analysis.
Uses the same node+kilo approach as builder_agent.py
"""
import subprocess
import json
import tempfile
import os
from pathlib import Path

MEMORY_DIR = Path("memory/site_understandings")
ARCHITECTURE_DIR = Path("memory/site_architectures")
RECOMMENDATION_DIR = Path("memory/site_recommendations")
PERSONA_PATH = Path("registry/personas/builder_specialist.md")

site_id = "20260520_132936"
arch_id = "20260520_132936"
rec_id = "20260520_132936"

from models.site_schemas import SiteUnderstanding, SiteArchitecture, ContentRecommendation

site_path = MEMORY_DIR / f"{site_id}.json"
arch_path = ARCHITECTURE_DIR / f"{arch_id}.json"
rec_path = RECOMMENDATION_DIR / f"{rec_id}.json"

site = SiteUnderstanding(**json.loads(site_path.read_text()))
arch = SiteArchitecture(**json.loads(arch_path.read_text()))
rec = ContentRecommendation(**json.loads(rec_path.read_text()))

persona = PERSONA_PATH.read_text()

prompt = f"""{persona}

## Task
You are a Builder Specialist. Analyze the following SiteUnderstanding, SiteArchitecture, and ContentRecommendation.
Produce a complete BuildManifest with production-ready code.

## Input SiteUnderstanding
{site.model_dump_json(indent=2)}

## Input SiteArchitecture
{arch.model_dump_json(indent=2)}

## Input ContentRecommendation
{rec.model_dump_json(indent=2)}

## Output Contract
Output ONLY valid JSON matching this schema:
{{
    "migration_id": "string",
    "source_url": "string",
    "source_understanding_id": "string",
    "source_architecture_id": "string",
    "source_recommendation_id": "string",
    "chosen_variant": "string",
    "brand_spec": {{"type": "object"}},
    "page_builds": [{{"type": "object"}}],
    "ui_polish_changes": [{{"type": "object"}}],
    "self_critique": {{"type": "object"}},
    "lighthouse_scores": {{"type": "object"}},
    "overall_quality_score": "number",
    "deployment_ready": "boolean",
    "deployed_url": "string",
    "build_timestamp": "string",
    "reasoning_trace": ["array"]
}}

## CRITICAL
- Output ONLY the JSON object — no markdown fences, no explanation
- The JSON must be valid and complete

Begin build manifest generation now."""

node_exe = "C:\\Program Files\\nodejs\\node.exe" if Path("C:\\Program Files\\nodejs\\node.exe").exists() else "node"
kilo_bin = Path("C:\\Users\\micha\\AppData\\Roaming\\npm\\node_modules\\@kilocode\\cli\\bin\\kilo")

print(f"[NODE] {node_exe}")
print(f"[KILO] {kilo_bin}")
print(f"[PERSONA] {PERSONA_PATH.exists()}")
print(f"[PROMPT LEN] {len(prompt)}")

with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write(prompt)
    prompt_path = f.name

print(f"[PROMPT FILE] {prompt_path}")

try:
    result = subprocess.run(
        [node_exe, str(kilo_bin), "run", "--format", "json", "--auto", "--", f"@{prompt_path}"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    print(f"[RETURNCODE] {result.returncode}")
    stdout = result.stdout or ""
    print(f"[STDOUT LEN] {len(stdout)}")

    lines = stdout.strip().split('\n') if stdout.strip() else []
    print(f"[LINES] {len(lines)}")

    # Print first 5 events
    for i, line in enumerate(lines[:5]):
        try:
            event = json.loads(line)
            evt_type = event.get("type", "unknown")
            if evt_type == "text":
                text = event.get("part", {}).get("text", "")
                print(f"  [{i}] type={evt_type} text_len={len(text)}")
            else:
                print(f"  [{i}] type={evt_type} keys={list(event.keys())}")
        except Exception as e:
            print(f"  [{i}] PARSE ERROR: {e} | {line[:100]}")

    # Look at last few events
    print("\n[LAST 5 EVENTS]")
    for i, line in enumerate(lines[-5:]):
        idx = len(lines) - 5 + i
        try:
            event = json.loads(line)
            evt_type = event.get("type", "unknown")
            if evt_type == "text":
                text = event.get("part", {}).get("text", "")
                print(f"  [{idx}] type={evt_type} text_len={len(text)} text_start={text[:200]}")
            else:
                print(f"  [{idx}] type={evt_type}")
        except Exception as e:
            print(f"  [{idx}] PARSE ERROR: {e} | {line[:200]}")

    # Try to extract JSON
    stdout_stripped = stdout.strip()
    first_brace = stdout_stripped.find("{")
    last_brace = stdout_stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
        candidate = stdout_stripped[first_brace:last_brace+1]
        try:
            json.loads(candidate)
            print(f"\n[EXTRACTED] Valid JSON found at {first_brace}:{last_brace} ({len(candidate)} chars)")
            print(f"  Keys: {list(json.loads(candidate).keys())}")
        except json.JSONDecodeError as e:
            print(f"\n[EXTRACTED] Invalid JSON at {first_brace}:{last_brace}: {e}")
            # Check if text events contain valid JSON
            for i, line in enumerate(lines):
                try:
                    event = json.loads(line)
                    if event.get("type") == "text":
                        text = event.get("part", {}).get("text", "")
                        fb = text.find("{")
                        lb = text.rfind("}")
                        if fb != -1 and lb != -1 and lb >= fb:
                            cand = text[fb:lb+1]
                            try:
                                parsed = json.loads(cand)
                                print(f"  Text event [{i}] has valid JSON at {fb}:{lb}")
                                print(f"  Keys: {list(parsed.keys())}")
                            except:
                                pass
                except:
                    pass

    else:
        print(f"\n[NO BRACES] stdout starts with: {stdout_stripped[:300]}")

finally:
    try:
        os.unlink(prompt_path)
    except:
        pass