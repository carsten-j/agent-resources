#!/bin/bash
# Git Worktree Manager (gwm)
# All commands emit a JSON envelope:
#   { "status": "ok"|"error", "command": "...", "message": "...", "data": { ... } }
#
# Usage: gwm add <branch-name> [sparse-path]
#        gwm list
#        gwm remove <branch-name>
#        gwm status <branch-name>
#        gwm prune
#
# Options:
#   --plain       Human-readable output instead of JSON
#   --no-restore  Skip dotnet restore and file copying (add only)

set -euo pipefail

SRC_DIR="${GWM_SRC_DIR:-/d/kkep/projects/kk.erhvervsportal}"
WORKTREE_DIR="${GWM_WORKTREE_DIR:-/d/worktrees/kkep}"

# ── Flags ────────────────────────────────────────────────────
PLAIN=false
NO_RESTORE=false
for arg in "$@"; do
    [[ "$arg" == "--plain" ]] && PLAIN=true
    [[ "$arg" == "--no-restore" ]] && NO_RESTORE=true
done
# Strip flags from positional args
args=()
for arg in "$@"; do
    [[ "$arg" != "--plain" && "$arg" != "--no-restore" ]] && args+=("$arg")
done
set -- "${args[@]+"${args[@]}"}"

cmd="${1:-}"
branch="${2:-}"
sparse_path="${3:-}"

# ── JSON helpers ─────────────────────────────────────────────
json_kv() {
    # Safely encode a string value for JSON (handles quotes, backslashes, newlines)
    local v="$1"
    v="${v//\\/\\\\}"
    v="${v//\"/\\\"}"
    v="${v//$'\n'/\\n}"
    v="${v//$'\t'/\\t}"
    printf '%s' "$v"
}

emit() {
    local status="$1" command="$2" message="$3" data="${4:-\{\}}"

    if $PLAIN; then
        if [[ "$status" == "error" ]]; then
            echo "ERROR: $message" >&2
        else
            echo "$message"
            # Pretty-print data keys if present and not empty object
            if [[ "$data" != "{}" ]]; then
                echo "$data" | python3 -m json.tool 2>/dev/null || echo "$data"
            fi
        fi
    else
        cat <<EOF
{"status":"${status}","command":"$(json_kv "$command")","message":"$(json_kv "$message")","data":${data}}
EOF
    fi

    [[ "$status" == "error" ]] && exit 1
    return 0
}

# ── Validation ───────────────────────────────────────────────
require_branch() {
    if [[ -z "$branch" ]]; then
        emit "error" "$cmd" "Missing required argument: branch-name" \
            '{"usage":"gwm '"$cmd"' <branch-name>"}'
    fi
}

preflight() {
    if ! command -v git &>/dev/null; then
        emit "error" "$cmd" "git is not installed or not in PATH" '{}'
    fi
    if [[ ! -d "$SRC_DIR" ]]; then
        emit "error" "$cmd" "SRC_DIR does not exist: $SRC_DIR (set GWM_SRC_DIR to override)" \
            "{\"src_dir\":\"$(json_kv "$SRC_DIR")\"}"
    fi
    if ! git -C "$SRC_DIR" rev-parse --git-dir &>/dev/null; then
        emit "error" "$cmd" "SRC_DIR is not a git repository: $SRC_DIR" \
            "{\"src_dir\":\"$(json_kv "$SRC_DIR")\"}"
    fi
    if [[ ! -d "$WORKTREE_DIR" ]]; then
        mkdir -p "$WORKTREE_DIR" 2>/dev/null || \
            emit "error" "$cmd" "Cannot create WORKTREE_DIR: $WORKTREE_DIR (set GWM_WORKTREE_DIR to override)" \
                "{\"worktree_dir\":\"$(json_kv "$WORKTREE_DIR")\"}"
    fi
}

