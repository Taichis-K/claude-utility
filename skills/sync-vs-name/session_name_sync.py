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

- セッション名は `~/.claude/sessions/<PID>.json` の `name` にあり、**他セッションの
  `ListAgents` と `claude agents --json` は外部プロセスが書き換えた値をそのまま読む**
- **`nameSource` は `"user"` にする**（`/rename` が書く値。実測）。
  Remote Control / VSCode 拡張のブリッジ経由の `/list-agents` は
  「人が選んだ名前」以外を伏せる（"not chosen by a human are withheld on this
  connection"）。その判定はこのキーで行われるらしく、`name` だけ直して `nameSource` を
  消した状態では **"(unnamed session)" と表示された**。以前の実装（消す）はこれを踏んだ
- **限界**: 動いているプロセス自身が出す「This session is <名前>」（自分の `ListAgents`
  の1行目）はメモリ上の値で、ファイルを書き換えても追随しない（`/rename` でだけ変わる）。
  他セッションからの到達と `claude agents --json` には効くので、用途はそこまで
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

# 本体プロセスも同じファイルを read-modify-write する。VSCode を開き直して複数の
# セッションが同時に resume すると、本体がファイルを開いている瞬間に当たり、Windows では
# os.replace が PermissionError、read が途中書き込みの不正 JSON になる（実測: 2026-09-23）。
# どちらも一瞬なので、短い間隔で数回やり直す（合計でもフックの timeout より十分短い）。
_WRITE_ATTEMPTS = 6
_WRITE_RETRY_SEC = 0.25

# `/rename` が書く nameSource の値（`~/.claude/sessions/<PID>.json` で実測）。
# ブリッジ経由の `/list-agents` は、この値でない名前を「人が選んでいない」として伏せる
_NAME_SOURCE_USER = "user"

# 結果ログ（~/.claude/logs/sync-vs-name.log）の上限。超えたら 1 世代だけ残して始め直す
_LOG_MAX_BYTES = 256 * 1024

# initialUserMessage で Claude に報告させる source。報告は毎回 1 往復ぶんのトークンを使う。
# initialUserMessage は startup / resume / clear でだけ効き compact では無視される
# （公式 docs では確認できず、2026-09-23 に実測。Nekochans の SessionStart フックでも使用中）
_REPORT_SOURCES = ("resume", "clear")
# これが設定されていれば報告させない（入れ子の `claude -p` などでも SessionStart フックは走るため）
_QUIET_ENV = "SYNC_VS_NAME_QUIET"


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


