import os
import importlib.util
from pathlib import Path
from typing import Optional


REGISTRY_ROOT = Path(__file__).parent
PERSONAS_DIR = REGISTRY_ROOT / "personas"
SKILLS_DIR = REGISTRY_ROOT.parent / "skills"
EXECUTABLE_SKILLS_DIR = SKILLS_DIR / "executable"
TOOLS_DIR = REGISTRY_ROOT / "tools"


def _load_markdown(file_path: Path) -> str:
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


def _load_executable_skill(skill_name: str):
    module_name = f"skills.executable.{skill_name}"
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        pass
    return None


def load_persona(name: str) -> dict:
    persona_path = PERSONAS_DIR / f"{name}.md"
    if not persona_path.exists():
        available = list_personas()
        raise FileNotFoundError(f"Persona '{name}' not found. Available: {available}")

    content = _load_markdown(persona_path)
    return {
        "name": name,
        "type": "persona",
        "content": content,
        "path": str(persona_path)
    }


def load_skill(name: str) -> dict:
    skill_md_path = SKILLS_DIR / f"{name}.md"
    executable_md_path = SKILLS_DIR / "executable" / f"{name}.md"

    md_path = skill_md_path if skill_md_path.exists() else executable_md_path
    md_content = _load_markdown(md_path) if md_path.exists() else ""

    executable = _load_executable_skill(name)

    if not md_content and not executable:
        available = list_skills()
        raise FileNotFoundError(f"Skill '{name}' not found. Available: {available}")

    return {
        "name": name,
        "type": "skill",
        "markdown": md_content,
        "callable": executable,
        "path": str(md_path) if md_path.exists() else None
    }


def load_tool(name: str) -> dict:
    tool_path = TOOLS_DIR / f"{name}.md"
    if not tool_path.exists():
        available = list_tools()
        raise FileNotFoundError(f"Tool '{name}' not found. Available: {available}")

    content = _load_markdown(tool_path)
    return {
        "name": name,
        "type": "tool",
        "content": content,
        "path": str(tool_path)
    }


def list_personas() -> list[str]:
    if not PERSONAS_DIR.exists():
        return []
    return [p.stem for p in PERSONAS_DIR.glob("*.md")]


def list_skills() -> list[str]:
    skill_files = set()
    if SKILLS_DIR.exists():
        skill_files.update(p.stem for p in SKILLS_DIR.glob("*.md"))
    if EXECUTABLE_SKILLS_DIR.exists():
        py_files = [p.stem for p in EXECUTABLE_SKILLS_DIR.glob("*.py") if p.stem not in ("__init__", "__pycache__")]
        skill_files.update(py_files)
    return sorted(skill_files)


def list_tools() -> list[str]:
    if not TOOLS_DIR.exists():
        return []
    return [t.stem for t in TOOLS_DIR.glob("*.md")]


def resolve_persona(name: str):
    """Load and return a persona definition for use by conductor."""
    return load_persona(name)


def resolve_skill(name: str):
    """Load and return a skill (markdown + callable) for use by conductor."""
    return load_skill(name)


def resolve_tool(name: str):
    """Load and return a tool definition for use by conductor."""
    return load_tool(name)


if __name__ == "__main__":
    print("Available personas:", list_personas())
    print("Available skills:", list_skills())
    print("Available tools:", list_tools())

    if list_personas():
        print("\nLoading persona:", list_personas()[0])
        p = load_persona(list_personas()[0])
        print(f"  Type: {p['type']}, Path: {p['path']}")

    if list_skills():
        print("\nLoading skill:", list_skills()[0])
        s = load_skill(list_skills()[0])
        print(f"  Type: {s['type']}, Has callable: {s['callable'] is not None}")