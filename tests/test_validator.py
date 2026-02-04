"""Tests for the SKILL.md validator."""

import tempfile
from pathlib import Path

import pytest

from validator import (
    ValidationResult,
    extract_frontmatter,
    validate_name,
    validate_description,
    validate_allowed_tools,
    validate_context_field,
    validate_model_field,
    validate_boolean_field,
    validate_hooks_field,
    validate_body,
    validate_string_substitutions,
    validate_frontmatter,
    validate_skill_file,
    validate_skill_directory,
    validate_references,
    format_result,
    MAX_NAME_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_RECOMMENDED_BODY_LINES,
)


class TestValidationResult:
    """Tests for the ValidationResult class."""

    def test_initial_state(self):
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.info == []

    def test_add_error_marks_invalid(self):
        result = ValidationResult()
        result.add_error("test error")
        assert result.valid is False
        assert "test error" in result.errors

    def test_add_warning_keeps_valid(self):
        result = ValidationResult()
        result.add_warning("test warning")
        assert result.valid is True
        assert "test warning" in result.warnings

    def test_add_info_keeps_valid(self):
        result = ValidationResult()
        result.add_info("test info")
        assert result.valid is True
        assert "test info" in result.info

    def test_merge_combines_results(self):
        result1 = ValidationResult()
        result1.add_error("error1")
        result1.add_warning("warning1")

        result2 = ValidationResult()
        result2.add_error("error2")
        result2.add_info("info2")

        result1.merge(result2)
        assert result1.valid is False
        assert "error1" in result1.errors
        assert "error2" in result1.errors
        assert "warning1" in result1.warnings
        assert "info2" in result1.info

    def test_merge_valid_into_invalid(self):
        result1 = ValidationResult()
        result1.add_error("error")

        result2 = ValidationResult()
        result2.add_info("info")

        result1.merge(result2)
        assert result1.valid is False

    def test_merge_invalid_into_valid(self):
        result1 = ValidationResult()
        result1.add_info("info")

        result2 = ValidationResult()
        result2.add_error("error")

        result1.merge(result2)
        assert result1.valid is False


class TestExtractFrontmatter:
    """Tests for the extract_frontmatter function."""

    def test_valid_frontmatter(self):
        content = """---
name: test-skill
description: A test skill
---
# Body content
"""
        frontmatter, body, end_line = extract_frontmatter(content)
        assert frontmatter == "name: test-skill\ndescription: A test skill"
        assert "# Body content" in body
        assert end_line == 4

    def test_no_frontmatter(self):
        content = "# Just markdown\nNo frontmatter here"
        frontmatter, body, end_line = extract_frontmatter(content)
        assert frontmatter is None
        assert body == content
        assert end_line == 0

    def test_unclosed_frontmatter(self):
        content = """---
name: test-skill
description: A test skill
"""
        frontmatter, body, end_line = extract_frontmatter(content)
        assert frontmatter is None
        assert body == content
        assert end_line == 0

    def test_empty_frontmatter(self):
        content = """---
---
Body here
"""
        frontmatter, body, end_line = extract_frontmatter(content)
        assert frontmatter == ""
        assert "Body here" in body

    def test_frontmatter_not_at_start(self):
        content = """Some text
---
name: test
---
"""
        frontmatter, body, end_line = extract_frontmatter(content)
        assert frontmatter is None


