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
