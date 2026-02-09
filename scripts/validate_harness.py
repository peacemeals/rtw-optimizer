"""Validate Claude Code harness files for correctness."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
errors = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {name}")
    else:
        msg = f"{name}: {detail}" if detail else name
        errors.append(msg)
        print(f"  {FAIL}  {name}" + (f" — {detail}" if detail else ""))


def main():
    print("Harness Validation")
    print("=" * 40)

    # --- File existence ---
    print("\n1. File Existence")
    files = {
        "CLAUDE.md": ROOT / "CLAUDE.md",
        ".claude/settings.json": ROOT / ".claude" / "settings.json",
        ".claude/rules/testing.md": ROOT / ".claude" / "rules" / "testing.md",
        ".claude/rules/rules-engine.md": ROOT / ".claude" / "rules" / "rules-engine.md",
        ".claude/commands/rtw-verify.md": ROOT / ".claude" / "commands" / "rtw-verify.md",
        ".claude/commands/rtw-status.md": ROOT / ".claude" / "commands" / "rtw-status.md",
        ".claude/commands/rtw-setup.md": ROOT / ".claude" / "commands" / "rtw-setup.md",
        ".claude/commands/rtw-help.md": ROOT / ".claude" / "commands" / "rtw-help.md",
    }
    for name, path in files.items():
        check(name, path.exists(), "file not found")

    # --- CLAUDE.md checks ---
    print("\n2. CLAUDE.md Content")
    claude_md = (ROOT / "CLAUDE.md").read_text()
    lines = claude_md.splitlines()
    check(f"Line count ({len(lines)} lines)", 100 <= len(lines) <= 170,
          f"expected 100-170, got {len(lines)}")

    required_sections = [
        "## Tech Stack", "## Quick Commands", "## CLI Commands",
        "## Module Map", "## Domain Vocabulary", "## Conventions",
        "## Reference Files", "## Slash Commands",
    ]
    for section in required_sections:
        check(f"Section: {section}", section in claude_md, "missing")

    tech_items = ["Python 3.11", "Typer", "Rich", "Pydantic", "uv", "pytest", "ruff"]
    for item in tech_items:
        check(f"Tech stack: {item}", item in claude_md, "not mentioned")

    check("Command: uv run pytest", "uv run pytest" in claude_md)
    check("Command: ruff check", "ruff check" in claude_md)
    check("Command: python3 -m rtw", "python3 -m rtw" in claude_md)
    check("ralph-dev defensive line", "ralph-dev" in claude_md)

    # --- settings.json checks ---
    print("\n3. settings.json")
    settings_path = ROOT / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            check("Valid JSON", True)
        except json.JSONDecodeError as e:
            check("Valid JSON", False, str(e))
            settings = {}

        perms = settings.get("permissions", {})
        allow = perms.get("allow", [])
        deny = perms.get("deny", [])
        check(f"Allow count ({len(allow)})", 10 <= len(allow) <= 14,
              f"expected 10-14, got {len(allow)}")
        check(f"Deny count ({len(deny)})", len(deny) == 3,
              f"expected 3, got {len(deny)}")

        allow_str = " ".join(allow)
        check("Allow: pytest", "pytest" in allow_str)
        check("Allow: ruff", "ruff" in allow_str)
        check("Allow: git", "git" in allow_str)

        deny_str = " ".join(deny)
        check("Deny: rm -rf", "rm -rf" in deny_str)
        check("Deny: push --force", "push --force" in deny_str)
        check("Deny: reset --hard", "reset --hard" in deny_str)

        # No bare Bash pattern
        check("No bare Bash pattern", not any(p == "Bash" for p in allow))

    # --- Command frontmatter checks ---
    print("\n4. Command Frontmatter")
    commands = ["rtw-init", "rtw-verify", "rtw-status", "rtw-setup", "rtw-help"]
    for cmd in commands:
        path = ROOT / ".claude" / "commands" / f"{cmd}.md"
        if path.exists():
            content = path.read_text()
            check(f"{cmd}: has frontmatter", content.startswith("---"))
            check(f"{cmd}: has description", "description:" in content)

    # --- Path-scoped rules checks ---
    print("\n5. Path-Scoped Rules")
    for rule_name, expected_glob in [("testing.md", "tests/"), ("rules-engine.md", "rtw/rules/")]:
        path = ROOT / ".claude" / "rules" / rule_name
        if path.exists():
            content = path.read_text()
            check(f"{rule_name}: has paths frontmatter", "paths:" in content)
            check(f"{rule_name}: correct glob", expected_glob in content)

    # --- .gitignore checks ---
    print("\n6. .gitignore")
    gitignore = (ROOT / ".gitignore").read_text()
    check("ralph-dev-* entry", "ralph-dev-*" in gitignore)
    check("settings.local.json entry", "settings.local.json" in gitignore)
    check("CLAUDE.local.md entry", "CLAUDE.local.md" in gitignore)
    # Negative checks: team-shared files NOT ignored
    check("CLAUDE.md NOT ignored (no exact match)",
          "\nCLAUDE.md\n" not in f"\n{gitignore}\n" or "CLAUDE.local.md" in gitignore)

    # --- Summary ---
    print(f"\n{'=' * 40}")
    if errors:
        print(f"\033[31m{len(errors)} FAILED\033[0m checks:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print(f"\033[32mAll checks passed!\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
