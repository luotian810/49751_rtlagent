# 只配置当前 PowerShell 会话，不修改系统 PATH。
$toolBin = Join-Path (Split-Path $PSScriptRoot -Parent) '.tools\iverilog\bin'
if (-not (Test-Path -LiteralPath (Join-Path $toolBin 'iverilog.exe'))) {
    throw 'Portable Icarus was not found. See docs/iverilog_setup.md.'
}
$env:IVERILOG_BIN = $toolBin
$env:PATH = "$toolBin;$env:PATH"
$env:RTL_SIMULATOR = 'iverilog'
Write-Host 'Icarus Verilog is configured for this session.'
