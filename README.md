# claude-utility

Claude Code の共通資産(コマンド・スクリプト・スキル)を複数 PC で共有するために履歴管理するリポジトリ。
実体は `~/.claude` にあり、[sync.sh](sync.sh) でリポジトリと双方向に同期する
(CLAUDE.md だけはこのリポジトリの作業ルールで、同期対象外)。
同期スクリプトは Windows(Git Bash)と macOS の両方で動作する。

## 構成

| パス | 内容 |
|---|---|
| `CLAUDE.md` | このリポジトリの作業ルール(公開・コミット前チェックルール)。`~/.claude` とは同期しない |
| `commands/` | スラッシュコマンド(例: `/open-claude`) |
| `scripts/` | コマンドから呼ばれる補助スクリプト(例: `open-claude.ps1` / `open-claude.sh`) |
| `skills/` | スキル(例: `grill-me`、`context-layering`、`context-declutter`、`sync-vs-name`) |
| `sync.sh` | `~/.claude` との同期スクリプト(Windows は Git Bash で実行) |

認証情報・履歴・セッションなどのマシン固有データはリポジトリに含めない。

## 収録しているコマンド・スキル

### `/open-claude`(コマンド + スクリプト)

新しい Claude Code セッションを「自分と同じ VS Code ウィンドウ」に開く。
引数なしで新規セッション、UUID を渡すと既存セッションの再開、それ以外の文字列は初期プロンプトになる。
Windows / macOS の両方に対応し、引数名は揃えてある。仕組みとハマりどころはコマンド定義に書いてある。

- [commands/open-claude.md](commands/open-claude.md) — コマンド定義(仕組み・ハマりどころの解説を含む)
- [scripts/open-claude.ps1](scripts/open-claude.ps1) — Windows の実体
- [scripts/open-claude.sh](scripts/open-claude.sh) — macOS の実体

### `grill-me`(スキル)

計画・設計について、共通認識に達するまで一問一答で徹底的にヒアリングするスキル。
質問は一度に一つ、各問に推奨回答を添え、コードを読めば分かることは質問せず自分で調べる、
というルールで設計ツリーを上流(前提・スコープ)から下流(実装選択)へたどる。

- [skills/grill-me/SKILL.md](skills/grill-me/SKILL.md)

### `context-layering`(スキル)

セッション開始時に毎回読み込まれるものを、プロジェクトの情報を失わずに参照用ドキュメントへ再配置して軽くする。

- [skills/context-layering/SKILL.md](skills/context-layering/SKILL.md)

### `context-declutter`(スキル)

AI が探索で読みにいく範囲から読む必要のないものを外し、読まないフォルダを決めてプロジェクトを軽くする。

- [skills/context-declutter/SKILL.md](skills/context-declutter/SKILL.md)

### `sync-vs-name`(スキル)

セッション名(`/list-agents` に出る名前)は、VSCode を開き直すと自動生成の名前に戻ってしまう。
このスキルは、セッション名を会話タイトル(VSCode のタブに出ている名前)に合わせ直す。

- [skills/sync-vs-name/SKILL.md](skills/sync-vs-name/SKILL.md)

## 使い方

Windows では Git Bash、macOS ではターミナルから実行する。

```bash
./sync.sh diff        # ローカル(~/.claude)との差分を表示(変更なし)
./sync.sh from-local  # ~/.claude → リポジトリへ収集(git diff で確認してコミット)
./sync.sh to-local    # リポジトリ → ~/.claude へ反映(事前に ~/.claude/backups へ退避)
```

### ローカルの変更をコミットする

```bash
./sync.sh from-local
git diff              # 内容を確認
git add -A && git commit -m "変更内容" && git push
```

### 別の PC でセットアップする

```bash
git clone https://github.com/Taichis-K/claude-utility.git
cd claude-utility
./sync.sh diff        # 上書きされる内容を確認
./sync.sh to-local
```

`to-local` は反映前に既存ファイル一式を `~/.claude/backups/sync-<日時>/` へ退避するので、
誤って上書きしても戻せる。

## 対象を増やすとき

`sync.sh` 冒頭の `DIRS` に追加する。
