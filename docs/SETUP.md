# セットアップ（機能ごとの取り込み手順）

必要な機能だけを選んで取り込む。AI に「SETUP.md の ○○ を入れて」と頼めば、この手順どおりに入れられる。

各機能について、次の 3 点を書いてある:

1. **置くファイル** — リポジトリのパスと、置き先（`~/.claude/` の下）の対応
2. **追加の設定** — ファイルを置くだけでは足りないもの（フック登録など）
3. **確かめ方**

置き先に同名のファイルが既にあるときは、上書きする前に差分を確認する。

旧版を退避するときは、**`~/.claude/skills/` の外**（`~/.claude/backups/` など）に置く。
`~/.claude/skills/<名前>.bak-<日時>/` のように skills/ の下に置くと、退避したものまでスキルとして
読み込まれ、同じ説明のスキルが 2 件並ぶ（2026-09-23 に実際に踏んだ）。

## 一覧

| 機能 | 種類 | 対応 OS | 追加の設定 |
|---|---|---|---|
| [/open-claude](#open-claude) | コマンド + スクリプト | Windows / macOS | なし |
| [grill-me](#grill-me) | スキル | 共通 | なし |
| [context-layering](#context-layering) | スキル | 共通 | なし |
| [context-declutter](#context-declutter) | スキル | 共通 | なし |
| [sync-vs-name](#sync-vs-name) | スキル + フック | 共通（VSCode 拡張向け） | SessionStart フック（任意） |

---

## /open-claude

新しい Claude Code セッションを「自分と同じ VS Code ウィンドウ」に開く。

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `commands/open-claude.md` | `~/.claude/commands/open-claude.md` |
| `scripts/open-claude.ps1` | `~/.claude/scripts/open-claude.ps1`（Windows で使う） |
| `scripts/open-claude.sh` | `~/.claude/scripts/open-claude.sh`（macOS で使う） |

使わない OS 側のスクリプトは置かなくてよい。

### 追加の設定

なし。

### 確かめ方

新しいセッションで `/open-claude` を打ち、同じ VS Code ウィンドウに新しい Claude Code が開けばよい。

---

## grill-me

計画・設計について、共通認識に達するまで一問一答でヒアリングする。

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `skills/grill-me/SKILL.md` | `~/.claude/skills/grill-me/SKILL.md` |

### 追加の設定

なし。

### 確かめ方

新しいセッションで `/grill-me` が候補に出ればよい。

---

## context-layering

セッション開始時に毎回読み込まれるものを、情報を失わずに参照用ドキュメントへ再配置して軽くする。

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `skills/context-layering/SKILL.md` | `~/.claude/skills/context-layering/SKILL.md` |

### 追加の設定

なし。

### 確かめ方

新しいセッションで `/context-layering` が候補に出ればよい。

---

## context-declutter

AI が探索で読みにいく範囲から、読む必要のないものを外す。

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `skills/context-declutter/SKILL.md` | `~/.claude/skills/context-declutter/SKILL.md` |

### 追加の設定

なし。

### 確かめ方

新しいセッションで `/context-declutter` が候補に出ればよい。

---

## sync-vs-name

VSCode を開き直してセッションを再開すると、セッション名（`/list-agents` に出る名前）が
自動生成の名前に戻る。これを会話タイトルに合わせ直す。

- **スキルだけ**入れると、`/sync-vs-name` を手で打って合わせ直せる
- **フックも**入れると、起動・再開・`/clear`・compact のたびに自動で合わせ直す。さらに再開・`/clear` の直後は、
  フックが Claude に定型の依頼（`initialUserMessage`）を送り、Claude が自分の名前と同期結果を自動で報告する
  （VSCode 拡張はフックの結果を画面に出さず、ユーザーが打つ `/list-agents` にも自分の名前は出ないため）。
  報告は毎回 1 往復ぶんのトークンを使う

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `skills/sync-vs-name/SKILL.md` | `~/.claude/skills/sync-vs-name/SKILL.md` |
| `skills/sync-vs-name/session_name_sync.py` | `~/.claude/skills/sync-vs-name/session_name_sync.py` |

Python 3.8 以上が要る（標準ライブラリのみ）。

### 追加の設定（自動で合わせ直すとき）

`~/.claude/settings.json` の `hooks` に追加する（既存の `hooks` があれば、その中に `SessionStart` を足す）:

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

- フックのコマンドは bash（Windows では Git Bash、無ければ PowerShell）で実行される。`$HOME` はそのどれでも
  展開されるので、ユーザー名入りのパスを書かずに済む（cmd.exe では展開されないが、フックは cmd.exe では動かない）
- macOS で `python` コマンドが無い場合は `python3` にする
- `/hooks` から同じ内容を追加してもよい
- `claude -p` を入れ子で起動するスクリプトなどで報告させたくないときは、環境変数 `SYNC_VS_NAME_QUIET=1` を渡す

登録前に、コマンド単体で動くことを確かめておく（`session_id` が架空なので結果は `対象を特定できず` になるが、
JSON が返れば動いている）:

```bash
echo '{"session_id":"none","hook_event_name":"SessionStart","source":"resume"}' \
  | python "$HOME/.claude/skills/sync-vs-name/session_name_sync.py"
```

### 確かめ方

VSCode を開き直してセッションを再開する。何も打たなくても、定型の依頼メッセージ（ユーザーが打ったものとして表示される）に続いて、
Claude が `/sync-vs-name` と同じ形式のブロックを報告する（`memory` 行は Claude が ListAgents で取って埋める）:

```
SESSION_NAME_SYNCED session name updated to match the conversation title
  title : '<会話タイトル>'  (conversation title, set by /rename)
  name  : '<会話タイトル>'  (session name shown in /list-agents)
  source: 'user'  (must be 'user' to be visible to other sessions)
  file  : <セッション情報ファイル>
  memory: '<メモリ上の名前>'  (name the running process calls itself; changes only via /rename or restart)
```

`memory` が会話タイトルと違うのは正常（メモリ上の名前は `/rename` か再起動でしか変わらない）。
他のセッションからは `name` の名前で届く。フックの実行結果は `~/.claude/logs/sync-vs-name.log` にも 1 行ずつ残る。
新規に開いただけ（startup）では報告しない（まだ会話タイトルが無く、合わせ直すものが無いため）。