class TestValidateName:
    """Tests for the validate_name function."""

    def test_valid_name(self):
        result = ValidationResult()
        validate_name("my-skill", result)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_name_with_numbers(self):
        result = ValidationResult()
        validate_name("skill-v2", result)
        assert result.valid is True

    def test_empty_name(self):
        result = ValidationResult()
        validate_name("", result)
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_name_too_long(self):
        result = ValidationResult()
        long_name = "a" * (MAX_NAME_LENGTH + 1)
        validate_name(long_name, result)
        assert result.valid is False
        assert any("exceeds maximum length" in e for e in result.errors)

    def test_name_at_max_length(self):
        result = ValidationResult()
        max_name = "a" * MAX_NAME_LENGTH
        validate_name(max_name, result)
        assert not any("exceeds maximum length" in e for e in result.errors)

    def test_name_with_uppercase(self):
        result = ValidationResult()
        validate_name("My-Skill", result)
        assert result.valid is False
        assert any("lowercase" in e for e in result.errors)

    def test_name_with_underscore(self):
        result = ValidationResult()
        validate_name("my_skill", result)
        assert result.valid is False
        assert any("lowercase letters, numbers, and hyphens" in e for e in result.errors)

    def test_name_with_spaces(self):
        result = ValidationResult()
        validate_name("my skill", result)
        assert result.valid is False

    def test_name_with_reserved_word_claude(self):
        result = ValidationResult()
        validate_name("claude-helper", result)
        assert result.valid is False
        assert any("reserved word" in e for e in result.errors)

    def test_name_with_reserved_word_anthropic(self):
        result = ValidationResult()
        validate_name("anthropic-tool", result)
        assert result.valid is False
        assert any("reserved word" in e for e in result.errors)

    def test_name_with_xml_tags(self):
        result = ValidationResult()
        validate_name("<script>skill</script>", result)
        assert result.valid is False
        assert any("XML tags" in e for e in result.errors)

    def test_name_non_string(self):
        result = ValidationResult()
        validate_name(123, result)
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)

    def test_name_gerund_suggestion(self):
        result = ValidationResult()
        validate_name("pdf-process", result)
        assert any("gerund" in i.lower() for i in result.info)

    def test_name_with_gerund_no_suggestion(self):
        result = ValidationResult()
        validate_name("processing-pdfs", result)
        assert not any("gerund" in i.lower() for i in result.info)


class TestValidateDescription:
    """Tests for the validate_description function."""

    def test_valid_description(self):
        result = ValidationResult()
        validate_description("Use this skill when working with PDF files.", result)
        assert result.valid is True

    def test_empty_description(self):
        result = ValidationResult()
        validate_description("", result)
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_description_too_long(self):
        result = ValidationResult()
        long_desc = "a" * (MAX_DESCRIPTION_LENGTH + 1)
        validate_description(long_desc, result)
        assert result.valid is False
        assert any("exceeds maximum length" in e for e in result.errors)

    def test_description_with_xml_tags(self):
        result = ValidationResult()
        validate_description("Process <data> elements", result)
        assert result.valid is False
        assert any("XML tags" in e for e in result.errors)

    def test_description_non_string(self):
        result = ValidationResult()
        validate_description(["list", "of", "things"], result)
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)

    def test_vague_description_warning(self):
        result = ValidationResult()
        validate_description("This helps with stuff", result)
        assert any("vague" in w.lower() for w in result.warnings)

    def test_missing_usage_guidance_warning(self):
        result = ValidationResult()
        validate_description("Processes PDF files efficiently", result)
        assert any("when to use" in w.lower() for w in result.warnings)

    def test_first_person_warning(self):
        result = ValidationResult()
        validate_description("I can help you with PDF files", result)
        assert any("third person" in w.lower() for w in result.warnings)

    def test_good_description_no_warnings(self):
        result = ValidationResult()
        validate_description(
            "Processes PDF files. Use when you need to extract text from PDF documents.",
            result,
        )
        # Should have no warnings about vagueness or missing usage guidance
        assert not any("vague" in w.lower() for w in result.warnings)
        assert not any("when to use" in w.lower() for w in result.warnings)


class TestValidateAllowedTools:
    """Tests for the validate_allowed_tools function."""

    def test_none_allowed_tools(self):
        result = ValidationResult()
        validate_allowed_tools(None, result)
        assert result.valid is True

    def test_valid_allowed_tools(self):
        result = ValidationResult()
        validate_allowed_tools("Read, Write, Bash", result)
        assert result.valid is True
        assert any("Read" in i for i in result.info)

    def test_non_string_allowed_tools(self):
        result = ValidationResult()
        validate_allowed_tools(["Read", "Write"], result)
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)

    def test_empty_allowed_tools_warning(self):
        result = ValidationResult()
        validate_allowed_tools("   ", result)
        assert any("empty" in w.lower() for w in result.warnings)


