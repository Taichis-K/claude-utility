<#
  自分（このシェルが属する VS Code ウィンドウ）に新しい Claude Code タブを開く。

  VS Code の vscode:// URI は既定では「フォーカス中のウィンドウ」に配られるが、
  本体の URLHandlerRouter がクエリの windowId=<数値> を読んで window:<id> の接続へ
  ルーティングする（未文書だが実測で確認済み）。これを使えばフォーカスを奪わずに
  自ウィンドウを指定できる。

  自ウィンドウの ID は、拡張ホストの PID（このシェルの祖先）が記録されている
  ログディレクトリ名 window<N> から求める。ウィンドウタイトルやワークスペース名に
  依存しないので、同じフォルダを複数ウィンドウで開いていても一意に決まる。
#>
[CmdletBinding()]
param(
  [string]$Session,        # 再開したいセッションの UUID
  [string]$Prompt,         # 初期プロンプト（URL エンコードは内部で行う）
  [switch]$NoWindowId      # windowId を付けない（＝フォーカス中のウィンドウに開く）
)

$ErrorActionPreference = 'Stop'

if (-not $env:VSCODE_CWD) { throw "VSCODE_CWD が無い。VS Code 拡張のセッションから実行すること。" }
$code = Join-Path $env:VSCODE_CWD 'Code.exe'
if (-not (Test-Path $code)) { throw "Code.exe が見つからない: $code" }

# --- 自ウィンドウの windowId を求める ---
function Get-MyWindowId {
  if (-not $env:CLAUDE_PID) { return $null }
  $extHost = (Get-CimInstance Win32_Process -Filter "ProcessId = $env:CLAUDE_PID" -EA SilentlyContinue).ParentProcessId
  if (-not $extHost) { return $null }

  # exthost.log に "Extension host with pid <PID> started" が記録される
  $pattern = "Extension host with pid $extHost started"
  $logRoot = Join-Path $env:APPDATA 'Code\logs'
  if (-not (Test-Path $logRoot)) { return $null }

  $sessions = Get-ChildItem $logRoot -Directory -EA SilentlyContinue | Sort-Object Name -Descending
  foreach ($s in $sessions) {
    foreach ($w in (Get-ChildItem $s.FullName -Directory -Filter 'window*' -EA SilentlyContinue)) {
      $f = Join-Path $w.FullName 'exthost\exthost.log'
      if (-not (Test-Path $f)) { continue }
      # 拡張ホストは再起動しうるので、1 行目だけでなくファイル全体を見る
      if (Select-String -Path $f -SimpleMatch -Pattern $pattern -Quiet -EA SilentlyContinue) {
        if ($w.Name -match '^window(\d+)$') { return [int]$Matches[1] }
      }
    }
  }
  return $null
}

$windowId = if ($NoWindowId) { $null } else { Get-MyWindowId }
if ($NoWindowId)            { Write-Host "windowId: 指定しない（フォーカス中のウィンドウに開く）" }
elseif ($null -eq $windowId) { Write-Host "警告: windowId を特定できなかった。フォーカス中のウィンドウに開く。" }
else                        { Write-Host "windowId: $windowId（自ウィンドウ）" }

# --- URI を組み立てる ---
$qs = @()
if ($windowId) { $qs += "windowId=$windowId" }
if ($Session)  { $qs += "session=$([uri]::EscapeDataString($Session))" }
if ($Prompt)   { $qs += "prompt=$([uri]::EscapeDataString($Prompt))" }
$uri = 'vscode://anthropic.claude-code/open'
if ($qs.Count) { $uri += '?' + ($qs -join '&') }

# --- 拡張ホストから継承した環境変数を落とす ---
# ELECTRON_RUN_AS_NODE が残ると Code.exe が素の Node として起動し bad option: --open-url になる。
# VSCODE_ESM_ENTRYPOINT などが残ると拡張ホスト用のエントリポイントで起動して URI が処理されない。
# 必ず Remove-Item を使うこと。[Environment]::SetEnvironmentVariable(名前, $null) では
# PowerShell の Env ドライブに空の変数が残り（Test-Path env:... が True のまま）、
# Start-Process がそれを子へ渡す。Electron は値ではなく変数の存在で判定するので罠が発動する。
@( 'ELECTRON_RUN_AS_NODE', 'VSCODE_IPC_HOOK', 'VSCODE_IPC_HOOK_CLI', 'VSCODE_ESM_ENTRYPOINT',
   'VSCODE_CODE_CACHE_PATH', 'VSCODE_NLS_CONFIG', 'VSCODE_CWD', 'VSCODE_PID',
   'VSCODE_CRASH_REPORTER_PROCESS_TYPE', 'VSCODE_HANDLES_UNCAUGHT_ERRORS',
   'VSCODE_L10N_BUNDLE_LOCATION' ) | ForEach-Object {
  Remove-Item -Path "Env:$_" -ErrorAction SilentlyContinue
}

# --- 送信し、終了コードと stderr で成否を確認する ---
$tmp = Join-Path $env:TEMP 'claude-open-claude'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$errFile = Join-Path $tmp 'stderr.txt'
$outFile = Join-Path $tmp 'stdout.txt'

$p = Start-Process $code -ArgumentList '--open-url','--',$uri -PassThru `
     -RedirectStandardError $errFile -RedirectStandardOutput $outFile
$exited = $p.WaitForExit(15000)

Write-Host "送信: $uri"
if (-not $exited) { Write-Host "結果: 15 秒経っても終了しなかった。異常。"; exit 1 }

$stderr = (Get-Content $errFile -Raw -EA SilentlyContinue)
if ($p.ExitCode -eq 0 -and [string]::IsNullOrWhiteSpace($stderr)) {
  Write-Host "結果: 成功（終了コード 0）"
} else {
  Write-Host "結果: 失敗 終了コード=$($p.ExitCode)"
  if ($stderr) { Write-Host "stderr: $stderr" }
  exit 1
}
