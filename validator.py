#!/usr/bin/env python3
"""
SKILL.md Validator for Claude Code Agent Skills

Validates skill files according to the specification at:
https://code.claude.com/docs/en/skills
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices

Usage:
    python skill_validator.py SKILL.md
    python skill_validator.py path/to/skill/directory
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ValidationResult:
    """Container for validation results."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        self.info.append(message)

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)
        if not other.valid:
            self.valid = False


# Validation constants from the documentation
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_RECOMMENDED_BODY_LINES = 500
RESERVED_WORDS = {"anthropic", "claude"}
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")
XML_TAG_PATTERN = re.compile(r"<[^>]+>")

# Known frontmatter fields from the Agent Skills specification
# Required fields
REQUIRED_FIELDS = {"name", "description"}

# Optional fields supported by Claude Code
OPTIONAL_FIELDS = {
    "allowed-tools",  # Restricts which tools the skill can use
    "model",  # Force specific model (opus, sonnet, haiku)
    "context",  # Set to "fork" to run in sub-agent context
    "agent",  # Agent type when context: fork
    "hooks",  # Lifecycle-scoped hooks (PreToolUse, PostToolUse, Stop)
    "user-invocable",  # false hides from slash menu but allows Skill tool
    "disable-model-invocation",  # true blocks Skill tool invocation
    "argument-hint",  # Usage hints displayed in slash command completion
}

# All known fields
KNOWN_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# Unsupported string substitution patterns (common mistakes)
# The only supported syntax is !`command` (Dynamic Context Injection)
UNSUPPORTED_SUBSTITUTION_PATTERNS = [
    (re.compile(r"\$\{[^}]+\}"), "${...}", "shell variable expansion"),
    (
        re.compile(r"\{\{[^}]+\}\}"),
        "{{...}}",
        "template variable (Jinja/Mustache style)",
    ),
    (
        re.compile(r"(?<![!`])\$[A-Z_][A-Z0-9_]*\b"),
        "$VARIABLE",
        "environment variable (use !`echo $VAR` instead)",
    ),
    (re.compile(r"%[A-Z_][A-Z0-9_]*%"), "%VARIABLE%", "Windows environment variable"),
]

# Valid Dynamic Context Injection pattern: !`command`
DCI_PATTERN = re.compile(r"!\`[^`]+\`")


def extract_frontmatter(content: str) -> tuple[Optional[str], Optional[str], int]:
    """
    Extract YAML frontmatter and markdown body from content.

    Returns:
        Tuple of (frontmatter_str, body_str, frontmatter_end_line)
    """
    lines = content.split("\n")

    # Check for opening delimiter on line 1
    if not lines or lines[0].strip() != "---":
        return None, content, 0

    # Find closing delimiter
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return frontmatter, body, i + 1

    # No closing delimiter found
    return None, content, 0


def validate_name(name: str, result: ValidationResult) -> None:
    """Validate the 'name' field."""
    if not name:
        result.add_error("Field 'name' is required but missing or empty")
        return

    if not isinstance(name, str):
        result.add_error(f"Field 'name' must be a string, got {type(name).__name__}")
        return

    # Length check
    if len(name) > MAX_NAME_LENGTH:
        result.add_error(
            f"Field 'name' exceeds maximum length of {MAX_NAME_LENGTH} characters "
            f"(got {len(name)})"
        )

    # Pattern check (lowercase letters, numbers, hyphens only)
    if not NAME_PATTERN.match(name):
        result.add_error(
            f"Field 'name' must contain only lowercase letters, numbers, and hyphens. "
            f"Got: '{name}'"
        )

    # Reserved words check
    name_lower = name.lower()
    for reserved in RESERVED_WORDS:
        if reserved in name_lower:
            result.add_error(
                f"Field 'name' cannot contain reserved word '{reserved}'. Got: '{name}'"
            )

    # XML tag check
    if XML_TAG_PATTERN.search(name):
        result.add_error(f"Field 'name' cannot contain XML tags. Got: '{name}'")

    # Naming convention recommendation (gerund form)
    if not name.endswith("ing") and "-" in name:
        parts = name.split("-")
        if not any(part.endswith("ing") for part in parts):
            result.add_info(
                f"Consider using gerund form (verb + -ing) for skill name, "
                f"e.g., 'processing-pdfs' instead of '{name}'"
            )