class TestValidateContextField:
    """Tests for the validate_context_field function."""

    def test_none_context(self):
        result = ValidationResult()
        validate_context_field(None, None, result)
        assert result.valid is True

    def test_valid_fork_context(self):
        result = ValidationResult()
        validate_context_field("fork", None, result)
        assert result.valid is True

    def test_invalid_context(self):
        result = ValidationResult()
        validate_context_field("invalid", None, result)
        assert result.valid is False
        assert any("invalid value" in e.lower() for e in result.errors)

    def test_agent_without_context_warning(self):
        result = ValidationResult()
        validate_context_field(None, "some-agent", result)
        assert any("agent" in w.lower() and "context" in w.lower() for w in result.warnings)

    def test_non_string_context(self):
        result = ValidationResult()
        validate_context_field(123, None, result)
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)


class TestValidateModelField:
    """Tests for the validate_model_field function."""

    def test_none_model(self):
        result = ValidationResult()
        validate_model_field(None, result)
        assert result.valid is True

    def test_valid_model_opus(self):
        result = ValidationResult()
        validate_model_field("opus", result)
        assert result.valid is True

    def test_valid_model_sonnet(self):
        result = ValidationResult()
        validate_model_field("sonnet", result)
        assert result.valid is True

    def test_valid_model_haiku(self):
        result = ValidationResult()
        validate_model_field("haiku", result)
        assert result.valid is True

    def test_unknown_model_info(self):
        result = ValidationResult()
        validate_model_field("custom-model", result)
        assert result.valid is True
        assert any("common values" in i.lower() for i in result.info)

    def test_non_string_model(self):
        result = ValidationResult()
        validate_model_field(123, result)
        assert result.valid is False
        assert any("must be a string" in e for e in result.errors)


class TestValidateBooleanField:
    """Tests for the validate_boolean_field function."""

    def test_none_value(self):
        result = ValidationResult()
        validate_boolean_field({"user-invocable": None}, "user-invocable", result)
        assert result.valid is True

    def test_missing_field(self):
        result = ValidationResult()
        validate_boolean_field({}, "user-invocable", result)
        assert result.valid is True

    def test_true_value(self):
        result = ValidationResult()
        validate_boolean_field({"user-invocable": True}, "user-invocable", result)
        assert result.valid is True

    def test_false_value(self):
        result = ValidationResult()
        validate_boolean_field({"user-invocable": False}, "user-invocable", result)
        assert result.valid is True

    def test_string_value(self):
        result = ValidationResult()
        validate_boolean_field({"user-invocable": "true"}, "user-invocable", result)
        assert result.valid is False
        assert any("must be a boolean" in e for e in result.errors)

    def test_integer_value(self):
        result = ValidationResult()
        validate_boolean_field({"user-invocable": 1}, "user-invocable", result)
        assert result.valid is False


class TestValidateHooksField:
    """Tests for the validate_hooks_field function."""

    def test_none_hooks(self):
        result = ValidationResult()
        validate_hooks_field(None, result)
        assert result.valid is True

    def test_valid_hooks(self):
        result = ValidationResult()
        validate_hooks_field({"PreToolUse": {}, "PostToolUse": {}}, result)
        assert result.valid is True

    def test_unknown_hook_type_warning(self):
        result = ValidationResult()
        validate_hooks_field({"UnknownHook": {}}, result)
        assert any("unknown hook type" in w.lower() for w in result.warnings)

    def test_non_dict_hooks(self):
        result = ValidationResult()
        validate_hooks_field("PreToolUse", result)
        assert result.valid is False
        assert any("must be a mapping" in e for e in result.errors)


