"""比赛异步 HTTP 入口：接单后立即返回编号，后台串行解题，轮询取回产物。

正式启动：./serve/run_api.sh start；由后台监督进程启动本模块。
仅依赖 Python 标准库；服务按比赛契约固定监听 127.0.0.1。
"""

from __future__ import annotations

import argparse
import ctypes
import hmac
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
MAX_BODY_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_DEADLINE_S = 3600


def validate_request(data: Any) -> dict[str, Any]:
    """只接收契约规定的类型，阻止拼错 mode 后悄悄进入另一路径。"""
    if not isinstance(data, dict):
        raise ValueError("request must be a JSON object")
    result = dict(data)
    for field, default in (("task_id", None), ("prompt", None),
                           ("nonce", ""), ("interface", "")):
        value = result.get(field, default)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        if field in ("task_id", "prompt") and not value.strip():
            raise ValueError(f"{field} must not be empty")
        result[field] = value
    result.setdefault("mode", "agent")
    if result["mode"] not in ("agent", "baseline"):
        raise ValueError("mode must be agent or baseline")
    deadline = result.setdefault("deadline_s", 900)
    if type(deadline) is not int or not 1 <= deadline <= MAX_DEADLINE_S:
        raise ValueError(f"deadline_s must be an integer from 1 to {MAX_DEADLINE_S}")
    return result


def _redact(text: str) -> str:
    """模型/工具错误可能含认证信息；返回日志前去除当前配置的密钥。"""
    for name in ("FPGACHINA_TOKEN", "LLM_API_KEY", "DEEPSEEK_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _vram_gb(device_root: Path = Path("/dev/dri"),
             sysfs_root: Path = Path("/sys/class/drm")) -> float | None:
    """实时读取实例获配的唯一 AMD GPU；不读取宿主机其他卡或旧环境采样。"""
    try:
        # sysfs can expose every host GPU even when the container only receives
        # one render node. Restrict discovery to /dev/dri assigned to us.
        devices = {(sysfs_root / node.name / "device").resolve()
                   for node in device_root.glob("renderD[0-9]*")
                   if node.name[7:].isdigit()}
        if len(devices) != 1:
            return None  # Ambiguous allocation is not a measured single-card value.
        device = devices.pop()
        if (device / "vendor").read_text().strip().lower() != "0x1002":
            return None
        used = int((device / "mem_info_vram_used").read_text())
        total = int((device / "mem_info_vram_total").read_text())
        return used / 1e9 if 0 <= used <= total and total > 0 else None
    except (OSError, ValueError, RuntimeError):
        return None


def _simulator_available() -> bool:
    # 与 CLI 共用探测逻辑，避免服务与实际执行认出不同的工具安装。
    try:
        from agent.verification import Toolchain
        return bool(Toolchain(os.environ.get("RTL_SIMULATOR", "vivado")).describe()["available"])
    except (ImportError, ValueError, KeyError):
        return False


