#!/usr/bin/env python3
"""
Agent Validator for Claude Code Subagents

Validates agent files according to the specification at:
https://code.claude.com/docs/en/sub-agents

Usage:
    python agent_validator.py agent.md
    python agent_validator.py .claude/agents/
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
MAX_DESCRIPTION_LENGTH = 4096
MAX_RECOMMENDED_BODY_LINES = 500

# Name pattern: lowercase letters, numbers, and hyphens only
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# Valid values for enumerated fields
VALID_MODELS = {"sonnet", "opus", "haiku", "inherit"}
VALID_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "delegate",
    "dontAsk",
    "bypassPermissions",
    "plan",
}
VALID_MEMORY_SCOPES = {"user", "project", "local"}

# Known hook event types for agents
VALID_HOOK_EVENTS = {"PreToolUse", "PostToolUse", "Stop"}

# Known Claude Code internal tools
KNOWN_TOOLS = {
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Task",
    "WebFetch",
    "WebSearch",
    "NotebookEdit",
    "TodoWrite",
    "AskUserQuestion",
}

# Required and optional frontmatter fields
REQUIRED_FIELDS = {"name", "description"}
OPTIONAL_FIELDS = {
    "tools",
    "disallowedTools",
    "model",
    "permissionMode",
    "maxTurns",
    "skills",
    "mcpServers",
    "hooks",
    "memory",
    "color",  # UI color for the agent
}
KNOWN_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


def extract_frontmatter(content: str) -> tuple[str | None, str | None, int]:
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


def validate_name(name: Any, result: ValidationResult) -> None:
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

    # Pattern check (lowercase letters, numbers, hyphens only, must start with letter)
    if not NAME_PATTERN.match(name):
        result.add_error(
            f"Field 'name' must start with a lowercase letter and contain only "
            f"lowercase letters, numbers, and hyphens. Got: '{name}'"
        )

    # Check for double hyphens
    if "--" in name:
        result.add_warning(
            f"Field 'name' contains consecutive hyphens. Consider using single hyphens: '{name}'"
        )

    # Check for trailing hyphen
    if name.endswith("-"):
        result.add_warning(f"Field 'name' ends with a hyphen: '{name}'")


def validate_description(description: Any, result: ValidationResult) -> None:
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

    # Quality checks
    desc_lower = description.lower()

    # Check for usage guidance
    usage_indicators = ["use when", "use for", "use this", "use proactively", "invoke"]
    has_usage_guidance = any(indicator in desc_lower for indicator in usage_indicators)
    if not has_usage_guidance:
        result.add_warning(
            "Description should include when to use the agent, "
            "e.g., 'Use when reviewing code...' or 'Use proactively after...'"
        )


def validate_model(model: Any, result: ValidationResult) -> None:
    """Validate the 'model' field."""
    if model is None:
        return

    if not isinstance(model, str):
        result.add_error(f"Field 'model' must be a string, got {type(model).__name__}")
        return

    model_lower = model.lower()
    if model_lower not in VALID_MODELS:
        result.add_error(
            f"Field 'model' has invalid value '{model}'. "
            f"Valid values are: {', '.join(sorted(VALID_MODELS))}"
        )


def validate_permission_mode(permission_mode: Any, result: ValidationResult) -> None:
    """Validate the 'permissionMode' field."""
    if permission_mode is None:
        return

    if not isinstance(permission_mode, str):
        result.add_error(
            f"Field 'permissionMode' must be a string, got {type(permission_mode).__name__}"
        )
        return

    if permission_mode not in VALID_PERMISSION_MODES:
        result.add_error(
            f"Field 'permissionMode' has invalid value '{permission_mode}'. "
            f"Valid values are: {', '.join(sorted(VALID_PERMISSION_MODES))}"
        )

    # Warn about dangerous permission modes
    if permission_mode == "bypassPermissions":
        result.add_warning(
            "permissionMode 'bypassPermissions' skips all permission checks. "
            "Use with caution."
        )


def validate_memory(memory: Any, result: ValidationResult) -> None:
    """Validate the 'memory' field."""
    if memory is None:
        return

    if not isinstance(memory, str):
        result.add_error(
            f"Field 'memory' must be a string, got {type(memory).__name__}"
        )
        return

    if memory not in VALID_MEMORY_SCOPES:
        result.add_error(
            f"Field 'memory' has invalid value '{memory}'. "
            f"Valid values are: {', '.join(sorted(VALID_MEMORY_SCOPES))}"
        )


def validate_max_turns(max_turns: Any, result: ValidationResult) -> None:
    """Validate the 'maxTurns' field."""
    if max_turns is None:
        return

    if not isinstance(max_turns, int) or isinstance(max_turns, bool):
        result.add_error(
            f"Field 'maxTurns' must be a positive integer, got {type(max_turns).__name__}"
        )
        return

    if max_turns <= 0:
        result.add_error(
            f"Field 'maxTurns' must be a positive integer, got {max_turns}"
        )


def validate_tools(tools: Any, field_name: str, result: ValidationResult) -> None:
    """Validate the 'tools' or 'disallowedTools' field."""
    if tools is None:
        return

    # Can be a string (comma-separated) or a list
    if isinstance(tools, str):
        tool_list = [t.strip() for t in tools.split(",") if t.strip()]
    elif isinstance(tools, list):
        tool_list = tools
    else:
        result.add_error(
            f"Field '{field_name}' must be a string or list, got {type(tools).__name__}"
        )
        return

    if not tool_list:
        result.add_warning(f"Field '{field_name}' is empty after parsing")
        return

    # Validate each tool
    for tool in tool_list:
        if not isinstance(tool, str):
            result.add_error(
                f"Field '{field_name}' contains non-string value: {tool}"
            )
            continue

        # Handle Task(agent_type) syntax
        tool_name = tool.split("(")[0].strip()

        # Check against known tools (info only, not an error since MCP tools exist)
        if tool_name not in KNOWN_TOOLS:
            result.add_info(
                f"Tool '{tool_name}' in '{field_name}' is not a built-in tool. "
                "This may be an MCP tool or a typo."
            )

    result.add_info(f"{field_name}: {', '.join(str(t) for t in tool_list)}")


def validate_skills(skills: Any, result: ValidationResult) -> None:
    """Validate the 'skills' field."""
    if skills is None:
        return

    if not isinstance(skills, list):
        result.add_error(
            f"Field 'skills' must be a list, got {type(skills).__name__}"
        )
        return

    for skill in skills:
        if not isinstance(skill, str):
            result.add_error(
                f"Field 'skills' contains non-string value: {skill}"
            )
        elif not skill.strip():
            result.add_warning("Field 'skills' contains empty skill name")


def validate_mcp_servers(mcp_servers: Any, result: ValidationResult) -> None:
    """Validate the 'mcpServers' field."""
    if mcp_servers is None:
        return

    if not isinstance(mcp_servers, (dict, list)):
        result.add_error(
            f"Field 'mcpServers' must be a mapping or list, got {type(mcp_servers).__name__}"
        )
        return

    if isinstance(mcp_servers, dict):
        for server_name, config in mcp_servers.items():
            if not isinstance(server_name, str):
                result.add_error(
                    f"MCP server name must be a string, got {type(server_name).__name__}"
                )
            if config is not None and not isinstance(config, dict):
                result.add_warning(
                    f"MCP server '{server_name}' config should be a mapping or null"
                )

        result.add_info(f"MCP servers configured: {', '.join(mcp_servers.keys())}")


def validate_hooks(hooks: Any, result: ValidationResult) -> None:
    """Validate the 'hooks' field."""
    if hooks is None:
        return

    if not isinstance(hooks, dict):
        result.add_error(
            f"Field 'hooks' must be a mapping, got {type(hooks).__name__}"
        )
        return

    for event_name, hook_config in hooks.items():
        if event_name not in VALID_HOOK_EVENTS:
            result.add_warning(
                f"Unknown hook event: '{event_name}'. "
                f"Known events are: {', '.join(sorted(VALID_HOOK_EVENTS))}"
            )

        if not isinstance(hook_config, list):
            result.add_error(
                f"Hook event '{event_name}' must have a list of hook definitions"
            )
            continue

        for i, hook_def in enumerate(hook_config):
            if not isinstance(hook_def, dict):
                result.add_error(
                    f"Hook definition {i + 1} in '{event_name}' must be a mapping"
                )
                continue

            # Check for required 'hooks' key in hook definition
            if "hooks" not in hook_def and "matcher" not in hook_def:
                result.add_warning(
                    f"Hook definition {i + 1} in '{event_name}' should have 'hooks' or 'matcher' key"
                )


def validate_frontmatter(frontmatter_str: str | None, result: ValidationResult) -> dict:
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
    validate_name(data.get("name"), result)
    validate_description(data.get("description"), result)

    # Validate optional fields
    validate_model(data.get("model"), result)
    validate_permission_mode(data.get("permissionMode"), result)
    validate_memory(data.get("memory"), result)
    validate_max_turns(data.get("maxTurns"), result)
    validate_tools(data.get("tools"), "tools", result)
    validate_tools(data.get("disallowedTools"), "disallowedTools", result)
    validate_skills(data.get("skills"), result)
    validate_mcp_servers(data.get("mcpServers"), result)
    validate_hooks(data.get("hooks"), result)

    # Check for unknown fields
    unknown_fields = set(data.keys()) - KNOWN_FIELDS
    if unknown_fields:
        for field_name in sorted(unknown_fields):
            result.add_warning(
                f"Unknown frontmatter field: '{field_name}'. "
                f"Known fields are: {', '.join(sorted(KNOWN_FIELDS))}"
            )

    return data


def validate_body(body: str, result: ValidationResult) -> None:
    """Validate the markdown body content (system prompt)."""
    if not body or not body.strip():
        result.add_warning(
            "Agent has no markdown body content. The body becomes the system prompt."
        )
        return

    lines = body.strip().split("\n")
    line_count = len(lines)

    # Check recommended line limit
    if line_count > MAX_RECOMMENDED_BODY_LINES:
        result.add_warning(
            f"Body exceeds recommended {MAX_RECOMMENDED_BODY_LINES} lines "
            f"(got {line_count}). Consider keeping the system prompt concise."
        )

    # Check for markdown structure
    has_headers = any(line.strip().startswith("#") for line in lines)
    if has_headers:
        result.add_info("System prompt uses markdown headers for structure")

    # Check for common patterns
    has_numbered_steps = any(
        re.match(r"^\d+\.", line.strip()) for line in lines
    )
    if has_numbered_steps:
        result.add_info("System prompt includes numbered steps")

    result.add_info(f"System prompt length: {len(body)} characters, {line_count} lines")


def validate_agent_file(file_path: Path) -> ValidationResult:
    """Validate a single agent markdown file."""
    result = ValidationResult()

    if not file_path.exists():
        result.add_error(f"File not found: {file_path}")
        return result

    if not file_path.is_file():
        result.add_error(f"Not a file: {file_path}")
        return result

    if not file_path.suffix == ".md":
        result.add_warning(f"Agent file should have .md extension: {file_path}")

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
    data = validate_frontmatter(frontmatter_str, result)

    # Validate body (system prompt)
    if body:
        validate_body(body, result)

    # Check filename matches name field
    if data.get("name"):
        expected_filename = f"{data['name']}.md"
        if file_path.name != expected_filename:
            result.add_warning(
                f"Filename '{file_path.name}' doesn't match name field '{data['name']}'. "
                f"Expected: '{expected_filename}'"
            )

    return result


def validate_agents_directory(dir_path: Path) -> ValidationResult:
    """Validate all agent files in a directory."""
    result = ValidationResult()

    if not dir_path.exists():
        result.add_error(f"Directory not found: {dir_path}")
        return result

    if not dir_path.is_dir():
        result.add_error(f"Not a directory: {dir_path}")
        return result

    # Find all .md files
    agent_files = list(dir_path.glob("*.md"))

    if not agent_files:
        result.add_warning(f"No .md files found in {dir_path}")
        return result

    result.add_info(f"Found {len(agent_files)} agent file(s)")

    # Validate each file
    for agent_file in sorted(agent_files):
        file_result = validate_agent_file(agent_file)

        # Prefix messages with filename
        for i, error in enumerate(file_result.errors):
            file_result.errors[i] = f"[{agent_file.name}] {error}"
        for i, warning in enumerate(file_result.warnings):
            file_result.warnings[i] = f"[{agent_file.name}] {warning}"
        for i, info in enumerate(file_result.info):
            file_result.info[i] = f"[{agent_file.name}] {info}"

        result.merge(file_result)

    return result


def format_result(result: ValidationResult, path: Path, verbose: bool = False) -> str:
    """Format validation result for display."""
    lines = []

    status = "VALID" if result.valid else "INVALID"
    lines.append(f"\n{'=' * 60}")
    lines.append(f"Validation result for: {path}")
    lines.append(f"Status: {status}")
    lines.append("=" * 60)

    if result.errors:
        lines.append(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            lines.append(f"   - {error}")

    if result.warnings:
        lines.append(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            lines.append(f"   - {warning}")

    if verbose and result.info:
        lines.append(f"\nInfo ({len(result.info)}):")
        for info in result.info:
            lines.append(f"   - {info}")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Claude Code agent files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s agent.md                     Validate a single file
  %(prog)s .claude/agents/              Validate all agents in directory
  %(prog)s agent.md --verbose           Show all info messages
  %(prog)s --strict agent.md            Treat warnings as errors
        """,
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to agent .md file or agents directory",
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
        result = validate_agent_file(path)
    elif path.is_dir():
        result = validate_agents_directory(path)
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
