#!/usr/bin/env bash
# Claude Code 共通資産(~/.claude)とこのリポジトリを同期するスクリプト
# Windows(Git Bash) / macOS 共通で動作する。
#
#   ./sync.sh diff        差分を表示する(何も変更しない)
#   ./sync.sh to-local    リポジトリ → ~/.claude へ反映(反映前に ~/.claude/backups へ退避)
#   ./sync.sh from-local  ~/.claude → リポジトリへ収集(git diff で確認してからコミットする)
#
# 対象: commands/, scripts/, skills/
# (CLAUDE.md はこのリポジトリのプロジェクト指示であり、~/.claude とは同期しない)
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
LOCAL="$HOME/.claude"
DIRS=(commands scripts skills)

# ミラー同期: 宛先を消してからコピーする(宛先だけにあるものは消える)
mirror() { # <src> <dst>
    rm -rf "$2"
    mkdir -p "$(dirname "$2")"
    cp -R "$1" "$2"
}

show_diff() { # <label> <a> <b>
    if [ ! -e "$2" ]; then echo "$1: $2 が存在しない"; return 1; fi
    if [ ! -e "$3" ]; then echo "$1: $3 が存在しない"; return 1; fi
    diff -rq "$2" "$3" >/dev/null 2>&1 || { echo "--- $1"; diff -rq "$2" "$3" || true; return 1; }
    return 0
}

case "${1:-}" in
diff)
    same=1
    for d in "${DIRS[@]}"; do show_diff "$d" "$LOCAL/$d" "$REPO/$d" || same=0; done
    [ "$same" = 1 ] && echo "差分なし"
    ;;
from-local)
    for d in "${DIRS[@]}"; do mirror "$LOCAL/$d" "$REPO/$d"; done
    echo "収集完了。git diff で内容を確認してからコミットしてください。"
    ;;
to-local)
    # ミラーはリポジトリに無いローカルファイルを消すため、反映前に対象一式を退避する
    backup="$LOCAL/backups/sync-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$backup"
    for d in "${DIRS[@]}"; do
        [ -e "$LOCAL/$d" ] && cp -R "$LOCAL/$d" "$backup/$d"
    done
    echo "退避: $backup"
    for d in "${DIRS[@]}"; do mirror "$REPO/$d" "$LOCAL/$d"; done
    echo "反映完了"
    ;;
*)
    echo "usage: $0 {diff|to-local|from-local}" >&2
    exit 2
    ;;
esac
