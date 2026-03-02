You are a coding agent. Read through this repository and create an
`CLAUDE.md` file at the repo root.

Requirements:

- Include a short codebase map that helps an agent find files quickly.
- Focus on entry points, directory roles, naming conventions, configuration wiring, and test locations.
- Add a section called "Local norms" with repo-specific rules you infer from the code and tooling.
- Add a section called "Self-correction" with two explicit instructions:
  - If the code map is discovered to be stale, update it.
  - If the user gives a correction about how work should be done in this repo, add it to "Local norms" (or another clearly labeled section) so future sessions inherit it.

Process:

- Use search and targeted file reads, do not read every file.
- Prefer `rg` searches to find entry points and configs.
- Prefer high-signal files: `README`, `pyproject.toml`, `package.json`, `Makefile`, `opencode.json`, `.github/workflows`, and top-level `src` or `app` directories.

Output:

- Write the final `CLAUDE.md` contents in Markdown.
- Keep it concise. Optimize for navigation and correctness.