def _write_json(path: Path, payload: dict) -> None:
    """同じディレクトリに一時ファイルを作って `os.replace` で差し替える。

    Windows では、相手プロセス（Claude 本体）がそのファイルを開いている間は
    `os.replace` が PermissionError になる（実測）。同じ瞬間でも**同じファイルへの
    上書き**は通るので、その場合だけ直接書く。

    直接書きは原子的でなく、書いている一瞬は本体から空や途中の JSON が見えうる。
    先に文字列化して 1 回の write で済ませ、その窓を最小にする（書いた後は
    ``apply_name`` が読み直して確かめる）。
    """
    text = json.dumps(payload)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.replace(tmp_name, path)
            return
        except PermissionError:
            pass
        with path.open("w", encoding="utf-8") as handle:
            handle.write(text)
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def apply_name(
    pid_file: Path, title: str, now_ms: int, sleep=time.sleep
) -> tuple[str, str | None, str | None]:
    """pid ファイルの `name` を `title` にする。``(結果, 実際の name, 最後のエラー)`` を返す。

    結果は ``"unchanged"`` / ``"updated"`` / ``"lost"`` / ``"failed"``。

    - **他のキーを落とさない**（本体プロセスが書いた `peerFeatures` 等がある）。ただし読んでから
      書くまでの間に本体が他のキーを書き換えると、その変更を古い値で巻き戻しうる（構造上避けられない）
    - `nameSource` は **`"user"` にする**（`/rename` が書く値）。`"derived"` は
      「cwd から自動生成」の印で、これが付いた（または `nameSource` が無い）名前は
      ブリッジ経由の `/list-agents` で "(unnamed session)" と伏せられる
    - `name` が既に一致していても `nameSource` が `"user"` でなければ書き直す
      （旧実装が `nameSource` を消して書いたファイルを、この版で直せるように）
    - 書いたあと**読み直して確かめる**。本体プロセスも同じファイルを
      read-modify-write するので、書き負けがありうる（`"lost"`）
    - 読み書きの OSError と読み取りの不正 JSON は、本体が書いている最中に当たった
      一瞬の状態として扱い、少し待ってやり直す。回数を使い切ったら ``"failed"``
      （``"lost"`` は、読み書き自体は通ったのに毎回書き負けた場合）
    """
    last_seen: str | None = None
    last_error: str | None = None
    wrote = False  # 一度でも書き込みが通ったか（読み直し失敗の後に自分の値を読んで unchanged と誤報しない）
    for attempt in range(_WRITE_ATTEMPTS):
        if attempt:
            sleep(_WRITE_RETRY_SEC)
        try:
            current = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            last_error = repr(exc)
            continue
        if not isinstance(current, dict):
            last_error = "session info file is not a JSON object"
            continue
        last_seen = current.get("name") if isinstance(current.get("name"), str) else None
        if last_seen == title and current.get("nameSource") == _NAME_SOURCE_USER:
            return ("updated" if wrote else "unchanged"), last_seen, None

        payload = dict(current)
        payload["name"] = title
        payload["nameSource"] = _NAME_SOURCE_USER
        payload["nameSince"] = now_ms
        payload["updatedAt"] = now_ms
        try:
            _write_json(pid_file, payload)
        except OSError as exc:
            last_error = repr(exc)
            continue
        wrote = True

        try:
            after = json.loads(pid_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            last_error = repr(exc)
            continue
        actual = after.get("name") if isinstance(after, dict) else None
        last_seen = actual if isinstance(actual, str) else None
        source_ok = isinstance(after, dict) and after.get("nameSource") == _NAME_SOURCE_USER
        if last_seen == title and source_ok:
            return "updated", last_seen, None
        last_error = None
    if last_error is not None:
        return "failed", last_seen, last_error
    return "lost", last_seen, None


def _read_state(pid_file: Path) -> tuple[str | None, str | None]:
    """pid ファイルの ``(name, nameSource)`` を返す。読めなければ ``(None, None)``。"""
    try:
        obj = json.loads(pid_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, None
    if not isinstance(obj, dict):
        return None, None
    name = obj.get("name")
    source = obj.get("nameSource")
    return (
        name if isinstance(name, str) else None,
        source if isinstance(source, str) else None,
    )


def format_status(
    result: str,
    note: str,
    title: str | None,
    name: str | None,
    source: str | None,
    pid_file: Path | None,
    memory: str | None = None,
) -> str:
    """固定フォーマットで現状を出す。1 行目が結果、以降が状態（値が無いものは ``-``）。

    ``memory`` は実行中プロセスがメモリ上で持つ自分の名前（``ListAgents`` の
    「This session is <名前>」）。ファイルからは取れないので呼び出し側が渡す。表示のみ。
    """

    def q(value: str | None) -> str:
        return repr(value) if value is not None else "-"

    return "\n".join(
        [
            f"SESSION_NAME_{result} {note}",
            f"  title : {q(title)}  (conversation title, set by /rename)",
            f"  name  : {q(name)}  (session name shown in /list-agents)",
            f"  source: {q(source)}  (must be 'user' to be visible to other sessions)",
            f"  file  : {pid_file if pid_file is not None else '-'}",
            f"  memory: {q(memory)}  (name the running process calls itself; changes only via /rename or restart)",
        ]
    )


def sync(
    session_id: str,
    projects_dir: Path,
    sessions_dir: Path,
    now_ms: int,
    dry_run: bool = False,
    waiter=wait_for_pid_file,
    memory_name: str | None = None,
) -> tuple[str, str | None]:
    """同期を1回試みる。``(結果, メッセージ)`` を返す。

    どの結果でも**固定フォーマットのメッセージを返す**（1 行目が ``SESSION_NAME_<結果>``、
    以降に title / name / source / file / memory）。出すかどうかは ``main`` が決める
    （SessionStart の ``startup`` で同期対象が無いときだけ出さない）。
    """

    def _status(*args, **kwargs) -> str:
        return format_status(*args, memory=memory_name, **kwargs)

    transcript = find_transcript(projects_dir, session_id)
    if transcript is None:
        return "no_transcript", _status(
            "UNKNOWN", "transcript not found or ambiguous", None, None, None, None
        )
    title = read_last_custom_title(transcript)
    if title is None:
        # 会話に名前が付いていなくても、現在のセッション名は報告する
        pid_file = find_pid_file(sessions_dir, session_id)
        name, source = _read_state(pid_file) if pid_file is not None else (None, None)
        return "no_title", _status(
            "INFO", "no conversation title set (run /rename <name>, then rerun)",
            None, name, source, pid_file,
        )

    pid_file = waiter(sessions_dir, session_id)
    if pid_file is None:
        return "no_pid_file", _status(
            "UNKNOWN", "session info file not found or ambiguous", title, None, None, None
        )
    if dry_run:
        name, source = _read_state(pid_file)
        return "dry_run", _status(
            "DRY_RUN", "would write the conversation title as the session name",
            title, name, source, pid_file,
        )

    outcome, _, error = apply_name(pid_file, title, now_ms)
    name, source = _read_state(pid_file)
    if outcome == "updated":
        return outcome, _status(
            "SYNCED", "session name updated to match the conversation title",
            title, name, source, pid_file,
        )
    if outcome == "unchanged":
        return outcome, _status("UNCHANGED", "already in sync", title, name, source, pid_file)
    if outcome == "lost":
        return outcome, _status(
            "NOT_SYNCED", "write was reverted right after writing; other sessions see the name below",
            title, name, source, pid_file,
        )
    detail = f": {error}" if error else ""
    return "failed", _status(
        "NOT_SYNCED",
        f"cannot read/write the session info file{detail}",
        title, name, source, pid_file,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", help="stdin/環境変数の代わりに使う")
    parser.add_argument(
        "--dry-run", action="store_true", help="書き換えず、対象と名前だけ出す"
    )
    parser.add_argument(
        "--memory-name",
        help="実行中プロセスがメモリ上で持つ自分の名前（ListAgents の This session is <名前>）。表示のみで書き込まない",
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
        result, message = sync(
            session_id=session_id,
            projects_dir=projects_dir,
            sessions_dir=sessions_dir,
            now_ms=int(time.time() * 1000),
            dry_run=args.dry_run,
            memory_name=args.memory_name,
        )
    except Exception as exc:  # noqa: BLE001 — フックでセッション起動を止めない
        # 想定外の失敗も通常の結果と同じ経路（ログ・フック時は JSON）で出す
        result, message = "failed", f"SESSION_NAME_NOT_SYNCED unexpected failure: {exc!r}"

    _append_log(message, hook_input.get("source"), session_id)

    # 新規セッションの起動（source: startup）では transcript も会話タイトルもまだ無い。
    # 同期するものが無いだけなので、毎回「UNKNOWN」を会話に流し込まない（ログには残す）
    if hook_input.get("source") == "startup" and result in ("no_transcript", "no_title"):
        return 0

    if hook_input.get("hook_event_name") == "SessionStart":
        # フックの素の stdout は Claude のコンテキストに入るだけで人の画面に出ない。
        # JSON で返し、systemMessage（画面表示）に 1 行要約、additionalContext に全文を入れる
        specific = {"hookEventName": "SessionStart", "additionalContext": message}
        # VSCode 拡張は systemMessage を画面に出さず、additionalContext だけではモデルも動かない。
        # resume / clear では毎回 initialUserMessage を付けて Claude に報告させる
        # （ユーザーが打ったものとして処理される。startup・compact では出さない／効かない）
        if hook_input.get("source") in _REPORT_SOURCES and not env.get(_QUIET_ENV):
            specific["initialUserMessage"] = _report_request(message)
        print(
            json.dumps(
                {
                    "systemMessage": _summary_line(message, hook_input.get("source")),
                    "hookSpecificOutput": specific,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    else:
        print(message, flush=True)
    return 0


def _report_request(message: str) -> str:
    """resume / clear 直後に Claude へ渡す定型の依頼文。"""
    # memory 行はフックからは取れない（プロセスのメモリ上の値）ので、Claude に埋めさせる
    block = "\n".join(
        line.replace("memory: -", "memory: '<ListAgents の名前>'", 1)
        if line.strip().startswith("memory:")
        else line
        for line in message.splitlines()
    )
    return (
        "【sync-vs-name の定型報告（セッション再開時に自動で送られたメッセージ）】\n"
        "ListAgents ツールを呼び、1 行目「This session is <名前>」の名前で下のブロックの "
        "<ListAgents の名前> を置き換え、ブロック全体をコードブロックでそのまま"
        "（要約・言い換えせず）報告してください:\n\n"
        f"{block}\n\n"
        "報告が済んだら止まってください。他の作業は始めないでください。"
    )


_SUMMARY_JA = {
    "SESSION_NAME_SYNCED": "同期しました",
    "SESSION_NAME_UNCHANGED": "既に一致",
    "SESSION_NAME_INFO": "会話タイトル未設定（/rename で付けてください）",
    "SESSION_NAME_NOT_SYNCED": "失敗",
    "SESSION_NAME_UNKNOWN": "対象を特定できず",
    "SESSION_NAME_DRY_RUN": "dry-run",
}


def _summary_line(message: str, source: str | None) -> str:
    """画面に出す 1 行。例: ``sync-vs-name (resume): 同期しました → 'ClaudeCodeTest'``"""
    first = message.splitlines()[0]
    code = first.split(" ", 1)[0]
    text = _SUMMARY_JA.get(code, code)
    name = None
    for line in message.splitlines()[1:]:
        if line.strip().startswith("name  :"):
            name = line.split(":", 1)[1].split("(", 1)[0].strip()
    line = f"sync-vs-name ({source or '-'}): {text}"
    if name and name != "-":
        line += f" → {name}"
    if code == "SESSION_NAME_NOT_SYNCED":
        line += f" [{first.split(' ', 1)[1] if ' ' in first else ''}]"
    return line


def _append_log(message: str, source: str | None, session_id: str) -> None:
    """``~/.claude/logs/sync-vs-name.log`` に 1 行追記する。失敗しても黙って続ける。

    ``_LOG_MAX_BYTES`` を超えたら ``.log.1`` に退避して（1 世代だけ）新しく始める。
    """
    try:
        log_dir = Path.home() / ".claude" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "sync-vs-name.log"
        try:
            if log_file.stat().st_size > _LOG_MAX_BYTES:
                # 複数セッションが同時に超過を見ても二重に退避しないよう、先に自分専用の名前へ
                # 移して「確保」する。確保できるのは 1 プロセスだけで、負けた側は OSError で抜ける
                claimed = log_file.with_name(f"{log_file.name}.{os.getpid()}.rotating")
                os.replace(log_file, claimed)
                os.replace(claimed, log_file.with_name(log_file.name + ".1"))
        except OSError:
            pass
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        first = message.splitlines()[0]
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}\t{source or 'manual'}\t{session_id}\t{first}\n")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
