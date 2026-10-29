[CmdletBinding()]
param(
    [string]$VivadoRoot = '',
    [string[]]$LicenseFiles = @()
)

$ErrorActionPreference = 'Stop'

# 安装根可以显式传入，也可复用当前会话的设置；不搜索或修改注册表。
if (-not $VivadoRoot) { $VivadoRoot = $env:XILINX_VIVADO }
if (-not $VivadoRoot) { $VivadoRoot = 'D:\vivado\2025.2\Vivado' }
if (-not (Test-Path -LiteralPath $VivadoRoot -PathType Container)) {
    throw "Vivado installation was not found: $VivadoRoot"
}
$resolvedVivadoRoot = (Resolve-Path -LiteralPath $VivadoRoot).Path
$vivadoBin = Join-Path $resolvedVivadoRoot 'bin'
foreach ($toolName in @('vivado.bat', 'xvlog.bat', 'xelab.bat', 'xsim.bat')) {
    if (-not (Test-Path -LiteralPath (Join-Path $vivadoBin $toolName) -PathType Leaf)) {
        throw "Vivado tool was not found: $toolName in $vivadoBin"
    }
}

# 2025.2 的共享 Tcl 仓库位于 <版本>/data，而非用户的 Tcl app 缓存。
$versionRoot = Split-Path $resolvedVivadoRoot -Parent
$installationRoot = Split-Path $versionRoot -Parent
$tclRepository = Join-Path $versionRoot 'data\XilinxTclStore'
if (-not (Test-Path -LiteralPath $tclRepository -PathType Container)) {
    throw "The installed Xilinx Tcl repository was not found: $tclRepository"
}

# 只检查许可证文件是否存在并传递路径；不读取、复制或显示其内容。
if ($LicenseFiles.Count -eq 0) {
    $LicenseFiles = @(
        (Join-Path $installationRoot 'License.lic'),
        (Join-Path $installationRoot 'vivado_lic2037.lic')
    )
}
$resolvedLicenseFiles = foreach ($licensePath in $LicenseFiles) {
    if (-not (Test-Path -LiteralPath $licensePath -PathType Leaf)) {
        throw "License file was not found: $licensePath. Pass -LicenseFiles to select existing files."
    }
    (Resolve-Path -LiteralPath $licensePath).Path
}

# 全部路径校验后再写进程环境，避免配置失败时留下半套设置。
$env:XILINX_VIVADO = $resolvedVivadoRoot
$env:XILINX_ROOT = $installationRoot
$env:XILINXD_LICENSE_FILE = $resolvedLicenseFiles -join ';'
$env:XILINX_TCLAPP_REPO = $tclRepository
$env:XILINX_LOCAL_USER_DATA = 'NO'
$env:RTL_SIMULATOR = 'vivado'
# Winsock 的进程级主机名覆盖，使 Vivado 的 .Xil 会话路径保持 ASCII。
# 这是本机 UTF-8/CP936 路径故障的兼容设置；不改系统电脑名或授权信息。
if ([Environment]::MachineName -match '[^\x00-\x7F]' -and -not $env:_CLUSTER_NETWORK_NAME_) {
    $env:_CLUSTER_NETWORK_NAME_ = 'RTLLOCAL'
}
if (($env:PATH -split ';') -notcontains $vivadoBin) {
    $env:PATH = "$vivadoBin;$env:PATH"
}

Write-Host "Vivado configured for this PowerShell process: $resolvedVivadoRoot"
Write-Host 'Tool discovery is ready; simulation and synthesis must still verify runtime availability.'