def validate_description(description: str, result: ValidationResult) -> None:
    """Validate the 'description' field."""
    if not description:
        result.add_error("Field 'description' is required but missing or empty")
        return

    if not isinstance(description, str):
        result.add_error(
            f"Field 'description' must be a string, got {type(description).__name__}"
        )
        return

    # Length check
    if len(description) > MAX_DESCRIPTION_LENGTH:
        result.add_error(
            f"Field 'description' exceeds maximum length of {MAX_DESCRIPTION_LENGTH} "
            f"characters (got {len(description)})"
        )

    # XML tag check
    if XML_TAG_PATTERN.search(description):
        result.add_error("Field 'description' cannot contain XML tags")

    # Quality checks (warnings/info)
    desc_lower = description.lower()

    # Check for vague descriptions
    vague_patterns = [
        "helps with",
        "for files",
        "for data",
        "does stuff",
        "processes data",
    ]
    for pattern in vague_patterns:
        if pattern in desc_lower:
            result.add_warning(
                f"Description may be too vague (contains '{pattern}'). "
                "Be specific about what the skill does and when to use it."
            )

    # Check for "when to use" guidance
    usage_indicators = ["use when", "use for", "use this", "triggers", "invoke"]
    has_usage_guidance = any(indicator in desc_lower for indicator in usage_indicators)
    if not has_usage_guidance:
        result.add_warning(
            "Description should include when to use the skill, "
            "e.g., 'Use when working with PDF files...'"
        )

    # Check for first-person language (should be third person)
    first_person = ["i can", "i will", "i help", "you can use this"]
    for phrase in first_person:
        if phrase in desc_lower:
            result.add_warning(
                f"Description should use third person, not '{phrase}'. "
                "Example: 'Processes PDF files' instead of 'I can process PDF files'"
            )


def validate_allowed_tools(allowed_tools: str, result: ValidationResult) -> None:
    """Validate the optional 'allowed-tools' field."""
    if allowed_tools is None:
        return

    if not isinstance(allowed_tools, str):
        result.add_error(
            f"Field 'allowed-tools' must be a string (comma-separated list), "
            f"got {type(allowed_tools).__name__}"
        )
        return

    # Parse comma-separated tools
    tools = [t.strip() for t in allowed_tools.split(",") if t.strip()]

    if not tools:
        result.add_warning("Field 'allowed-tools' is empty after parsing")
    else:
        result.add_info(f"Allowed tools: {', '.join(tools)}")


def validate_frontmatter(frontmatter_str: str, result: ValidationResult) -> dict:
    """Validate and parse YAML frontmatter."""
    if frontmatter_str is None:
        result.add_error(
            "Missing YAML frontmatter. File must start with '---' on line 1"
        )
        return {}

    try:
        data = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as e:
        result.add_error(f"Invalid YAML syntax in frontmatter: {e}")
        return {}

    if not isinstance(data, dict):
        result.add_error(
            f"Frontmatter must be a YAML mapping, got {type(data).__name__}"
        )
        return {}

    # Validate required fields
    validate_name(data.get("name", ""), result)
    validate_description(data.get("description", ""), result)

    # Validate optional fields
    validate_allowed_tools(data.get("allowed-tools"), result)
    validate_context_field(data.get("context"), data.get("agent"), result)
    validate_model_field(data.get("model"), result)
    validate_boolean_field(data, "user-invocable", result)
    validate_boolean_field(data, "disable-model-invocation", result)
    validate_hooks_field(data.get("hooks"), result)

    # Check for unknown fields (error)
    unknown_fields = set(data.keys()) - KNOWN_FIELDS
    if unknown_fields:
        for field_name in sorted(unknown_fields):
            result.add_error(
                f"Unknown frontmatter field: '{field_name}'. "
                f"Known fields are: {', '.join(sorted(KNOWN_FIELDS))}"
            )

    return data


def validate_context_field(
    context: str | None, agent: str | None, result: ValidationResult
) -> None:
    """Validate the 'context' and 'agent' fields."""
    if context is None:
        if agent is not None:
            result.add_warning(
                "Field 'agent' is specified but 'context' is not set. "
                "'agent' only applies when 'context: fork' is set."
            )
        return

    if not isinstance(context, str):
        result.add_error(
            f"Field 'context' must be a string, got {type(context).__name__}"
        )
        return

    valid_contexts = {"fork"}
    if context not in valid_contexts:
        result.add_error(
            f"Field 'context' has invalid value '{context}'. "
            f"Valid values are: {', '.join(sorted(valid_contexts))}"
        )


