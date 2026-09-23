---
name: sync-vs-name
description: 会話タイトル（VSCode のタブに出る名前）をセッション名（/list-agents に出る名前）に同期する。VSCode を開き直したり /clear した後にセッション名が自動生成に戻ったとき、名前を打ち直さずに戻す。
allowed-tools: Bash
---

# 会話タイトルをセッション名に同期する

同じディレクトリの `session_name_sync.py` を呼ぶだけ。**自分で名前を組み立てたり、
`~/.claude/sessions/*.json` を直接編集したりしないこと。**

1. まず `ListAgents` ツールを呼び、1 行目「This session is **<名前>** [ref]」の名前を取る
   （実行中プロセスがメモリ上で持つ自分の名前。ファイルには無いので、これだけは呼び出し側が渡す）
2. その名前を `--memory-name` に渡してスクリプトを実行する

```bash
s=.claude/skills/sync-vs-name/session_name_sync.py
[ -f "$s" ] || s=~/.claude/skills/sync-vs-name/session_name_sync.py
python "$s" --memory-name "<1 行目の名前>" </dev/null 2>/dev/null || python3 "$s" --memory-name "<1 行目の名前>" </dev/null
```

プロジェクト(`.claude/skills/`)にあればそちらを、無ければユーザー(`~/.claude/skills/`)のものを使う。

`</dev/null` を必ず付ける（スクリプト自体は TTY からは読まないが、非 TTY で stdin が
開いたままの実行環境では読みに行って固まるため）。**標準ライブラリだけ**で動く。

## 出力の読み方

出力は常に固定フォーマット（1 行目が結果、以降が現状。値が無い項目は `-`）:

```
SESSION_NAME_<結果> <理由>
  title : '<会話タイトル>'   (conversation title, set by /rename)
  name  : '<セッション名>'   (session name shown in /list-agents)
  source: 'user'            (must be 'user' to be visible to other sessions)
  file  : <セッション情報ファイル>
  memory: '<メモリ上の名前>'      (name the running process calls itself; changes only via /rename or restart)
```

`memory` は `--memory-name` で渡した値をそのまま表示する（書き込まない）。
`file` の name と違っていても正常: 他セッションからは `name` で届き、プロセス自身は `memory` を名乗る。

| 1 行目 | 意味 | 次にやること |
|---|---|---|
| `SESSION_NAME_SYNCED` | 同期できた | `/list-agents` で確認できる |
| `SESSION_NAME_UNCHANGED` | 既に一致している | なし |
| `SESSION_NAME_INFO` | 会話に名前が付いていない | 変えたいなら `/rename <名前>` してから再実行 |
| `SESSION_NAME_NOT_SYNCED` | できなかった | 1 行目の理由をそのまま伝える |
| `SESSION_NAME_UNKNOWN` | 対象を特定できなかった（transcript かセッション情報ファイルが見つからない・複数あって絞れない） | その旨を伝える |

**出力ブロックをそのまま（要約・言い換えせず）ユーザーに見せる。**
ツール結果はリモート（Remote Control）からは見えないため、再掲が必要。

## なぜ要るのか

Claude Code には名前が **3つ**あり、揃わない:

| 名前 | 実体 | 誰が見るか |
|---|---|---|
| 会話タイトル | transcript の `custom-title` 行（`/rename` が書く保存値） | VSCode のタブの元ネタ |
| **セッション名** | `~/.claude/sessions/<PID>.json` の `name` | **`/list-agents`・他セッションからの送信先** |
| 表示中のタブ文字列 | VSCode 拡張が会話タイトルを描画したもの（反映が遅れることがある） | 人の目だけ |

セッション名のファイルは **PID がファイル名**になっている。VSCode を開き直すと新しい PID の
ファイルが作られ、名前は cwd から自動生成（`nameSource: "derived"`）に戻る。
起動時に名前を渡す手段（`--name` / `CLAUDE_CODE_SESSION_NAME`）は **VSCode 拡張からは使えない**
（拡張の設定はワークスペース単位で、セッション単位の入口が無い）。
なおスクリプトはファイル名の PID ではなく、JSON 内の `sessionId` で対象ファイルを探す。

