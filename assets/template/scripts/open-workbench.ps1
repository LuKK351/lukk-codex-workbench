# Only this local reader is started; this script never collects or updates chats.
param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
try {
    $root = Split-Path -Parent $PSScriptRoot
    $configPath = Join-Path $root 'config\workbench.json'
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = Join-Path (Split-Path -Parent $config.pythonExecutable) 'pythonw.exe'
    $launcher = Join-Path $root 'scripts\launcher.py'
    if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $launcher)) {
        throw '工作台文件或原运行环境已找不到。请让 Codex 修复已有工作台的打开入口，不要重新初始化。'
    }
    $arguments = @($launcher, $root, '--gui')
    if ($Quiet) { $arguments += '--ensure-only' }
    & $python @arguments
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Codex 工作台暂时无法打开') | Out-Null
}
