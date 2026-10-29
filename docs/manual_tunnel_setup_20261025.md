# 手动配置千问、投题服务与公网隧道

适用于当前 V7、固定 Qwen3-14B-Q4_K_M、AMD FPGA-CHINA 镜像。2026-10-25 23:46 已完成一次云端公网单题链路验证，见 [实测报告](fullchain_validation_20261025.md)。下面的手动步骤按实测中的去代理安装结论更新，不代表所有错误分支或长期运行已验证。

网页启动、Jupyter 终端配置、网页销毁都不需要 `rcc` 管理 CLI。此前管理 CLI 的 404 与下面 7860 端口的投题接口是两条不同的链路。

整套操作分为两个位置：第 1 步在云平台网页；第 2–6 步在云端 JupyterLab 的 **Terminal**；第 7–8 步在你自己电脑的 **PowerShell**；最后回云平台销毁。不要把 Linux 命令粘贴到 Windows PowerShell，也不要把它们当成 Notebook Python 单元格运行。

## 1. 网页启动实例

打开 <https://developer.amd.com.cn/radeon/profile>，确认登录的是原赛事账户。若已有实例，先核实其用途，不要重复启动。

使用之前的 **Readable RTL Agent Validation** 模板，核对为 FPGA-CHINA / fpgachina-rtlhls 镜像、1 GPU、持久化 `/workspace`。不要改用普通 AMD OneClick Base 镜像；它不保证包含本工程需要的 EDA 和 llama.cpp。

**模板的 Launch 会直接启动并开始计费。** 点击前设一个 40 分钟提醒，计划 45 分钟前在网页销毁，给最多 1 积分的这轮验证留出余量。提醒不是自动销毁；手动测试期间请保持在线。遇到卡住或预计超时，先保存日志并销毁，不要为排查而一直保留实例。

Ready 后打开 Notebook / JupyterLab。通过 **File → New → Terminal** 或 Launcher 中的 **Terminal** 打开终端。

## 2. 上传最新源码包并解压

在 JupyterLab 左侧文件栏进入 `/workspace`，点击上传按钮，选择本机文件：

`D:/fgpa/output/rtl-tunnel-validation-20261025/cloud-deployment.zip`

不要上传包含令牌的邮件。上传完成后回到 Terminal，执行：

```bash
cd /workspace
python3 - <<'PY'
from pathlib import Path
import hashlib, json, zipfile
archive = Path('/workspace/cloud-deployment.zip')
expected = '3366bd6497dd2d1ac624262af4b0402e8fd457775dc71b1633e9b2cd124576ae'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected, 'ZIP SHA 不匹配，停止'
root = Path('/workspace/rtl-manual-tunnel-20261025')
root.mkdir(exist_ok=False)
with zipfile.ZipFile(archive) as bundle:
    bundle.extractall(root)
for name, digest in json.loads((root/'input-sha256.json').read_text()).items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
manifest = json.loads((root/'project/manifest.json').read_text())
assert manifest['version'] == '2026.10.24-v7-qwen-only'
print('源码校验通过:', manifest['version'], manifest['model']['name'])
PY
```

应显示 `源码校验通过: 2026.10.24-v7-qwen-only Qwen3-14B-Q4_K_M`。

如果目录已存在，先停下，不要删除或覆盖历史目录。如果 SHA 不匹配，不继续执行包内代码。这份包不包含模型权重。

## 3. 输入令牌并保存固定运行配置

仍在云端 Terminal，先输入：

```bash
read -rsp '粘贴队伍投题令牌（不会显示），然后回车: ' FPGACHINA_TOKEN; printf '\n'; export FPGACHINA_TOKEN
```

出现提示后，粘贴邮件里的完整 `fc26_…` 令牌并回车。粘贴时看不到字符是正常的。

再复制下面整个代码块执行。它保留 `/workspace/env.sh` 中其他配置，替换本项目相关配置；不打印令牌：

