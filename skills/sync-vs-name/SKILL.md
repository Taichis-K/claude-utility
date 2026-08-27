---
name: sync-vs-name
description: 会話タイトル（VSCode のタブに出る名前）をセッション名（/list-agents に出る名前）に同期する。VSCode を開き直したり /clear した後にセッション名が自動生成に戻ったとき、名前を打ち直さずに戻す。
allowed-tools: Bash
---

# 会話タイトルをセッション名に同期する

同じディレクトリの `session_name_sync.py` を呼ぶだけ。**自分で名前を組み立てたり、
`~/.claude/sessions/*.json` を直接編集したりしないこと。**

```bash
s=.claude/skills/sync-vs-name/session_name_sync.py
[ -f "$s" ] || s=~/.claude/skills/sync-vs-name/session_name_sync.py
python "$s" </dev/null 2>/dev/null || python3 "$s" </dev/null
```

プロジェクト(`.claude/skills/`)にあればそちらを、無ければユーザー(`~/.claude/skills/`)のものを使う。

`</dev/null` を必ず付ける（スクリプト自体は TTY からは読まないが、非 TTY で stdin が
開いたままの実行環境では読みに行って固まるため）。**標準ライブラリだけ**で動く。

## 出力の読み方

| 出力 | 意味 | 次にやること |
|---|---|---|
| （何も出ない） | 同期の必要が無いか、対象を特定できなかった（既に一致 ／ 会話に名前が付いていない ／ セッション情報ファイルが見つからない・複数あって絞れない） | 名前を付けていなければ `/rename <名前>` してから再実行。付けているのに何も出ないなら、特定できなかった可能性をユーザーに伝える |
| `SESSION_NAME_SYNCED …` | 同期できた | `/list-agents` で確認できる |
| `SESSION_NAME_NOT_SYNCED …` | できなかった | 出力の理由をそのままユーザーに伝える |

結果はユーザーに**1行で**報告する。同期できたなら新しいセッション名を含める。

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