def health() -> dict[str, Any]:
    """真正查询模型端点；HTTP 服务活着不等于模型和 EDA 已经就绪。"""
    model = os.environ.get("MODEL_NAME") or os.environ.get("LLM_MODEL") or "unknown"
    vram = _vram_gb()
    result: dict[str, Any] = {
        "ready": False, "track": "rtl", "model": model,
        "vram_gb": vram, "status": "model_not_configured",
        "vram_measurement": "live_assigned_gpu_sysfs" if vram is not None else "unavailable",
        "simulator_license": "not_checked",
    }
    if model == "unknown":
        return result
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.environ.get("LLM_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        request = urllib.request.Request(base_url + "/models", headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
        if len(raw) > MAX_BODY_BYTES:
            raise ValueError("oversized model response")
        models = json.loads(raw).get("data", [])
        found = any(isinstance(item, dict) and item.get("id") == model for item in models)
    except (OSError, ValueError, TypeError, AttributeError):
        result["status"] = "model_unreachable"
        return result
    if not found:
        result["status"] = "model_not_available"
    elif not (ROOT / "agent" / "main.py").is_file():
        result["status"] = "agent_unavailable"
    elif not _simulator_available():
        result["status"] = "simulator_unavailable"
    else:
        result.update(ready=True, status="ready")
    return result


def _stop_process_tree(process: subprocess.Popen, grace_s: float = 5) -> None:
    """超时后清理 Python 及其 EDA 子进程，避免下一道题继续占用资源。"""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        deadline = time.monotonic() + grace_s
        try:
            os.killpg(process.pid, signal.SIGTERM)
            # 单题脚本、模型请求和 EDA 同组；智能体还会在 finally 中清理工具。
            process.wait(timeout=grace_s)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            pass
        # shell 往往先退出，不能因此立即强杀仍在清理临时文件的智能体。
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        # 即使 Python 已退出，同组 EDA 进程也可能尚未结束。
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def _become_subreaper() -> bool:
    """Linux 云实例的 PID 1 不回收孤儿；由本服务接管自己任务的后代。"""
    if not sys.platform.startswith("linux"):
        return False
    try:
        return ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    except (OSError, AttributeError):
        return False


def _cleanup_group(pgid: int) -> None:
    """正常退出也清扫残留，只回收这个 job 的组，不抢其他子进程的退出状态。"""
    if os.name == "nt":
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    until = time.monotonic() + 2
    while True:
        try:
            child, _ = os.waitpid(-pgid, os.WNOHANG)
        except ChildProcessError:
            return
        if child == 0:
            if time.monotonic() >= until:
                return
            time.sleep(0.05)


def _read_output(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_OUTPUT_BYTES + 1)
        # 不返回被截断的 Verilog 或 JSONL，以免把损坏产物伪装成完整结果。
        return data.decode("utf-8") if len(data) <= MAX_OUTPUT_BYTES else ""
    except (OSError, UnicodeDecodeError):
        return ""


def solve(data: dict[str, Any], submitted: float | None = None,
          cancel_event: threading.Event | None = None) -> dict[str, Any]:
    """无论子进程成功、报错还是超时，都返回它已经写出的 solution/trace。"""
    started = time.monotonic() if submitted is None else submitted
    solution = trace = ""
    event = None
    remaining = data["deadline_s"] - (time.monotonic() - started)
    if remaining <= 0:
        return {"task_id": data["task_id"], "solution": "",
                "trace": json.dumps({"tool": "service", "event": "queue_deadline_expired",
                                     "ts": time.time()}) + "\n",
                "elapsed_s": round(time.monotonic() - started, 3)}
    scratch = os.environ.get("AGENT_TMP") or ("/var/tmp" if os.name != "nt" else None)
    eda_scratch = os.environ.get("EDA_TMP") or scratch
    try:
        for base in (scratch, eda_scratch):
            if base:
                Path(base).mkdir(parents=True, exist_ok=True)
        # 服务持有每题 EDA 根目录；子进程被强杀也由服务最终清理。
        with tempfile.TemporaryDirectory(prefix="rtl-request-", dir=scratch) as directory, \
                tempfile.TemporaryDirectory(prefix="rtl-eda-job-", dir=eda_scratch) as eda_directory:
            work = Path(directory)
            source, output = work / "in", work / "out"
            source.mkdir()
            output.mkdir()
            (source / "prompt.txt").write_text(data["prompt"], encoding="utf-8")
            if data["interface"]:
                (source / "interface.txt").write_text(data["interface"], encoding="utf-8")

            # 子进程与外层等待共用一个预算，另给子进程启动/返回留少量余量。
            # 短请求也保留小数秒，不能把不足 1 秒的预算向上扩成 1 秒。
            reserve = min(10.0, max(0.5, data["deadline_s"] * 0.1))
            timeout = data["deadline_s"] - reserve - (time.monotonic() - started)
            launch_margin = min(0.5, max(0.0, timeout) * 0.1)
            child_deadline = str(max(0.0, timeout - launch_margin))
            environment = dict(os.environ)
            environment.setdefault("LLM_BASE_URL", DEFAULT_BASE_URL)
            if not environment.get("MODEL_NAME") and environment.get("LLM_MODEL"):
                environment["MODEL_NAME"] = environment["LLM_MODEL"]
            environment["AGENT_DEADLINE_S"] = child_deadline
            environment["PYTHONUTF8"] = "1"
            environment["EDA_TMP"] = eda_directory
            # Linux 与容器退路共用单题入口；Windows 保留不依赖 Bash 的开发入口。
            if os.name != "nt":
                script = "run_baseline.sh" if data["mode"] == "baseline" else "run.sh"
                environment["PYTHON_EXE"] = sys.executable
                command = ["bash", str(ROOT / script), str(source), str(output)]
            elif data["mode"] == "baseline":
                command = [sys.executable, str(ROOT / "baseline.py"),
                           str(source), str(output), "rtl"]
            else:
                command = [sys.executable, "-m", "agent.main", "--input", str(source),
                           "--output", str(output), "--deadline", child_deadline,
                           "--max-rounds", environment.get("AGENT_MAX_ROUNDS", "3"),
                           "--backend", environment.get("RTL_SIMULATOR", "vivado")]
            options: dict[str, Any] = {"cwd": ROOT, "env": environment,
                                       "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                options["start_new_session"] = True
            try:
                if timeout <= 0:
                    event = {"event": "queue_deadline_expired"}
                    raise TimeoutError("no time left to launch")
                process = subprocess.Popen(command, **options)
                try:
                    if cancel_event is None:
                        return_code = process.wait(timeout=timeout)
                    else:
                        stop_at = time.monotonic() + timeout
                        while True:
                            if cancel_event.is_set():
                                _stop_process_tree(process, grace_s=min(5, reserve / 2))
                                event = {"event": "service_cancelled"}
                                return_code = 0
                                break
                            left = stop_at - time.monotonic()
                            if left <= 0:
                                raise subprocess.TimeoutExpired(command, timeout)
                            try:
                                return_code = process.wait(timeout=min(0.2, left))
                                break
                            except subprocess.TimeoutExpired:
                                continue
                    if return_code:
                        event = {"event": "service_child_exit", "rc": return_code}
                except subprocess.TimeoutExpired:
                    _stop_process_tree(process, grace_s=min(5, reserve / 2))
                    event = {"event": "service_timeout"}
                finally:
                    _cleanup_group(process.pid)
            except TimeoutError:
                pass
            except OSError:
                event = {"event": "service_launch_failed"}
            finally:
                solution = _read_output(output / "solution.v")
                trace = _read_output(output / "trace.jsonl")
    except OSError:
        event = {"event": "service_workspace_failed"}
    if event is not None:
        event["tool"] = "service"
        event["ts"] = time.time()
        trace = trace.rstrip("\n") + ("\n" if trace else "") + json.dumps(event) + "\n"
    return {"task_id": data["task_id"], "solution": _redact(solution),
            "trace": _redact(trace), "elapsed_s": round(time.monotonic() - started, 3)}


class JobQueue:
    """一个工作线程按提交顺序解题；nonce 在服务生命周期内保持幂等。"""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.by_nonce: dict[str, str] = {}
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.pending: queue.Queue = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    @staticmethod
    def _public(job: dict[str, Any]) -> dict[str, Any]:
        result = {key: job[key] for key in ("job_id", "task_id", "status")}
        if job["status"] == "done":
            result.update({key: job[key] for key in ("solution", "trace", "elapsed_s")})
        return result

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            nonce = request["nonce"]
            if nonce and nonce in self.by_nonce:
                return self._public(self.jobs[self.by_nonce[nonce]])
            job_id = uuid.uuid4().hex
            job = {"job_id": job_id, "task_id": request["task_id"], "status": "queued"}
            self.jobs[job_id] = job
            if nonce:
                self.by_nonce[nonce] = job_id
            # 在解题线程开始前留住 queued 响应；计时从接单开始，包含排队。
            result = self._public(job)
            self.pending.put((job_id, dict(request), time.monotonic()))
            return result

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return self._public(job) if job else None

    def _work(self) -> None:
        while True:
            item = self.pending.get()
            try:
                if item is None or self.cancel_event.is_set():
                    return
                job_id, request, submitted = item
                with self.lock:
                    self.jobs[job_id]["status"] = "running"
                try:
                    result = solve(request, submitted=submitted, cancel_event=self.cancel_event)
                except Exception:
                    # 不让一题异常杀死工作线程，或让该题永久停在 running。
                    result = {"solution": "", "trace": json.dumps({"tool": "service",
                              "event": "service_worker_failed", "ts": time.time()}) + "\n",
                              "elapsed_s": round(time.monotonic() - submitted, 3)}
                with self.lock:
                    self.jobs[job_id].update(status="done", **{
                        key: result[key] for key in ("solution", "trace", "elapsed_s")})
            finally:
                self.pending.task_done()

    def close(self) -> None:
        self.cancel_event.set()
        self.pending.put(None)
        self.worker.join(timeout=10)


class ServiceServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], handler: type) -> None:
        super().__init__(address, handler)
        self.jobs = JobQueue()

    def server_close(self) -> None:
        super().server_close()
        self.jobs.close()