```bash
python3 - <<'PY'
from pathlib import Path
import os, re, shlex
token = os.environ['FPGACHINA_TOKEN']
assert re.fullmatch(r'fc26_[a-f0-9]{32}', token), '令牌格式不正确，重新输入'
config = {
    'FPGACHINA_TOKEN': token,
    'INFERENCE_BACKEND': 'llamacpp',
    'LLAMA_SERVER': '/opt/llamacpp/llama-server',
    'MODEL': '/workspace/models/Qwen3-14B-Q4_K_M.gguf',
    'MODEL_NAME': 'Qwen3-14B-Q4_K_M',
    'LLM_MODEL': 'Qwen3-14B-Q4_K_M',
    'LLM_BASE_URL': 'http://127.0.0.1:8000/v1',
    'LLM_API_KEY': 'dummy',
    'PORT': '8000',
    'MAX_LEN': '32768',
    'HIP_VISIBLE_DEVICES': '0',
    'ROCBLAS_TENSILE_LIBPATH': '/opt/llamacpp/rocblas/library',
    'RTL_SIMULATOR': 'vivado',
    'XILINX_VIVADO': '/tools/Xilinx/2026.1/Vivado',
    'XILINXD_LICENSE_FILE': '2100@vivado-lic.fpgachina.svc.cluster.local',
    'FLEXLM_TIMEOUT': '300000000',
    'EDA_TMP': '/var/tmp/eda',
    'AGENT_TMP': '/var/tmp',
    'SELFTEST_TMP': '/var/tmp',
    'SERVE_LOG_DIR': '/workspace/rtl-manual-tunnel-20261025/logs',
    'NO_PROXY': '127.0.0.1,localhost',
    'no_proxy': '127.0.0.1,localhost',
}
path = Path('/workspace/env.sh')
lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
pattern = re.compile(r'^\s*(?:export\s+)?(' + '|'.join(map(re.escape, config)) + r')\s*=')
lines = [line for line in lines if not pattern.match(line)]
lines.extend('export ' + key + '=' + shlex.quote(value) for key, value in config.items())
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
path.chmod(0o600)
print('环境已保存；未显示令牌')
PY

source /workspace/env.sh
unset DEEPSEEK_API_KEY VRAM_GB
export PATH="$XILINX_VIVADO/bin:$PATH"
mkdir -p "$EDA_TMP" "$SERVE_LOG_DIR"
cd /workspace/rtl-manual-tunnel-20261025/project
```

后续新开 Terminal 时，重新执行 `source /workspace/env.sh`、`unset DEEPSEEK_API_KEY`、`export PATH="$XILINX_VIVADO/bin:$PATH"` 和 `cd`。不要把 env.sh 全文贴进聊天。

## 4. 检查权重与工具，再启动千问

先执行：

```bash
rocm-smi
command -v vivado
vivado -version
"$LLAMA_SERVER" --version
python3 - <<'PY'
from pathlib import Path
import hashlib, json, os
p = Path(os.environ['MODEL'])
assert p.is_file(), '持久盘中未找到既定权重，停止，不切换模型'
assert p.stat().st_size == 9001752960, '权重大小不一致'
with p.open('rb') as f:
    digest = hashlib.file_digest(f, 'sha256').hexdigest()
assert digest == '500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0', '权重 SHA 不一致'
manifest = json.loads(Path('manifest.json').read_text())
assert manifest['generation']['chat_template_kwargs']['enable_thinking'] is False
print('既定千问权重和 thinking=false 校验通过')
PY
```

应识别赛事 W7900 / gfx1100 GPU、Vivado 2026.1 和之前固定的 llama.cpp 构建（历史为 `f114f91`）。若工具缺失、版本或权重不一致，停在这里，不安装其他模型代替。

校验通过后启动：

```bash
bash serve/start.sh
```

看到 `model Qwen3-14B-Q4_K_M is ready` 才继续。此脚本会把模型进程放到独立会话，启动完成后返回终端提示符。

再验证实际服务进程的权重路径、32768 上下文、单槽及 thinking=false：

```bash
PYTHONPATH=.. python3 - <<'PY'
from cloud_support import qwen_guard
import json, os
print(json.dumps(qwen_guard(os.environ['MODEL']), indent=2))
PY
```

应包含 `model_id: Qwen3-14B-Q4_K_M`、`context: 32768`、`parallel_slots: 1`、`thinking: false`。如果报错，停止并查看 `$SERVE_LOG_DIR/llamacpp.log`，不要只凭模型列表名称继续。

## 5. 测量当前显存并后台启动投题服务

先保存新实例的实际显存快照，不使用旧报告中的数值：

```bash
rocm-smi --showmeminfo vram --json > "$SERVE_LOG_DIR/vram-start.json"
export VRAM_GB="$(python3 - <<'PY'
from pathlib import Path
import json, os
data = json.loads((Path(os.environ['SERVE_LOG_DIR'])/'vram-start.json').read_text())
used = [int(v['VRAM Total Used Memory (B)']) for v in data.values()
        if isinstance(v, dict) and 'VRAM Total Used Memory (B)' in v]
assert len(used) == 1, '应恰好有一张可见 GPU'
assert used[0] <= 32000000000, '显存超过 32 GB，停止'
print(used[0] / 1e9)
PY
)"
test -n "$VRAM_GB" || { echo '显存读取失败，停止'; return 1 2>/dev/null || exit 1; }
printf '当前显存 GB: %s\n' "$VRAM_GB"
```

