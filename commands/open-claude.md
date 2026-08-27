---
description: 新しい Claude Code を「自分と同じ VS Code ウィンドウ」に開く（セッション再開・初期プロンプト指定も可）
argument-hint: "[sessionId | 初期プロンプト]  ※省略で新規"
allowed-tools: Bash, PowerShell
---

`~/.claude/scripts/open-claude.*` を呼ぶだけ。自分でコマンドを組み立て直さないこと。
**Windows は `open-claude.ps1` / macOS は `open-claude.sh`** で、引数の名前は揃えてある。

## 引数の解釈

`$ARGUMENTS` を見て振り分ける。

| `$ARGUMENTS` | 渡し方 |
|---|---|
| 空 | 引数なし（新規セッション） |
| UUID 形式 | `-Session <UUID>` |
| それ以外の文字列 | `-Prompt "<文字列>"` |

```powershell
# Windows
& "$env:USERPROFILE\.claude\scripts\open-claude.ps1"
```

```bash
# macOS
bash "$HOME/.claude/scripts/open-claude.sh"
```

宛先ウィンドウはスクリプトが自動判定する。フォルダ名やウィンドウタイトルを渡す必要は無い。

## 報告

スクリプトは `windowId` / 送信した URI / 「結果: 成功（終了コード 0）」または失敗を出力する。
**この出力で成否を判断してよい**。終了コード 0 かつ stderr 空なら URI は VS Code に届いている。
成功と出たら素直に成功と伝えること（ユーザーに目視確認を求める必要は無い）。
失敗と出たら stderr をそのまま示す。

## 仕組み（勝手に作り替えないための前提）

- 公式ドキュメントに記載があるのは `prompt` と `session` の 2 パラメータのみで、
  「VS Code が既に実行中なら**フォーカス中のウィンドウ**で開く」と明記されている。
- しかし VS Code 本体の `URLHandlerRouter#routeCall()` はクエリの `windowId=<数値>` を読み、
  `window:<id>` に一致する接続へルーティングする。**未文書だが Windows / macOS の両方で
  実測で動作を確認済み**（別ウィンドウをアクティブにした状態で自ウィンドウの `windowId` を
  送り、非アクティブな自ウィンドウにタブが開くことを確認。macOS 側の A/B は README 参照）。
  `windowId=_blank` は新規ウィンドウを強制する。
  **一致する接続が無いときは黙ってフォールバックする**（存在しない `windowId=999` を送っても
  アクティブなウィンドウに開くことを macOS で実測）。ここは OS 非依存の本体側コード。
- 自ウィンドウの ID は、拡張ホストの PID（`$env:CLAUDE_PID` / `$CLAUDE_PID` の親プロセス）を
  ログディレクトリ `window<N>` 配下の `exthost/exthost.log` にある
  `Extension host with pid <PID> started` と突き合わせて求める。
  ウィンドウタイトルやワークスペース名に依存しないので、同じフォルダを複数ウィンドウで
  開いていても一意に決まる。ログの置き場は
  Windows=`%APPDATA%\Code\logs`、macOS=`~/Library/Application Support/Code/logs`。
  **拡張ホストは再起動しうるので 1 行目だけでなくファイル全体を見る**（macOS の実測では、
  自分の拡張ホストの `started` 行がファイル先頭ではなく途中にあった）。
- フォアグラウンド化は**不要**。かつて必要だと考えたのは誤りで、実際は下記の環境変数の
  除去に失敗していただけだった。フォーカスを奪うコードは持たせないこと。

## 環境変数の罠（Windows。ここを間違えると無言で失敗する）

起動前に `ELECTRON_RUN_AS_NODE` と `VSCODE_*` を落とす必要がある。残っていると
`Code.exe` が素の Node や拡張ホスト用エントリポイントとして起動し、URI が処理されない。

**必ず `Remove-Item env:<名前>` を使うこと。**
`[Environment]::SetEnvironmentVariable(名前, $null)` は PowerShell の Env ドライブに
空の変数を残し（`Test-Path env:...` が True のまま）、`Start-Process` がそれを子へ渡す。
Electron は値ではなく**変数の存在**で Node モードを判定するため、空でも罠が発動する
（実測: 終了コード 9 / `bad option: --open-url`）。

**macOS はこの罠を踏まない。** `open(1)` は LaunchServices 経由で「起動中の VS Code」へ
URL を渡すだけで、こちらのシェルの環境変数は関係しない（`ELECTRON_RUN_AS_NODE` は
macOS の拡張ホスト配下でも同じように設定されているが、影響しない）。
そのぶん `Code.exe --open-url` のような**プロセスの終了コードによる検証はできない**ので、
`open -g` の終了コード＝「URL を VS Code に手渡せた」までしか保証しない。

## macOS 実装のメモ

- 送信は `open -g "vscode://..."`。`-g` はフォアグラウンド化しない指定。
- 初期プロンプトの percent-encode は**バイト単位**で行う（`LC_ALL=C`）。
  文字単位で回すと日本語が壊れる。加えて **bash 3.2（macOS 標準）の `printf "'<文字>"` は
  0x80 以上のバイトを符号拡張する**ので `& 0xFF` で潰す必要がある
  （潰さないと `%FFFFFFFFFFFFFFE3` のような出力になる。実測）。
- **日本語のすぐ前に来る変数展開は `${var}` と括る**。ロケール次第で bash 3.2 が
  後続の高位バイトを変数名の一部として読み、`unbound variable` で落ちる（実測）。

## 補足

- 拡張 ID は `Anthropic.claude-code`。外部から叩ける入口は URI ハンドラの `/open`（`session` /
  `prompt`）と `/install-plugin` の 2 パスだけ。他の `claude-vscode.*` はコマンドパレット専用で、
  VS Code CLI に任意のコマンドを実行するフラグは無い。
- `Code.exe` に `--version` / `--help` を付けても CLI としては動かず、**新しいウィンドウが開く**。
  動作確認のつもりで叩かないこと（CLI が要るときは `bin\code.cmd`、macOS は
  `/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code`）。
- `session` は VS Code で現在開いているワークスペースに属している必要がある（公式ドキュメント）。
  見つからない場合は新規会話になる。
- フォーカス中のウィンドウに開きたい場合は `-NoWindowId`。
