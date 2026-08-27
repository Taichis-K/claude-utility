#!/usr/bin/env bash
#
# open-claude.ps1 の macOS 版。
# 自分（このシェルが属する VS Code ウィンドウ）に新しい Claude Code タブを開く。
#
# vscode:// URI は既定では「フォーカス中のウィンドウ」に配られるが、VS Code 本体の
# URLHandlerRouter がクエリの windowId=<数値> を読んで window:<id> の接続へ
# ルーティングする（未文書。Windows 版と同じ仕組みで、macOS でも実測で確認済み）。
#
# 自ウィンドウの ID は、拡張ホストの PID（このシェルの親）が記録されている
# ログディレクトリ名 window<N> から求める。ウィンドウタイトルやワークスペース名に
# 依存しないので、同じフォルダを複数ウィンドウで開いていても一意に決まる。
#
#   open-claude.sh                        新規セッション
#   open-claude.sh -Session <UUID>        既存セッションの再開
#   open-claude.sh -Prompt "<文字列>"     初期プロンプト付きで新規
#   open-claude.sh -NoWindowId            windowId を付けない（フォーカス中のウィンドウ）
#
# Windows 版と引数名を合わせてあるので、POSIX 風の --session / --prompt / --no-window-id も受ける。
set -euo pipefail

session=''
prompt=''
no_window_id=0

while [ $# -gt 0 ]; do
    case "$1" in
    -Session | --session)
        session="${2-}"
        [ $# -ge 2 ] || { echo "$1 に値が無い" >&2; exit 2; }
        shift 2
        ;;
    -Prompt | --prompt)
        prompt="${2-}"
        [ $# -ge 2 ] || { echo "$1 に値が無い" >&2; exit 2; }
        shift 2
        ;;
    -NoWindowId | --no-window-id)
        no_window_id=1
        shift
        ;;
    *)
        echo "不明な引数: $1" >&2
        exit 2
        ;;
    esac
done

# --- 自ウィンドウの windowId を求める ---
# 拡張ホストは再起動しうるので、ログは 1 行目だけでなくファイル全体を見る。
get_my_window_id() {
    [ -n "${CLAUDE_PID-}" ] || return 1
    local exthost logroot f w
    exthost="$(ps -o ppid= -p "$CLAUDE_PID" 2>/dev/null | tr -d '[:space:]')"
    [ -n "$exthost" ] || return 1

    logroot="$HOME/Library/Application Support/Code/logs"
    [ -d "$logroot" ] || return 1

    # 更新時刻の新しいログから順に見る（PID は再利用されるので古いログを先に当てない）
    while IFS= read -r f; do
        if grep -qF "Extension host with pid $exthost started" "$f" 2>/dev/null; then
            w="$(basename "$(dirname "$(dirname "$f")")")"
            case "$w" in
            window*)
                printf '%s' "${w#window}"
                return 0
                ;;
            esac
        fi
    done <<EOF
$(ls -dt "$logroot"/*/window*/exthost/exthost.log 2>/dev/null)
EOF
    return 1
}

window_id=''
if [ "$no_window_id" = 1 ]; then
    echo "windowId: 指定しない（フォーカス中のウィンドウに開く）"
else
    window_id="$(get_my_window_id || true)"
    if [ -z "$window_id" ]; then
        echo "警告: windowId を特定できなかった。フォーカス中のウィンドウに開く。"
    else
        # 日本語が直後に続くので ${} で括る（LC_ALL 次第で bash 3.2 が高位バイトを変数名の一部と読む）
        echo "windowId: ${window_id}（自ウィンドウ）"
    fi
fi

# --- URI を組み立てる ---
# 日本語プロンプトが壊れないよう、文字単位ではなくバイト単位で percent-encode する
# （LC_ALL=C にすると ${#s} と ${s:i:1} がバイト単位になる）。
urlencode() {
    local LC_ALL=C
    local s="$1" i c out=''
    for ((i = 0; i < ${#s}; i++)); do
        c="${s:i:1}"
        case "$c" in
        [a-zA-Z0-9.~_-]) out="$out$c" ;;
        # bash 3.2 の printf "'<文字>" は 0x80 以上のバイトを符号拡張するので 0xFF で潰す
        *) out="$out$(printf '%%%02X' "$(( $(printf '%d' "'$c") & 0xFF ))")" ;;
        esac
    done
    printf '%s' "$out"
}

qs=''
append_qs() { if [ -z "$qs" ]; then qs="$1"; else qs="$qs&$1"; fi; }
[ -n "$window_id" ] && append_qs "windowId=$window_id"
[ -n "$session" ] && append_qs "session=$(urlencode "$session")"
[ -n "$prompt" ] && append_qs "prompt=$(urlencode "$prompt")"

uri='vscode://anthropic.claude-code/open'
[ -n "$qs" ] && uri="$uri?$qs"

# --- 送信する ---
# macOS では open(1) が LaunchServices 経由で「起動中の VS Code」に URL を渡すので、
# Windows 版のような ELECTRON_RUN_AS_NODE / VSCODE_* の除去は要らない
# （env を継承するのは新規にアプリを起動するときだけで、その場合も launchd の環境が使われる）。
# -g はフォアグラウンド化しない指定。windowId で宛先を決めるのでフォーカスを奪う必要が無い。
echo "送信: $uri"
if open -g "$uri" 2>/tmp/open-claude-stderr.$$; then
    rm -f "/tmp/open-claude-stderr.$$"
    echo "結果: 成功（終了コード 0）"
else
    code=$?
    echo "結果: 失敗 終了コード=$code"
    [ -s "/tmp/open-claude-stderr.$$" ] && echo "stderr: $(cat "/tmp/open-claude-stderr.$$")"
    rm -f "/tmp/open-claude-stderr.$$"
    exit 1
fi
