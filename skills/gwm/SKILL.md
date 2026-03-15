---
name: gwm
description: Manage git worktrees using the gwm script. Supports creating, listing, removing, and checking status of worktrees. Use when the user says "create git worktree", "new worktree", or needs to work with multiple branches simultaneously via git worktrees.
disable-model-invocation: false
---

# Git Worktree Manager (gwm)

Manage git worktrees using the `gwm.sh` script located at `skills/gwm/scripts/gwm.sh` in the agent-resources repo.

## Arguments

The user invokes this skill as `/gwm <command> [args]`, or by saying something like "create git worktree for KKEP-1234". Parse the command and arguments from the user's input. If the user says "create worktree" or similar without specifying a command, treat it as `add`.

Supported commands:
- `add <branch-name> [sparse-path]` — Create a new worktree (optionally with sparse checkout)
- `list` — List all worktrees
- `remove <branch-name>` — Remove a worktree and optionally delete the branch
- `status <branch-name>` — Show dirty state, ahead/behind for a worktree
- `prune` — Clean up stale worktree references
- `help` — Show available commands

Flags:
- `--plain` — Human-readable output (always use this when presenting results)
- `--no-restore` — Skip dotnet restore and file copying after creating a worktree

## Configuration

The script uses two directory paths, configurable via environment variables:
- `GWM_SRC_DIR` — The main git repository (default: `/d/kkep/projects/kk.erhvervsportal`)
- `GWM_WORKTREE_DIR` — Where worktrees are created (default: `/d/worktrees/kkep`)

## Branch naming convention

Before running the `add` command, validate the branch name against the expected pattern `KKEP-XYZQ` where `XYZQ` is a four-digit number (e.g. `KKEP-1234`, `KKEP-5678`).

- If the branch name does **not** match this pattern, **warn the user** that the name deviates from the convention and ask for confirmation before proceeding.
- If the user confirms, proceed with the provided name.
- This validation only applies to the `add` command.

## Instructions

1. **Locate the script**
   - The script is at: `skills/gwm/scripts/gwm.sh` (relative to the agent-resources repo root)
   - It must be run from within the source git repository configured in the script (`SRC_DIR`)

2. **Run the command**
   - Execute: `bash skills/gwm/scripts/gwm.sh <command> [args]`
   - The script outputs JSON by default. Add `--plain` for human-readable output
   - Always use `--plain` when presenting results to the user

3. **Handle the output**
   - On success (`status: ok`): present the message and relevant data to the user
   - On error (`status: error`): show the error message and suggest corrective action

4. **After creating a worktree** (successful `add` command)
   - Use `cd` to change into the worktree folder (the path reported in the output)
   - This ensures subsequent commands run in the context of the new worktree

5. **Examples**
   - Create a worktree: `bash skills/gwm/scripts/gwm.sh add KKEP-1234 --plain`
   - Create with sparse checkout: `bash skills/gwm/scripts/gwm.sh add KKEP-1234 src/MyProject --plain`
   - Create without restore: `bash skills/gwm/scripts/gwm.sh add KKEP-1234 --no-restore --plain`
   - List worktrees: `bash skills/gwm/scripts/gwm.sh list --plain`
   - Check status: `bash skills/gwm/scripts/gwm.sh status KKEP-1234 --plain`
   - Remove a worktree: `bash skills/gwm/scripts/gwm.sh remove KKEP-1234 --plain`
   - Clean up stale references: `bash skills/gwm/scripts/gwm.sh prune --plain`

6. **If no command is provided**, run `bash skills/gwm/scripts/gwm.sh help --plain` and show the available commands.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| "Branch already exists locally" | Branch was previously created | Use `gwm status <branch>` to inspect, or `gwm remove <branch>` first |
| "Incomplete worktree found" | Previous creation failed partway | Run `gwm remove <branch>` to clean up, then retry |
| "Sparse path not found" | The path doesn't exist in the repo | Check the path with `git ls-tree --name-only HEAD` |
| "SRC_DIR does not exist" | Env not configured for this machine | Set `GWM_SRC_DIR` environment variable |
| "dotnet restore failed" | Build dependencies issue | Use `--no-restore` to skip, then restore manually |
