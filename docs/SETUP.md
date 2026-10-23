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
| [sync-vs-name](#sync-vs-name) | スキル | 共通（VSCode 拡張向け） | なし |

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

セッション名（`/list-agents` に出る名前）が自動生成の名前に戻ってしまったとき
（2.1.308 以前は VSCode を開き直すたびに戻っていた）、`/sync-vs-name` で会話タイトルに合わせ直す。

Claude Code 2.1.309 以降は、本体が開き直し後や `/clear` 後も `/rename` した名前を自動で戻すので、
普段は使わなくてよい（2026-10-23 確認）。名前がずれたときに手で合わせ直す用に置いておく。
以前は SessionStart フックで自動実行していたが、今は不要（古い版向けの登録方法は `SKILL.md` に残してある）。

### 置くファイル

| リポジトリ | 置き先 |
|---|---|
| `skills/sync-vs-name/SKILL.md` | `~/.claude/skills/sync-vs-name/SKILL.md` |
| `skills/sync-vs-name/session_name_sync.py` | `~/.claude/skills/sync-vs-name/session_name_sync.py` |

Python 3.8 以上が要る（標準ライブラリのみ）。

### 追加の設定

なし。

### 確かめ方

`/rename` 済みのセッションで `/sync-vs-name` を打ち、次のような固定形式のブロックが返ればよい
（1 行目は `SESSION_NAME_SYNCED` か `SESSION_NAME_UNCHANGED`。2.1.309 以降は本体が `nameSource: "auto"` で
書くため、名前が一致していても `"user"` に書き直して `SYNCED` になることがある）:

```
SESSION_NAME_SYNCED session name updated to match the conversation title
  title : '<会話タイトル>'  (conversation title, set by /rename)
  name  : '<会話タイトル>'  (session name shown in /list-agents)
  ...
```