def validate_model_field(model: str | None, result: ValidationResult) -> None:
    """Validate the 'model' field."""
    if model is None:
        return

    if not isinstance(model, str):
        result.add_error(f"Field 'model' must be a string, got {type(model).__name__}")
        return

    # Common model values (not exhaustive, just informational)
    common_models = {"opus", "sonnet", "haiku", "inherit"}
    model_lower = model.lower()

    # Check if it looks like a model identifier
    if not any(m in model_lower for m in common_models):
        result.add_info(
            f"Field 'model' is set to '{model}'. Common values include: "
            "opus, sonnet, haiku, inherit, or full model identifiers."
        )


def validate_boolean_field(
    data: dict, field_name: str, result: ValidationResult
) -> None:
    """Validate a boolean frontmatter field."""
    value = data.get(field_name)
    if value is None:
        return

    if not isinstance(value, bool):
        result.add_error(
            f"Field '{field_name}' must be a boolean (true/false), "
            f"got {type(value).__name__}: {value}"
        )


def validate_hooks_field(hooks: dict | None, result: ValidationResult) -> None:
    """Validate the 'hooks' field."""
    if hooks is None:
        return

    if not isinstance(hooks, dict):
        result.add_error(f"Field 'hooks' must be a mapping, got {type(hooks).__name__}")
        return

    valid_hook_types = {"PreToolUse", "PostToolUse", "Stop"}
    for hook_name in hooks.keys():
        if hook_name not in valid_hook_types:
            result.add_warning(
                f"Unknown hook type: '{hook_name}'. "
                f"Known hook types are: {', '.join(sorted(valid_hook_types))}"
            )


def validate_body(body: str, result: ValidationResult) -> None:
    """Validate the markdown body content."""
    if not body or not body.strip():
        result.add_warning("Skill has no markdown body content")
        return

    lines = body.split("\n")
    line_count = len(lines)

    # Check recommended line limit
    if line_count > MAX_RECOMMENDED_BODY_LINES:
        result.add_warning(
            f"Body exceeds recommended {MAX_RECOMMENDED_BODY_LINES} lines "
            f"(got {line_count}). Consider splitting into separate files."
        )

    # Check for Windows-style paths
    windows_path_pattern = re.compile(r"\\[a-zA-Z]")
    for i, line in enumerate(lines, start=1):
        if windows_path_pattern.search(line):
            result.add_warning(
                f"Line {i}: Possible Windows-style path detected. "
                "Use forward slashes for cross-platform compatibility."
            )

    # Check for unsupported string substitution patterns
    validate_string_substitutions(body, result)

    # Check for valid Dynamic Context Injection usage
    dci_matches = DCI_PATTERN.findall(body)
    if dci_matches:
        result.add_info(
            f"Found {len(dci_matches)} Dynamic Context Injection directive(s) (!`command`)"
        )

    # Check for markdown headers (good structure)
    has_headers = any(line.strip().startswith("#") for line in lines)
    if not has_headers:
        result.add_info(
            "Consider adding markdown headers to structure the skill content"
        )

    # Check for code blocks (often useful in skills)
    has_code_blocks = "```" in body
    if has_code_blocks:
        result.add_info("Skill contains code blocks")


def validate_string_substitutions(content: str, result: ValidationResult) -> None:
    """Check for unsupported string substitution patterns."""
    # Skip content inside code blocks for substitution checks
    # We'll check line by line, tracking code block state
    lines = content.split("\n")
    in_code_block = False

    for i, line in enumerate(lines, start=1):
        # Track code block state
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue

        # Skip checks inside code blocks (code examples may legitimately have these)
        if in_code_block:
            continue

        # Check for unsupported substitution patterns
        for pattern, syntax, description in UNSUPPORTED_SUBSTITUTION_PATTERNS:
            matches = pattern.findall(line)
            for match in matches:
                result.add_error(
                    f"Line {i}: Unsupported string substitution syntax {syntax} found: '{match}'. "
                    f"This is {description}. "
                    "Use Dynamic Context Injection (!`command`) instead for shell commands."
                )


