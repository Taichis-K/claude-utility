#!/usr/bin/env python3
"""会話タイトル（`/rename` で付ける名前）を**セッション名**（`/list-agents` に出る名前）に同期する。

Claude Code には名前が **3つ**ある。混同すると「rename したのに届かない」が起きる:

| 名前 | 実体 | 誰が見るか |
|---|---|---|
| 会話タイトル | transcript の `custom-title` 行（`/rename` が書く保存値） | VSCode のタブの元ネタ |
| セッション名 | `~/.claude/sessions/<PID>.json` の `name` | **`/list-agents`・他セッションからの送信先** |
| 表示中のタブ文字列 | VSCode 拡張が会話タイトルを描画したもの（反映が遅れることがある） | 人の目だけ |

このスクリプトは **会話タイトル → セッション名** を同期する（スキルからの手動実行でも
SessionStart フックとしての実行でも同じ）。動機は、セッション名のファイルが
**PID をファイル名**として持たれていること: VSCode を開き直すと新しい PID になり、
名前は cwd から自動生成（`nameSource: "derived"`）に戻る。

実測で確認した事実（この実装の前提）:

- セッション名は `~/.claude/sessions/<PID>.json` の `name` にあり、**外部プロセスから
  書き換えた値がそのまま `/list-agents` に出る**
- 通信の同一性は隣の `<PID>.<hash>.key` 内の `peerToken` が担っており、
  **このスクリプトはそのファイルに触れない**＝名前を書き換えても通信は壊れない
- 起動時に名前を渡す手段（`--name` / `CLAUDE_CODE_SESSION_NAME`）は
  **VSCode 拡張からは使えない**（拡張の設定はワークスペース単位で、
  セッション単位の入口が無い）。だから起動**後**に直すこの道具が要る

**プロジェクト非依存**（標準ライブラリのみ・他モジュールを import しない）。
他のリポジトリにそのままコピーして使える。

同期の失敗では**呼び出し側を止めない**（原則 exit 0。引数の指定誤りだけは
argparse が exit 2 を返す）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# pid ファイルは起動直後に書かれるが、SessionStart フックとの前後関係は
# 保証されていない。短いあいだだけ待つ（フックの timeout より十分短く）。
_PID_FILE_WAIT_SEC = 2.0
_PID_FILE_POLL_SEC = 0.1

# 本体プロセスも同じファイルを read-modify-write する。書き負けたときに
# 1度だけやり直す（それでも駄目なら黙らずに報告する）。
_WRITE_ATTEMPTS = 2


def read_hook_input() -> dict:
    """stdin の JSON を読む。読めなければ空 dict。

    **stdin が TTY なら読まない**——手動実行で入力待ちに入って固まる事故を防ぐ。
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
    except Exception:  # noqa: BLE001 — 入力が読めなくてもフックは落とさない
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_session_id(hook_input: dict, env: dict[str, str]) -> str | None:
    """セッション ID を stdin → 環境変数の順で解決する。"""
    value = hook_input.get("session_id")
    if isinstance(value, str) and value:
        return value
    value = env.get("CLAUDE_CODE_SESSION_ID")
    if isinstance(value, str) and value:
        return value
    return None


def find_transcript(projects_dir: Path, session_id: str) -> Path | None:
    """`<projects_dir>/*/<session_id>.jsonl` を1件に解決する。

    0件・2件以上はどちらも None（**曖昧なまま書きに行かない**）。
    """
    candidates = sorted(projects_dir.glob(f"*/{session_id}.jsonl"))
    if len(candidates) != 1:
        return None
    return candidates[0]


def read_last_custom_title(path: Path) -> str | None:
    """transcript の `custom-title` 行の**最後**の `customTitle` を返す。

    - パース不能な行はスキップ（1行の破損で全体を諦めない）
    - **行内の `sessionId` は見ない**——resume 系譜で複製され、実測で不一致がある
    - 候補が無ければ None（＝人が名前を付けていない。**推測しない**）
    """
    last: str | None = None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "custom-title":
                    continue
                title = obj.get("customTitle")
                if isinstance(title, str) and title.strip():
                    last = title
    except OSError:
        return None
    return last


def find_pid_file(sessions_dir: Path, session_id: str) -> Path | None:
    """`sessionId` が一致する `~/.claude/sessions/<PID>.json` を1件に解決する。

    **PID では引かない。** フックの親プロセスが Claude 本体とは限らない
    （シェル経由で起動される）。一致が 0 件・2 件以上なら None。
    """
    matches: list[Path] = []
    try:
        entries = sorted(sessions_dir.glob("*.json"))
    except OSError:
        return None
    for path in entries:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("sessionId") == session_id:
            matches.append(path)
    if len(matches) != 1:
        return None
    return matches[0]