class Handler(BaseHTTPRequestHandler):
    """请求正文有大小/读取时限；解题串行，健康检查仍可并发访问。"""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format: str, *args: Any) -> None:
        # 不将请求 URL、认证头或模型输出写进终端日志。
        return

    def _send(self, status: int, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        self.close_connection = True

    def _authorized(self) -> bool:
        token = os.environ.get("FPGACHINA_TOKEN", "")
        if not token:
            self._send(503, {"error": "FPGACHINA_TOKEN is not configured"})
            return False
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + token).encode("utf-8")):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        if not self._authorized():
            return
        if self.path == "/v1/health":
            self._send(200, health())
            return
        if self.path.startswith("/v1/jobs/"):
            result = self.server.jobs.get(self.path[len("/v1/jobs/"):])
            if result is not None:
                self._send(200, result)
                return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorized():
            return
        if self.path != "/v1/solve":
            self._send(404, {"error": "not found"})
            return
        if self.headers.get_content_type() != "application/json":
            self._send(415, {"error": "Content-Type must be application/json"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._send(400, {"error": "chunked bodies are not supported"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 0 <= length <= MAX_BODY_BYTES:
                self._send(413, {"error": "invalid or oversized request body"})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete request body")
            request = validate_request(json.loads(raw))
        except (ValueError, UnicodeError):
            self._send(400, {"error": "invalid solve request"})
            return
        except TimeoutError:
            self._send(408, {"error": "request body timeout"})
            return
        self._send(202, self.server.jobs.submit(request))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be from 1 to 65535")
    if not os.environ.get("FPGACHINA_TOKEN"):
        parser.error("set FPGACHINA_TOKEN before starting the service")
    _become_subreaper()
    server = ServiceServer(("127.0.0.1", args.port), Handler)
    def stop_service(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_service)
    print(f"RTL service listening at http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
