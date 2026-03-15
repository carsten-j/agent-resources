---
name: update-claude-md

description: Update the project's CLAUDE.md with meta learnings, conventions, gotchas, and significant codebase changes. Use when the user asks to update CLAUDE.md, capture learnings, document project conventions, or reflect recent work in the project guide.
disable-model-invocation: true
---

# Update CLAUDE.md with learnings

CLAUDE.md is the project's institutional knowledge — the things a new developer (or a new Claude session) needs to know that aren't obvious from the code itself. The goal is to keep it concise, current, and high-signal.

## What belongs in CLAUDE.md

Include information that saves future sessions from re-discovering things the hard way:

- **Conventions and philosophy** — e.g., "Prefer composition over inheritance", "No backwards compatibility unless explicitly requested"
- **Non-obvious gotchas** — Things that cause repeated bugs or confusion
- **Build/test/run commands** — How to run, test, lint, deploy
- **Project structure** — Key directories and their purpose, especially if the layout is non-standard
- **Recent significant changes** — New capabilities, major refactors, or architectural shifts that change how the project works

## What does NOT belong

Skip anything that's either ephemeral or derivable from the code:

- Bug fix details — the fix is in the code, the context is in the commit message
- Implementation details obvious from reading the source
- Temporary workarounds that will be removed soon
- One-off decisions that won't recur

**Rule of thumb**: Would you tell a new developer this on their first day? If yes, add it. If it's just details about today's work, skip it.

## Instructions

1. **Read CLAUDE.md** — If it exists, understand what's already documented so you don't duplicate. If it doesn't exist, you'll create it.
2. **Review recent work** — Run `git log --oneline -20` and `git diff HEAD~5..HEAD --stat` to identify significant changes. Look for patterns: new scripts, moved directories, changed conventions, recurring issues.
3. **Extract meta learnings** — From the recent work and the current conversation, identify anything that fits the "what belongs" criteria above.
4. **Update conservatively** — Keep CLAUDE.md under 300 lines. If adding new content pushes it over, remove outdated entries first. Prefer updating existing sections over adding new ones.

## Output

After updating, summarize:
- What was added/changed
- What was removed (if anything)
- Current line count