def validate_references(body: str, skill_dir: Path, result: ValidationResult) -> None:
    """Check that referenced files exist."""
    # Find markdown links
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for match in link_pattern.finditer(body):
        link_text, link_path = match.groups()

        # Skip URLs
        if link_path.startswith(("http://", "https://", "mailto:")):
            continue

        # Skip anchors
        if link_path.startswith("#"):
            continue

        # Check if file exists
        ref_path = skill_dir / link_path
        if not ref_path.exists():
            result.add_warning(
                f"Referenced file not found: '{link_path}' (link text: '{link_text}')"
            )
        else:
            result.add_info(f"Referenced file exists: '{link_path}'")


def validate_skill_file(file_path: Path) -> ValidationResult:
    """Validate a single SKILL.md file."""
    result = ValidationResult()

    if not file_path.exists():
        result.add_error(f"File not found: {file_path}")
        return result

    if not file_path.is_file():
        result.add_error(f"Not a file: {file_path}")
        return result

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result.add_error(f"File is not valid UTF-8: {file_path}")
        return result
    except OSError as e:
        result.add_error(f"Cannot read file: {e}")
        return result

    # Extract and validate frontmatter
    frontmatter_str, body, _ = extract_frontmatter(content)
    validate_frontmatter(frontmatter_str, result)

    # Validate body
    if body:
        validate_body(body, result)
        validate_references(body, file_path.parent, result)

    return result


def validate_skill_directory(dir_path: Path) -> ValidationResult:
    """Validate a skill directory."""
    result = ValidationResult()

    if not dir_path.exists():
        result.add_error(f"Directory not found: {dir_path}")
        return result

    if not dir_path.is_dir():
        result.add_error(f"Not a directory: {dir_path}")
        return result

    # Check for SKILL.md
    skill_file = dir_path / "SKILL.md"
    if not skill_file.exists():
        result.add_error(f"SKILL.md not found in {dir_path}")
        return result

    # Validate the SKILL.md file
    file_result = validate_skill_file(skill_file)
    result.merge(file_result)

    # List other files in the directory
    other_files = [
        f.relative_to(dir_path)
        for f in dir_path.rglob("*")
        if f.is_file() and f.name != "SKILL.md"
    ]
    if other_files:
        result.add_info(f"Additional files in skill directory: {len(other_files)}")
        for f in other_files[:10]:  # Show first 10
            result.add_info(f"  - {f}")
        if len(other_files) > 10:
            result.add_info(f"  ... and {len(other_files) - 10} more")

    return result


def format_result(result: ValidationResult, path: Path, verbose: bool = False) -> str:
    """Format validation result for display."""
    lines = []

    status = "✓ VALID" if result.valid else "✗ INVALID"
    lines.append(f"\n{'=' * 60}")
    lines.append(f"Validation result for: {path}")
    lines.append(f"Status: {status}")
    lines.append("=" * 60)

    if result.errors:
        lines.append(f"\n❌ Errors ({len(result.errors)}):")
        for error in result.errors:
            lines.append(f"   • {error}")

    if result.warnings:
        lines.append(f"\n⚠️  Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            lines.append(f"   • {warning}")

    if verbose and result.info:
        lines.append(f"\nℹ️  Info ({len(result.info)}):")
        for info in result.info:
            lines.append(f"   • {info}")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files for Claude Code Agent Skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s SKILL.md                    Validate a single file
  %(prog)s my-skill/                   Validate a skill directory
  %(prog)s SKILL.md --verbose          Show all info messages
  %(prog)s --strict SKILL.md           Treat warnings as errors
        """,
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to SKILL.md file or skill directory",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show info messages in addition to errors and warnings",
    )
    parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only output errors (suppress warnings and info)",
    )

    args = parser.parse_args()

    path = args.path.resolve()

    # Determine if path is file or directory
    if path.is_file():
        result = validate_skill_file(path)
    elif path.is_dir():
        result = validate_skill_directory(path)
    else:
        print(f"Error: Path not found: {path}", file=sys.stderr)
        return 1

    # Apply strict mode
    if args.strict and result.warnings:
        result.valid = False

    # Format and print result
    if not args.quiet or not result.valid:
        print(format_result(result, path, verbose=args.verbose))

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