这是启动后的快照，不是完整推理峰值证明。若采样失败或超过 32 GB，不启动投题服务。测试生成期间可在另一个 Terminal 用 `rocm-smi --showmeminfo vram` 检查占用。

然后执行：

```bash
setsid nohup python3 -m serve.serve_api --port 7860 \
  > "$SERVE_LOG_DIR/serve-api.log" 2>&1 < /dev/null &
echo "$!" > "$SERVE_LOG_DIR/serve-api.pid"
sleep 2
curl --noproxy '*' -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:7860/v1/health
```

**无令牌应返回 401。** 这是预期结果。

带令牌检查：

```bash
curl --noproxy '*' -sS \
  -H "Authorization: Bearer $FPGACHINA_TOKEN" \
  http://127.0.0.1:7860/v1/health | python3 -m json.tool
```

只有看到以下内容才继续：

```json
{
  "ready": true,
  "track": "rtl",
  "model": "Qwen3-14B-Q4_K_M"
}
```

实际响应还会有显存等字段。`ready=false` 时不暴露隧道；先按最后的排错表处理。此检查不验证 Vivado 许可证能否成功签出。

## 6. 安装官方隧道并暴露 7860

仍在云端 Terminal：

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY /var/run/secrets/frp-self-service/install

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY "$HOME/.local/bin/rc-tunnel" expose --port 7860

sleep 15
"$HOME/.local/bin/rc-tunnel" status
```

应看到 `Status: active` 和 `URL:`。复制实际 HTTPS URL，当前不报送。只暴露 **7860**，模型端口 8000 留在环回地址。

本次实际遇到安装器经代理返回 HTTP 403，去代理后安装成功，所以安装步骤也需要使用上面的 `env -u`。

## 7. 从自己的电脑验证公网健康检查

这一阶段离开云端 Terminal，在 Windows 开始菜单打开 **PowerShell**。依次执行：

```powershell
$base = (Read-Host '粘贴 rc-tunnel 的实际 HTTPS URL').TrimEnd('/')
$secure = Read-Host '输入队伍投题令牌' -AsSecureString
$token = [System.Net.NetworkCredential]::new('', $secure).Password
$headers = @{ Authorization = "Bearer $token" }

Invoke-RestMethod -Method Get -Uri "$base/v1/health" -Headers $headers -TimeoutSec 20
```

应看到 `ready=True`、`track=rtl`、`model=Qwen3-14B-Q4_K_M`。**这才证明从本机到云端投题服务的公网健康检查通了。** 不要在云实例里访问自己的公网 URL 来替代这一步。

还可以用下面命令检查公网无令牌访问；预期 401：

```powershell
curl.exe --noproxy "*" -s -o NUL -w "%{http_code}" "$base/v1/health"
```

## 8. 同一 PowerShell 再投一道简单题，验证结果回传

这是一次 agent 请求，不重跑旧版或官方基线。采用新的 nonce，约 240 秒预算。复制整个代码块：

```powershell
$body = @{
    task_id = 'manual-tunnel-popcount8'
    nonce = 'manual-' + [guid]::NewGuid().ToString('N')
    mode = 'agent'
    prompt = 'Implement a combinational Verilog module named TopModule with input [7:0] in and output [3:0] out. out must equal the number of 1 bits in in, from 0 to 8. There is no clock or reset.'
    interface = ''
    deadline_s = 240
} | ConvertTo-Json

$accepted = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$base/v1/solve" `
    -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 20
if ([int]$accepted.StatusCode -ne 202) { throw '接单未返回 202' }
$job = $accepted.Content | ConvertFrom-Json
if (-not $job.job_id -or $job.task_id -ne 'manual-tunnel-popcount8') { throw '接单编号或题号不符合契约' }
$job

$until = (Get-Date).AddSeconds(270)
do {
    Start-Sleep -Seconds 2
    $result = Invoke-RestMethod -Uri "$base/v1/jobs/$($job.job_id)" -Headers $headers -TimeoutSec 20
    Write-Host $result.status
} until ($result.status -eq 'done' -or (Get-Date) -gt $until)