def wait_for_pid_file(
    sessions_dir: Path,
    session_id: str,
    timeout_sec: float = _PID_FILE_WAIT_SEC,
    poll_sec: float = _PID_FILE_POLL_SEC,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> Path | None:
    """pid ファイルが現れるまで短く待つ。現れなければ None。"""
    deadline = monotonic() + timeout_sec
    while True:
        found = find_pid_file(sessions_dir, session_id)
        if found is not None:
            return found
        if monotonic() >= deadline:
            return None
        sleep(poll_sec)


def _write_atomic(path: Path, payload: dict) -> None:
    """同じディレクトリに一時ファイルを作って `os.replace` で差し替える。"""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def apply_name(pid_file: Path, title: str, now_ms: int) -> tuple[str, str | None]:
    """pid ファイルの `name` を `title` にする。``(結果, 実際の name)`` を返す。

    結果は ``"unchanged"`` / ``"updated"`` / ``"lost"`` / ``"failed"``。

    - **他のキーを落とさない**（本体プロセスが書いた `peerFeatures` 等がある）
    - `nameSource` は**消す**。残っている `"derived"` / `"auto"` は
      「自動生成なので衝突時に譲ってよい」印で、人が付けた名前には付かない
    - 書いたあと**読み直して確かめる**。本体プロセスも同じファイルを
      read-modify-write するので、書き負けがありうる（`"lost"`）
    """
    last_seen: str | None = None
    for _ in range(_WRITE_ATTEMPTS):
        try:
            current = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return "failed", None
        if not isinstance(current, dict):
            return "failed", None
        last_seen = current.get("name") if isinstance(current.get("name"), str) else None
        if last_seen == title:
            return "unchanged", last_seen

        payload = dict(current)
        payload["name"] = title
        payload.pop("nameSource", None)
        payload["nameSince"] = now_ms
        payload["updatedAt"] = now_ms
        try:
            _write_atomic(pid_file, payload)
        except OSError:
            return "failed", last_seen

        try:
            after = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return "failed", last_seen
        actual = after.get("name") if isinstance(after, dict) else None
        last_seen = actual if isinstance(actual, str) else None
        if last_seen == title:
            return "updated", last_seen
    return "lost", last_seen


def format_updated(title: str) -> str:
    return (
        f"SESSION_NAME_SYNCED session name now matches the conversation "
        f"title {title!r} (the name shown in /list-agents)."
    )


def format_lost(title: str, actual: str | None) -> str:
    return (
        f"SESSION_NAME_NOT_SYNCED could not set the session name to {title!r} "
        f"(it was reverted to {actual!r} right after writing). Other sessions will "
        "reach this session by that name, not by the conversation title."
    )


def format_failed() -> str:
    return (
        "SESSION_NAME_NOT_SYNCED failed to sync the session name "
        "(cannot read/write the session info file)."
    )


def sync(
    session_id: str,
    projects_dir: Path,
    sessions_dir: Path,
    now_ms: int,
    dry_run: bool = False,
    waiter=wait_for_pid_file,
) -> tuple[str, str | None]:
    """同期を1回試みる。``(結果, メッセージ)`` を返す。

    結果 ``"no_title"`` / ``"no_pid_file"`` / ``"no_transcript"`` は
    **黙って終わる**（名前を付けていない・対象ファイルがまだ無い・候補が複数で
    絞れない、のいずれか。SKILL.md の「何も出ない」に対応する）。
    """
    transcript = find_transcript(projects_dir, session_id)
    if transcript is None:
        return "no_transcript", None
    title = read_last_custom_title(transcript)
    if title is None:
        return "no_title", None

    pid_file = waiter(sessions_dir, session_id)
    if pid_file is None:
        return "no_pid_file", None
    if dry_run:
        return "dry_run", f"{pid_file} <- {title!r}"

    outcome, actual = apply_name(pid_file, title, now_ms)
    if outcome == "updated":
        return outcome, format_updated(title)
    if outcome == "unchanged":
        return outcome, None
    if outcome == "lost":
        return outcome, format_lost(title, actual)
    return "failed", format_failed()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", help="stdin/環境変数の代わりに使う")
    parser.add_argument(
        "--dry-run", action="store_true", help="書き換えず、対象と名前だけ出す"
    )
    args = parser.parse_args(argv)

    hook_input = {} if args.session_id else read_hook_input()
    env = dict(os.environ)
    session_id = args.session_id or resolve_session_id(hook_input, env)
    if not session_id:
        return 0

    projects_dir = Path(
        env.get("CLAUDE_PROJECTS_DIR") or (Path.home() / ".claude" / "projects")
    ).expanduser()
    sessions_dir = Path(
        env.get("CLAUDE_SESSIONS_DIR") or (Path.home() / ".claude" / "sessions")
    ).expanduser()

    # Windows では stdout が cp932 になり、UTF-8 で読む受け側で化けるので固定する
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        _, message = sync(
            session_id=session_id,
            projects_dir=projects_dir,
            sessions_dir=sessions_dir,
            now_ms=int(time.time() * 1000),
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 — フックでセッション起動を止めない
        print(f"SESSION_NAME_NOT_SYNCED unexpected failure: {exc!r}", flush=True)
        return 0

    if message:
        print(message, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