class TestValidateBody:
    """Tests for the validate_body function."""

    def test_empty_body_warning(self):
        result = ValidationResult()
        validate_body("", result)
        assert any("no markdown body" in w.lower() for w in result.warnings)

    def test_whitespace_only_body(self):
        result = ValidationResult()
        validate_body("   \n  \n  ", result)
        assert any("no markdown body" in w.lower() for w in result.warnings)

    def test_body_exceeds_line_limit(self):
        result = ValidationResult()
        long_body = "\n".join(["line"] * (MAX_RECOMMENDED_BODY_LINES + 1))
        validate_body(long_body, result)
        assert any("exceeds recommended" in w.lower() for w in result.warnings)

    def test_windows_path_warning(self):
        result = ValidationResult()
        validate_body("Use the file at C:\\Users\\path", result)
        assert any("windows-style path" in w.lower() for w in result.warnings)

    def test_dci_directive_info(self):
        result = ValidationResult()
        validate_body("Get the date: !`date`", result)
        assert any("dynamic context injection" in i.lower() for i in result.info)

    def test_markdown_headers_suggestion(self):
        result = ValidationResult()
        validate_body("Just plain text without any headers", result)
        assert any("markdown headers" in i.lower() for i in result.info)

    def test_code_blocks_info(self):
        result = ValidationResult()
        validate_body("```python\nprint('hello')\n```", result)
        assert any("code blocks" in i.lower() for i in result.info)


class TestValidateStringSubstitutions:
    """Tests for the validate_string_substitutions function."""

    def test_shell_variable_expansion_error(self):
        result = ValidationResult()
        validate_string_substitutions("Use ${HOME} for paths", result)
        assert result.valid is False
        assert any("unsupported" in e.lower() for e in result.errors)

    def test_jinja_template_error(self):
        result = ValidationResult()
        validate_string_substitutions("Hello {{name}}", result)
        assert result.valid is False
        assert any("unsupported" in e.lower() for e in result.errors)

    def test_env_variable_error(self):
        result = ValidationResult()
        validate_string_substitutions("Use $HOME_DIR for paths", result)
        assert result.valid is False
        assert any("unsupported" in e.lower() for e in result.errors)

    def test_windows_env_variable_error(self):
        result = ValidationResult()
        validate_string_substitutions("Use %USERPROFILE% for paths", result)
        assert result.valid is False
        assert any("unsupported" in e.lower() for e in result.errors)

    def test_substitution_in_code_block_ok(self):
        result = ValidationResult()
        content = """Some text
```bash
echo ${HOME}
```
More text"""
        validate_string_substitutions(content, result)
        assert result.valid is True

    def test_valid_dci_pattern(self):
        result = ValidationResult()
        validate_string_substitutions("Get date: !`date`", result)
        assert result.valid is True


class TestValidateFrontmatter:
    """Tests for the validate_frontmatter function."""

    def test_valid_frontmatter(self):
        result = ValidationResult()
        data = validate_frontmatter("name: test-skill\ndescription: Use when testing", result)
        assert result.valid is True
        assert data["name"] == "test-skill"

    def test_none_frontmatter(self):
        result = ValidationResult()
        validate_frontmatter(None, result)
        assert result.valid is False
        assert any("missing" in e.lower() for e in result.errors)

    def test_invalid_yaml(self):
        result = ValidationResult()
        validate_frontmatter("name: [invalid", result)
        assert result.valid is False
        assert any("invalid yaml" in e.lower() for e in result.errors)

    def test_non_dict_frontmatter(self):
        result = ValidationResult()
        validate_frontmatter("- item1\n- item2", result)
        assert result.valid is False
        assert any("must be a yaml mapping" in e.lower() for e in result.errors)

    def test_unknown_fields_error(self):
        result = ValidationResult()
        validate_frontmatter(
            "name: test\ndescription: Use when testing\nunknown-field: value",
            result,
        )
        assert result.valid is False
        assert any("unknown frontmatter field" in e.lower() for e in result.errors)

    def test_all_optional_fields_valid(self):
        result = ValidationResult()
        frontmatter = """
name: test-skill
description: Use when testing
allowed-tools: Read, Write
model: sonnet
context: fork
agent: my-agent
user-invocable: true
disable-model-invocation: false
argument-hint: <file>
hooks:
  PreToolUse: {}
"""
        validate_frontmatter(frontmatter, result)
        # Should not have errors about unknown fields
        assert not any("unknown frontmatter field" in e.lower() for e in result.errors)


