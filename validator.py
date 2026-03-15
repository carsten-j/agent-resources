#!/usr/bin/env python3
"""
SKILL.md Validator for Agent Skills

Validates skill files according to the Agent Skills specification at:
https://agentskills.io/specification

Usage:
    python validator.py SKILL.md
    python validator.py path/to/skill/directory
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


# Validation constants from the specification
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
MAX_RECOMMENDED_BODY_LINES = 500

# Name pattern: lowercase letters, numbers, and hyphens only
NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")

# Required frontmatter fields
REQUIRED_FIELDS = {"name", "description"}

# Optional fields per the Agent Skills specification
OPTIONAL_FIELDS = {
    "license",  # License name or reference to a bundled license file
    "compatibility",  # Max 500 chars. Environment requirements
    "metadata",  # Arbitrary key-value mapping for additional metadata
    "allowed-tools",  # Space-delimited list of pre-approved tools (experimental)
    "disable-model-invocation",  # Blocks Skill tool invocation (not in spec)
}

# All known fields
KNOWN_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# Unsupported string substitution patterns (common mistakes in body content)
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
        "environment variable",
    ),
    (re.compile(r"%[A-Z_][A-Z0-9_]*%"), "%VARIABLE%", "Windows environment variable"),
]


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


def validate_name(
    name: str, result: ValidationResult, parent_dir_name: str | None = None
) -> None:
    """Validate the 'name' field per the specification."""
    if not name:
        result.add_error("Field 'name' is required but missing or empty")
        return

    if not isinstance(name, str):
        result.add_error(f"Field 'name' must be a string, got {type(name).__name__}")
        return

    # Length check: must be 1-64 characters
    if len(name) > MAX_NAME_LENGTH:
        result.add_error(
            f"Field 'name' exceeds maximum length of {MAX_NAME_LENGTH} characters "
            f"(got {len(name)})"
        )

    # Pattern check: lowercase letters, numbers, and hyphens only
    if not NAME_PATTERN.match(name):
        result.add_error(
            f"Field 'name' must contain only lowercase letters, numbers, and hyphens. "
            f"Got: '{name}'"
        )

    # Must not start with a hyphen
    if name.startswith("-"):
        result.add_error(
            f"Field 'name' must not start with a hyphen. Got: '{name}'"
        )

    # Must not end with a hyphen
    if name.endswith("-"):
        result.add_error(
            f"Field 'name' must not end with a hyphen. Got: '{name}'"
        )

    # Must not contain consecutive hyphens
    if "--" in name:
        result.add_error(
            f"Field 'name' must not contain consecutive hyphens. Got: '{name}'"
        )

    # Must match parent directory name
    if parent_dir_name is not None and name != parent_dir_name:
        result.add_error(
            f"Field 'name' must match the parent directory name. "
            f"Got name='{name}', directory='{parent_dir_name}'"
        )


def validate_description(description: str, result: ValidationResult) -> None:
    """Validate the 'description' field per the specification."""
    if not description:
        result.add_error("Field 'description' is required but missing or empty")
        return

    if not isinstance(description, str):
        result.add_error(
            f"Field 'description' must be a string, got {type(description).__name__}"
        )
        return

    # Length check: must be 1-1024 characters
    if len(description) > MAX_DESCRIPTION_LENGTH:
        result.add_error(
            f"Field 'description' exceeds maximum length of {MAX_DESCRIPTION_LENGTH} "
            f"characters (got {len(description)})"
        )

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


def validate_allowed_tools(allowed_tools: str | None, result: ValidationResult) -> None:
    """Validate the optional 'allowed-tools' field (space-delimited list)."""
    if allowed_tools is None:
        return

    if not isinstance(allowed_tools, str):
        result.add_error(
            f"Field 'allowed-tools' must be a string (space-delimited list), "
            f"got {type(allowed_tools).__name__}"
        )
        return

    # Parse space-delimited tools
    tools = allowed_tools.split()

    if not tools:
        result.add_warning("Field 'allowed-tools' is empty after parsing")
    else:
        result.add_info(f"Allowed tools: {', '.join(tools)}")


def validate_license_field(license_val: str | None, result: ValidationResult) -> None:
    """Validate the optional 'license' field."""
    if license_val is None:
        return

    if not isinstance(license_val, str):
        result.add_error(
            f"Field 'license' must be a string, got {type(license_val).__name__}"
        )
        return

    if not license_val.strip():
        result.add_warning("Field 'license' is present but empty")


def validate_compatibility_field(
    compatibility: str | None, result: ValidationResult
) -> None:
    """Validate the optional 'compatibility' field (max 500 chars)."""
    if compatibility is None:
        return

    if not isinstance(compatibility, str):
        result.add_error(
            f"Field 'compatibility' must be a string, got {type(compatibility).__name__}"
        )
        return

    if not compatibility.strip():
        result.add_warning("Field 'compatibility' is present but empty")
        return

    if len(compatibility) > MAX_COMPATIBILITY_LENGTH:
        result.add_error(
            f"Field 'compatibility' exceeds maximum length of "
            f"{MAX_COMPATIBILITY_LENGTH} characters (got {len(compatibility)})"
        )


def validate_metadata_field(
    metadata: dict | None, result: ValidationResult
) -> None:
    """Validate the optional 'metadata' field (string keys to string values)."""
    if metadata is None:
        return

    if not isinstance(metadata, dict):
        result.add_error(
            f"Field 'metadata' must be a mapping, got {type(metadata).__name__}"
        )
        return

    for key, value in metadata.items():
        if not isinstance(key, str):
            result.add_error(
                f"Field 'metadata' keys must be strings, got {type(key).__name__} "
                f"for key: {key}"
            )
        if not isinstance(value, str):
            result.add_warning(
                f"Field 'metadata' values should be strings, got "
                f"{type(value).__name__} for key '{key}'. "
                "Consider quoting the value in YAML (e.g., version: \"1.0\")."
            )


def validate_frontmatter(
    frontmatter_str: str,
    result: ValidationResult,
    parent_dir_name: str | None = None,
) -> dict:
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
    validate_name(data.get("name", ""), result, parent_dir_name=parent_dir_name)
    validate_description(data.get("description", ""), result)

    # Validate optional fields
    validate_allowed_tools(data.get("allowed-tools"), result)
    validate_license_field(data.get("license"), result)
    validate_compatibility_field(data.get("compatibility"), result)
    validate_metadata_field(data.get("metadata"), result)

    # Check for unknown fields (error)
    unknown_fields = set(data.keys()) - KNOWN_FIELDS
    if unknown_fields:
        for field_name in sorted(unknown_fields):
            result.add_error(
                f"Unknown frontmatter field: '{field_name}'. "
                f"Known fields are: {', '.join(sorted(KNOWN_FIELDS))}"
            )

    return data


def validate_body(body: str, result: ValidationResult) -> None:
    """Validate the markdown body content."""
    if not body or not body.strip():
        result.add_warning("Skill has no markdown body content")
        return

    lines = body.split("\n")
    line_count = len(lines)

    # Check recommended line limit (spec recommends under 500 lines)
    if line_count > MAX_RECOMMENDED_BODY_LINES:
        result.add_warning(
            f"Body exceeds recommended {MAX_RECOMMENDED_BODY_LINES} lines "
            f"(got {line_count}). Consider splitting into separate files."
        )

    # Check for unsupported string substitution patterns
    validate_string_substitutions(body, result)

    # Check for markdown headers (good structure)
    has_headers = any(line.strip().startswith("#") for line in lines)
    if not has_headers:
        result.add_info(
            "Consider adding markdown headers to structure the skill content"
        )


def validate_string_substitutions(content: str, result: ValidationResult) -> None:
    """Check for unsupported string substitution patterns."""
    # Skip content inside code blocks for substitution checks
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
                result.add_warning(
                    f"Line {i}: Possible unsupported string substitution syntax "
                    f"{syntax} found: '{match}' ({description})."
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


def validate_skill_file(
    file_path: Path, parent_dir_name: str | None = None
) -> ValidationResult:
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
    validate_frontmatter(frontmatter_str, result, parent_dir_name=parent_dir_name)

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

    # Validate the SKILL.md file, passing the directory name for name-matching check
    file_result = validate_skill_file(skill_file, parent_dir_name=dir_path.name)
    result.merge(file_result)

    # Check for files outside SKILL.md and conventional directories
    script_extensions = {".sh", ".py", ".js", ".ts", ".rb", ".pl", ".bash", ".zsh"}
    other_files = []
    for f in dir_path.rglob("*"):
        if not f.is_file() or f.name == "SKILL.md":
            continue
        rel = f.relative_to(dir_path)
        other_files.append(rel)

        # Warn if script-like files are outside scripts/
        if rel.suffix in script_extensions and not str(rel).startswith("scripts/"):
            result.add_warning(
                f"Script file '{rel}' is outside the 'scripts/' directory. "
                "The spec recommends placing executable code in scripts/."
            )

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

    status = "\u2713 VALID" if result.valid else "\u2717 INVALID"
    lines.append(f"\n{'=' * 60}")
    lines.append(f"Validation result for: {path}")
    lines.append(f"Status: {status}")
    lines.append("=" * 60)

    if result.errors:
        lines.append(f"\n\u274c Errors ({len(result.errors)}):")
        for error in result.errors:
            lines.append(f"   \u2022 {error}")

    if result.warnings:
        lines.append(f"\n\u26a0\ufe0f  Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            lines.append(f"   \u2022 {warning}")

    if verbose and result.info:
        lines.append(f"\n\u2139\ufe0f  Info ({len(result.info)}):")
        for info in result.info:
            lines.append(f"   \u2022 {info}")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files per the Agent Skills specification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
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
