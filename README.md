# claude-utility

Claude Code の共通資産(コマンド・スクリプト・スキル)を複数 PC で共有するために履歴管理するリポジトリ。
使うときは、必要な機能だけを [docs/SETUP.md](docs/SETUP.md) の手順で `~/.claude` に取り込む。

## 構成

| パス | 内容 |
|---|---|
| `CLAUDE.md` | このリポジトリの作業ルール(公開・コミット前チェックルール)。取り込み対象ではない |
| `commands/` | スラッシュコマンド(例: `/open-claude`) |
| `scripts/` | コマンドから呼ばれる補助スクリプト(例: `open-claude.ps1` / `open-claude.sh`) |
| `skills/` | スキル(例: `grill-me`、`context-layering`、`context-declutter`、`sync-vs-name`) |
| `docs/` | 機能ごとの取り込み手順([SETUP.md](docs/SETUP.md)) |

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

### `sync-vs-name`(スキル + フック)

セッション名(`/list-agents` に出る名前)は、VSCode を開き直すと自動生成の名前に戻ってしまう。
このスキルは、セッション名を会話タイトル(VSCode のタブに出ている名前)に合わせ直す。

- [skills/sync-vs-name/SKILL.md](skills/sync-vs-name/SKILL.md)
- [docs/SETUP.md](docs/SETUP.md#sync-vs-name) — 再開時に自動で同期・報告させる設定(フック登録)

## 使い方

必要な機能だけを選んで `~/.claude` に取り込む。機能ごとに、置くファイル・追加の設定・確かめ方を
[docs/SETUP.md](docs/SETUP.md) にまとめてある。AI に「SETUP.md の ○○ を入れて」と頼めばよい。

### 更新するとき

`~/.claude` 側で直したら、[docs/SETUP.md](docs/SETUP.md) の対応表を見てリポジトリの同じパスへ書き戻し、コミットする。
ファイルを増やしたり減らしたりしたら、SETUP.md の対応表も直す。