class TestValidateSkillFile:
    """Tests for the validate_skill_file function."""

    def test_nonexistent_file(self):
        result = validate_skill_file(Path("/nonexistent/SKILL.md"))
        assert result.valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_valid_skill_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("""---
name: test-skill
description: Use when testing the validator
---
# Test Skill

This is a test skill body.
""")
            f.flush()
            result = validate_skill_file(Path(f.name))
            assert result.valid is True

    def test_skill_file_missing_frontmatter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Just markdown\nNo frontmatter")
            f.flush()
            result = validate_skill_file(Path(f.name))
            assert result.valid is False

    def test_directory_instead_of_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_skill_file(Path(tmpdir))
            assert result.valid is False
            assert any("not a file" in e.lower() for e in result.errors)


class TestValidateSkillDirectory:
    """Tests for the validate_skill_directory function."""

    def test_nonexistent_directory(self):
        result = validate_skill_directory(Path("/nonexistent/dir"))
        assert result.valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_file_instead_of_directory(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            result = validate_skill_directory(Path(f.name))
            assert result.valid is False
            assert any("not a directory" in e.lower() for e in result.errors)

    def test_directory_without_skill_md(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_skill_directory(Path(tmpdir))
            assert result.valid is False
            assert any("skill.md not found" in e.lower() for e in result.errors)

    def test_valid_skill_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_file = Path(tmpdir) / "SKILL.md"
            skill_file.write_text("""---
name: test-skill
description: Use when testing the validator
---
# Test Skill
""")
            result = validate_skill_directory(Path(tmpdir))
            assert result.valid is True

    def test_directory_with_additional_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_file = Path(tmpdir) / "SKILL.md"
            skill_file.write_text("""---
name: test-skill
description: Use when testing the validator
---
# Test Skill
""")
            extra_file = Path(tmpdir) / "helper.py"
            extra_file.write_text("# helper script")

            result = validate_skill_directory(Path(tmpdir))
            assert result.valid is True
            assert any("additional files" in i.lower() for i in result.info)


class TestValidateReferences:
    """Tests for the validate_references function."""

    def test_valid_local_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            helper_file = skill_dir / "helper.py"
            helper_file.write_text("# helper")

            result = ValidationResult()
            validate_references("[helper](helper.py)", skill_dir, result)
            assert any("exists" in i.lower() for i in result.info)

    def test_missing_local_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            result = ValidationResult()
            validate_references("[missing](missing.py)", skill_dir, result)
            assert any("not found" in w.lower() for w in result.warnings)

    def test_url_references_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            result = ValidationResult()
            validate_references("[link](https://example.com)", skill_dir, result)
            # No warnings about missing files for URLs
            assert not any("not found" in w.lower() for w in result.warnings)

    def test_anchor_references_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir)
            result = ValidationResult()
            validate_references("[section](#my-section)", skill_dir, result)
            assert not any("not found" in w.lower() for w in result.warnings)


class TestFormatResult:
    """Tests for the format_result function."""

    def test_valid_result_format(self):
        result = ValidationResult()
        output = format_result(result, Path("SKILL.md"))
        assert "VALID" in output
        assert "SKILL.md" in output

    def test_invalid_result_format(self):
        result = ValidationResult()
        result.add_error("Test error")
        output = format_result(result, Path("SKILL.md"))
        assert "INVALID" in output
        assert "Test error" in output

    def test_warnings_displayed(self):
        result = ValidationResult()
        result.add_warning("Test warning")
        output = format_result(result, Path("SKILL.md"))
        assert "Test warning" in output

    def test_info_hidden_by_default(self):
        result = ValidationResult()
        result.add_info("Test info")
        output = format_result(result, Path("SKILL.md"), verbose=False)
        assert "Test info" not in output

    def test_info_shown_when_verbose(self):
        result = ValidationResult()
        result.add_info("Test info")
        output = format_result(result, Path("SKILL.md"), verbose=True)
        assert "Test info" in output