このスキルは会話タイトルを読んでセッション名に書き戻す。**打つ操作はゼロ。**

## 効く範囲と限界（実測）

- 書くのは `name` と **`nameSource: "user"`**（`/rename` が書く値と同じ）。
  Remote Control や VSCode 拡張のブリッジ経由の `/list-agents` は「人が選んだ名前」以外を
  伏せる（"not chosen by a human are withheld on this connection"）ので、`nameSource` が
  無いと **"(unnamed session)"** と出る。以前の版は `nameSource` を消して書いていたため
  これを踏んだ。この版は名前が一致していても `nameSource` が違えば書き直す
- **効くもの**: 他セッションの `ListAgents` / `SendMessage` の宛先、`claude agents --json`
- **効かないもの**: 動いているプロセス自身の `ListAgents` 1行目「This session is <名前>」。
  これはメモリ上の値で、ファイルを直しても追随しない。**ここまで揃えたいときだけ
  `/rename` を打つ**（人の操作）
- **本体との書き込み競合**（2026-09-23 実測）: VSCode を開き直して複数セッションが同時に
  resume すると、本体がセッション情報ファイルを開いている瞬間に当たる。Windows ではその間
  `os.replace` が PermissionError になり、旧版は即 `NOT_SYNCED cannot read/write` で諦めていた。
  現版は読み書きの失敗を最大 6 回（0.25 秒間隔）やり直し、`os.replace` が拒否されたときは
  同じファイルへの上書きに切り替える。`NOT_SYNCED` の 1 行目には最後のエラーが付く
- **SessionStart フックの `startup`**（新規セッション）では transcript も会話タイトルもまだ
  無いので、スクリプトは何も出力しない（以前は毎回 `SESSION_NAME_UNKNOWN` が会話に流れていた）。
  `resume` / `clear` / `compact` では従来どおり結果を出す

## SessionStart フックとしての登録と出力

`~/.claude/settings.json` に登録して、起動・resume・clear・compact のたびに自動で同期する
（手順と、結果を VSCode で表示させる設定はリポジトリの `docs/SETUP.md`）:

```json
"hooks": {
  "SessionStart": [
    {
      "matcher": "startup|resume|clear|compact",
      "hooks": [
        {
          "type": "command",
          "command": "python \"$HOME/.claude/skills/sync-vs-name/session_name_sync.py\"",
          "timeout": 10,
          "statusMessage": "セッション名を会話タイトルに同期"
        }
      ]
    }
  ]
}
```

- stdin の `hook_event_name` が `SessionStart` のときは **JSON で返す**:
  `systemMessage` に 1 行の日本語要約（例: `sync-vs-name (resume): 同期しました → 'ClaudeCodeTest'`）、
  `hookSpecificOutput.additionalContext` に上の固定フォーマット全文。手動実行はテキストのまま
- **VSCode 拡張は SessionStart の `systemMessage` を画面に出さない**（2026-09-23 実測）。
  `additionalContext` だけではモデルも動かないので、ユーザーが打つまで何も表示されない
- そこで `resume` / `clear` では**毎回** `hookSpecificOutput.initialUserMessage` に定型の依頼文を入れる。
  Claude はそれをユーザーが打ったメッセージとして処理し、ListAgents を呼んで `memory` 行を埋めた
  固定フォーマットのブロックを報告して止まる（1 往復ぶんのトークンを使う）。
  `initialUserMessage` は `startup` / `resume` / `clear` でだけ効き、`compact` では無視される
  （公式 docs では確認できていない。2026-09-23 に resume で実測、別プロジェクトの SessionStart フックでも使用中）。
  `startup` では出さない（開いただけでモデルを動かさない）
- 環境変数 `SYNC_VS_NAME_QUIET` が設定されていれば `initialUserMessage` を出さない
  （入れ子の `claude -p` でも SessionStart フックは走るため。呼ぶ側が設定する）
- 実行のたびに `~/.claude/logs/sync-vs-name.log` へ 1 行追記する
  （`時刻<TAB>source(startup/resume/clear/compact/manual)<TAB>session_id<TAB>結果の1行目`）。
  startup の無出力分もここには残る。256 KB を超えたら `sync-vs-name.log.1` に退避して
  新しく始める（1 世代だけ）