# ── Commands ─────────────────────────────────────────────────
do_add() {
    require_branch
    local worktree_path="$WORKTREE_DIR/$branch"
    local err

    # Check if branch already exists locally
    if git -C "$SRC_DIR" show-ref --verify --quiet "refs/heads/$branch" 2>/dev/null; then
        emit "error" "add" "Branch '$branch' already exists locally. Use 'gwm status $branch' to inspect it" \
            "{\"branch\":\"$(json_kv "$branch")\"}"
    fi

    # Detect existing or incomplete worktree
    if [[ -d "$worktree_path" ]]; then
        if [[ -f "$worktree_path/.git" ]]; then
            emit "error" "add" "Worktree already exists at $worktree_path" \
                "{\"path\":\"$(json_kv "$worktree_path")\"}"
        else
            emit "error" "add" "Incomplete worktree found at $worktree_path. Run 'gwm remove $branch' to clean up" \
                "{\"path\":\"$(json_kv "$worktree_path")\",\"incomplete\":true}"
        fi
    fi

    # Validate sparse path exists in the repo
    if [[ -n "$sparse_path" ]]; then
        if ! git -C "$SRC_DIR" ls-tree --name-only HEAD "$sparse_path" &>/dev/null ||
           [[ -z "$(git -C "$SRC_DIR" ls-tree --name-only HEAD "$sparse_path" 2>/dev/null)" ]]; then
            emit "error" "add" "Sparse path '$sparse_path' not found in repository" \
                "{\"sparse_path\":\"$(json_kv "$sparse_path")\"}"
        fi
    fi

    if [[ -n "$sparse_path" ]]; then
        if ! err=$(git worktree add --no-checkout "$worktree_path" -b "$branch" 2>&1); then
            emit "error" "add" "Failed to create worktree: $err" \
                "{\"branch\":\"$(json_kv "$branch")\",\"detail\":\"$(json_kv "$err")\"}"
        fi
        cd "$worktree_path"
        git sparse-checkout init --cone
        git sparse-checkout set "$sparse_path"
        git sparse-checkout add .husky
        git sparse-checkout add .config
        if ! err=$(git checkout "$branch" 2>&1); then
            emit "error" "add" "Failed to checkout branch: $err" \
                "{\"branch\":\"$(json_kv "$branch")\",\"detail\":\"$(json_kv "$err")\"}"
        fi
    else
        if ! err=$(git worktree add "$worktree_path" -b "$branch" 2>&1); then
            emit "error" "add" "Failed to create worktree: $err" \
                "{\"branch\":\"$(json_kv "$branch")\",\"detail\":\"$(json_kv "$err")\"}"
        fi
    fi

    if ! $NO_RESTORE; then
        cd "$worktree_path/src"
        if ! err=$(dotnet restore --verbosity quiet 2>&1); then
            emit "error" "add" "Worktree created but dotnet restore failed: $err" \
                "{\"branch\":\"$(json_kv "$branch")\",\"path\":\"$(json_kv "$worktree_path")\",\"detail\":\"$(json_kv "$err")\"}"
        fi

        # Copy shell scripts
        cp "$SRC_DIR"/src/*.sh "$worktree_path/src/" 2>/dev/null || true

        # Copy agent and Claude configuration
        for dir in .agents .claude; do
            if [[ -d "$SRC_DIR/src/$dir" ]]; then
                cp -r "$SRC_DIR/src/$dir" "$worktree_path/src/$dir"
            fi
        done
    fi

    local sparse_info="null"
    [[ -n "$sparse_path" ]] && sparse_info="\"$sparse_path\""

    emit "ok" "add" "Worktree created for branch '$branch'" \
        "{\"branch\":\"$(json_kv "$branch")\",\"path\":\"$(json_kv "$worktree_path")\",\"sparse_path\":${sparse_info},\"restored\":$( $NO_RESTORE && echo false || echo true )}"
}

do_list() {
    local entries="[]"
    local items=()

    while IFS= read -r line; do
        # git worktree list --porcelain gives structured blocks
        local wt_path="" wt_branch="" wt_commit="" bare=false

        while IFS= read -r field; do
            [[ -z "$field" ]] && break
            case "$field" in
                worktree\ *)  wt_path="${field#worktree }" ;;
                HEAD\ *)      wt_commit="${field#HEAD }" ;;
                branch\ *)    wt_branch="${field#branch refs/heads/}" ;;
                bare)         bare=true ;;
            esac
        done

        [[ -z "$wt_path" ]] && continue

        items+=("{\"path\":\"$(json_kv "$wt_path")\",\"branch\":\"$(json_kv "$wt_branch")\",\"commit\":\"$(json_kv "$wt_commit")\",\"bare\":$bare}")
    done < <(git worktree list --porcelain; echo "")

    # Join array
    local joined=""
    for i in "${!items[@]}"; do
        [[ $i -gt 0 ]] && joined+=","
        joined+="${items[$i]}"
    done

    emit "ok" "list" "Found ${#items[@]} worktree(s)" \
        "{\"count\":${#items[@]},\"worktrees\":[${joined}]}"
}

do_remove() {
    require_branch
    local worktree_path="$WORKTREE_DIR/$branch"

    if [[ ! -d "$worktree_path" ]]; then
        emit "error" "remove" "Worktree not found at $worktree_path" \
            "{\"path\":\"$(json_kv "$worktree_path")\"}"
    fi

    git worktree remove --force "$worktree_path" 2>/dev/null
    local branch_deleted=false
    if git branch -d "$branch" 2>/dev/null; then
        branch_deleted=true
    fi

    emit "ok" "remove" "Removed worktree for branch '$branch'" \
        "{\"branch\":\"$(json_kv "$branch")\",\"path\":\"$(json_kv "$worktree_path")\",\"branch_deleted\":$branch_deleted}"
}

do_status() {
    require_branch
    local worktree_path="$WORKTREE_DIR/$branch"

    if [[ ! -d "$worktree_path" ]]; then
        emit "error" "status" "Worktree not found at $worktree_path" \
            "{\"path\":\"$(json_kv "$worktree_path")\"}"
    fi

    cd "$worktree_path"
    local commit head_ref dirty=false ahead=0 behind=0

    commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    head_ref=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")

    if [[ -n $(git status --porcelain 2>/dev/null) ]]; then
        dirty=true
    fi

    # Ahead/behind tracking branch
    local upstream
    upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || echo "")
    if [[ -n "$upstream" ]]; then
        ahead=$(git rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)
        behind=$(git rev-list --count 'HEAD..@{upstream}' 2>/dev/null || echo 0)
    fi

    emit "ok" "status" "Status for '$branch'" \
        "{\"branch\":\"$(json_kv "$branch")\",\"path\":\"$(json_kv "$worktree_path")\",\"commit\":\"$(json_kv "$commit")\",\"head\":\"$(json_kv "$head_ref")\",\"dirty\":$dirty,\"ahead\":$ahead,\"behind\":$behind}"
}

do_prune() {
    local output
    output=$(git worktree prune --verbose 2>&1) || true
    local pruned=0
    if [[ -n "$output" ]]; then
        pruned=$(echo "$output" | wc -l | tr -d ' ')
    fi

    emit "ok" "prune" "Pruned $pruned stale worktree reference(s)" \
        "{\"pruned\":$pruned,\"detail\":\"$(json_kv "$output")\"}"
}

do_help() {
    emit "ok" "help" "Git Worktree Manager — agent-friendly output" \
        "{\"commands\":{\"add\":{\"args\":\"<branch-name> [sparse-path]\",\"description\":\"Create a new worktree with optional sparse checkout\"},\"list\":{\"args\":\"\",\"description\":\"List all worktrees with branch and commit info\"},\"remove\":{\"args\":\"<branch-name>\",\"description\":\"Remove worktree and optionally delete branch\"},\"status\":{\"args\":\"<branch-name>\",\"description\":\"Show dirty state, ahead/behind for a worktree\"},\"prune\":{\"args\":\"\",\"description\":\"Clean up stale worktree references\"},\"help\":{\"args\":\"\",\"description\":\"Show this help\"}},\"options\":{\"--plain\":\"Human-readable output instead of JSON\",\"--no-restore\":\"Skip dotnet restore and file copying after creating worktree\"},\"config\":{\"src_dir\":\"$(json_kv "$SRC_DIR")\",\"worktree_dir\":\"$(json_kv "$WORKTREE_DIR")\"}}"
}

# ── Dispatch ─────────────────────────────────────────────────
[[ "$cmd" != "help" && -n "$cmd" ]] && preflight

case "${cmd}" in
    add)    do_add    ;;
    list)   do_list   ;;
    remove) do_remove ;;
    status) do_status ;;
    prune)  do_prune  ;;
    help|"") do_help  ;;
    *)
        emit "error" "$cmd" "Unknown command: $cmd" \
            '{"known_commands":["add","list","remove","status","prune","help"]}'
        ;;
esac