$folder = Join-Path 'D:\fgpa\output\rtl-tunnel-validation-20261025\manual-external' $job.job_id
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $folder 'request.json'), $body, $utf8)
[System.IO.File]::WriteAllText((Join-Path $folder 'accepted.json'), $accepted.Content, $utf8)
[System.IO.File]::WriteAllText((Join-Path $folder 'result.json'), ($result | ConvertTo-Json -Depth 20), $utf8)
[System.IO.File]::WriteAllText((Join-Path $folder 'solution.v'), [string]$result.solution, $utf8)
[System.IO.File]::WriteAllText((Join-Path $folder 'trace.jsonl'), [string]$result.trace, $utf8)
if ($result.status -ne 'done') { throw "等待结果超时，最后状态已保存至 $folder；保留 job_id，不重投" }
if ([string]::IsNullOrWhiteSpace($result.solution)) { throw "协议已完成但返回空解，证据保存在 $folder" }
Write-Host "收到代码与 trace，已保存至 $folder"
```

预期 POST 返回 202 和 job_id，轮询由 queued/running 进入 done，并取得非空 solution。若报错，不把测试当成功，也不要反复点击或生成新 nonce 重投以覆盖这次失败。

到此是异步投题链路通过；代码功能正确仍需独立仿真。若已拿到结果，可以将上述目录中的 `result.json`、`solution.v`、`trace.jsonl` 交给我继续检查，**不要附带令牌**。

需要自己验证这道公开题的功能时，在同一个 PowerShell 执行：

```powershell
$icarus = 'D:\fgpa\readable-rtl-agent\.tools\iverilog\bin'
$task = 'D:\fgpa\readable-rtl-agent\vendor\rtlagent2026_selftest\tasks\ex01_popcount8'
& "$icarus\iverilog.exe" -g2012 -s tb -o "$folder\sim.vvp" "$folder\solution.v" "$task\ref.sv" "$task\tb.sv"
if ($LASTEXITCODE -ne 0) { throw '返回的 Verilog 编译失败，保留源码' }
& "$icarus\vvp.exe" "$folder\sim.vvp"
```

期望最后为 `Mismatches: 0 in 257 samples`。这只是该公开题的 Icarus 功能仿真，不代表 Vivado 综合通过或正式成绩。

## 9. 保存日志并在网页销毁本次实例

先在云端 Terminal 保存一份状态：

```bash
"$HOME/.local/bin/rc-tunnel" status > "$SERVE_LOG_DIR/tunnel-status.txt" 2>&1
tar -czf /workspace/rtl-manual-tunnel-20261025/manual-logs.tgz \
  -C /workspace/rtl-manual-tunnel-20261025 logs
```

从 JupyterLab 下载 `manual-logs.tgz`，不要打包 `/workspace/env.sh`。

回到云平台 Profile，点击 **Destroy Instance**，确认只销毁本次测试实例、保留持久化 `/workspace`。等到页面明确显示 **No active instance**，核对剩余积分。关闭网页、关闭 Terminal 或停止模型都不能代替销毁。

测试网址会随实例销毁而失效；当前不报送。下次实例重启后需要重新启动模型与投题服务、安装 rc-tunnel 并 expose，通常会得到新网址。服务中断约一分钟后隧道可能被收回，恢复服务后仍需再次 expose。

## 常见错误

| 现象 | 先检查什么 |
| --- | --- |
| 找不到模型文件 | 持久化 `/workspace` 是否挂载，是否仍有既定 GGUF；不替换其他模型 |
| `ready=false / model_unreachable` | 查看 `/workspace/rtl-manual-tunnel-20261025/logs/llamacpp.log`；检查模型是否成功启动 |
| `simulator_unavailable` | 是否使用 FPGA-CHINA 镜像；`command -v vivado`，以及 `XILINX_VIVADO` 和 PATH |
| 带正确令牌仍返回 401 | 当前 Terminal 是否重新 source；运行中的服务是否在令牌更新前启动。更新环境不会自动改变已运行进程 |
| 启动 7860 报地址已占用 | 用 `ss -ltnp 'sport = :7860'` 确认已有进程，先核实所属工程；不要反复后台启动多个副本 |
| 本地 health 正常，隧道不 active | 必须先启动投题服务，再 expose；使用给定的去代理命令 |
| active 但公网 404/502 | 检查本地服务仍存活、URL 是否最新；查看 `/root/.local/state/rc-tunnel/frpc.log`，恢复后重新 expose |
| Windows 不能访问公网 URL | 确认访问实际 HTTPS URL、网络可达；401 是鉴权问题，404/502 是路由或后端问题，不能混为模型错误 |
| POST 返回 202 但最终空解 | 接单链路通了，但解题失败；保存 result 和 trace，不当作功能通过 |

来源：项目固定 manifest、`serve/start.sh`、`serve/llamacpp.sh`、`serve/serve_api.py`、已核对的 RTL `docs/API_CONTRACT.md`，以及用户 2026-10-25 转发的隧道通知。本文不表示管理 CLI 已修复、云端链路已通过或 V7 取得正式成绩。
