[CmdletBinding(DefaultParameterSetName = 'Agent')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Agent')][string]$TaskDir,
    [Parameter(Mandatory = $true, ParameterSetName = 'Agent')]
    [Parameter(ParameterSetName = 'Demo')][string]$OutDir,
    [Parameter(Mandatory = $true, ParameterSetName = 'Demo')][switch]$Demo,
    [ValidateSet('auto', 'modelsim', 'vivado', 'iverilog', 'none')][string]$Backend = 'auto',
    [ValidateRange(1, 10)][int]$MaxRounds = 3,
    [ValidateRange(1, 86400)][int]$Deadline = 900,
    [switch]$Synth,
    [string]$PythonPath = '',
    [string]$VivadoRoot = '',
    [string[]]$LicenseFiles = @()
)

$ErrorActionPreference = 'Stop'

# 仅配置这个 PowerShell 进程及其子进程；显式选择 Icarus 等后端时不加载 Vivado。
if ($Backend -in @('auto', 'vivado')) {
    $candidateVivadoRoot = $VivadoRoot
    if (-not $candidateVivadoRoot) { $candidateVivadoRoot = $env:XILINX_VIVADO }
    if (-not $candidateVivadoRoot) { $candidateVivadoRoot = 'D:\vivado\2025.2\Vivado' }
    $candidateVivadoBin = Join-Path $candidateVivadoRoot 'bin'
    $missingVivadoTools = @('vivado.bat', 'xvlog.bat', 'xelab.bat', 'xsim.bat') | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $candidateVivadoBin $_) -PathType Leaf)
    }
    if ($Backend -eq 'vivado' -or $VivadoRoot -or -not $missingVivadoTools) {
        $vivadoOptions = @{ VivadoRoot = $candidateVivadoRoot }
        if ($LicenseFiles.Count -gt 0) { $vivadoOptions.LicenseFiles = $LicenseFiles }
        & (Join-Path $PSScriptRoot 'scripts\use_vivado.ps1') @vivadoOptions
    }
}

function Resolve-TaskPython {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) { $candidates += $ExplicitPath }
    elseif ($env:PYTHON_EXE) { $candidates += $env:PYTHON_EXE }
    else {
        foreach ($commandName in @('python', 'python3', 'py')) {
            $command = Get-Command $commandName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($command) { $candidates += $command.Source }
        }
        if ($env:USERPROFILE) {
            $candidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        # Exclude Windows Store aliases that may open an installer instead of Python.
        if ($candidate -like '*\Microsoft\WindowsApps\*') { continue }
        try {
            $probe = & $candidate -c 'import sys; print("RTL_PYTHON_OK" if sys.version_info >= (3, 10) else "RTL_PYTHON_OLD")' 2>$null
            if ($LASTEXITCODE -eq 0 -and $probe -contains 'RTL_PYTHON_OK') { return $candidate }
        }
        catch { continue }
    }
    throw 'Python 3.10+ was not found. Pass -PythonPath C:\path\to\python.exe or set PYTHON_EXE.'
}

if ($Demo) {
    $pythonCommand = Resolve-TaskPython -ExplicitPath $PythonPath
    $demoArgs = @('scripts/run_demo.py', '--backend', $Backend)
    if ($OutDir) {
        $demoArgs += @('--output', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir))
    }
    if ($Synth) { $demoArgs += '--synth' }
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $pythonCommand @demoArgs
        $runExitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
    exit $runExitCode
}

# Resolve user paths before changing cwd so relative paths behave as expected.
$resolvedTask = (Resolve-Path -LiteralPath $TaskDir).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolvedTask 'prompt.txt') -PathType Leaf)) {
    throw "Task directory has no prompt.txt: $resolvedTask"
}
$resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir)
$pythonCommand = Resolve-TaskPython -ExplicitPath $PythonPath

Push-Location -LiteralPath $PSScriptRoot
try {
    $agentArgs = @('-m', 'agent.main', '--input', $resolvedTask, '--output', $resolvedOutput, '--backend', $Backend, '--max-rounds', $MaxRounds, '--deadline', $Deadline)
    if ($Synth) { $agentArgs += '--synth' }
    & $pythonCommand @agentArgs
    $runExitCode = $LASTEXITCODE
}
finally { Pop-Location }

exit $runExitCode
