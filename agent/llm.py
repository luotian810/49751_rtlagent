"""固定千问本地模型的 OpenAI 兼容接口客户端。

网络请求放在短命子进程中，父进程按整次调用的墙钟时间终止它。
这避免服务端持续发送空白保活时，socket 超时无法约束总耗时。
密钥仅从环境读取，不进入请求记录、命令行参数或异常正文。
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.json"
REQUIRED_MODEL = "Qwen3-14B-Q4_K_M"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


def load_generation() -> dict:
    """读取与官方基线相同的思考参数白名单，禁止借此覆盖采样/预算。"""
    try:
        generation = json.loads(MANIFEST.read_text(encoding="utf-8")).get("generation") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(generation, dict):
        return {}
    selected = {}
    kwargs = generation.get("chat_template_kwargs")
    if isinstance(kwargs, dict):
        kwargs = {key: value for key, value in kwargs.items()
                  if isinstance(key, str) and isinstance(value, (bool, int, float, str))}
        if kwargs:
            selected["chat_template_kwargs"] = kwargs
    effort = generation.get("reasoning_effort")
    if isinstance(effort, str) and effort:
        selected["reasoning_effort"] = effort
    return selected


class LLMError(RuntimeError):
    """可向用户展示的、已去除服务端原始内容的错误。"""


def validate_qwen_config(base_url: str, model: str) -> None:
    """在启动子进程或联网前拒绝模型替换及远端服务。"""
    if model != REQUIRED_MODEL:
        raise LLMError("本工程仅允许本地模型 " + REQUIRED_MODEL)
    try:
        if not isinstance(base_url, str) or any(ord(char) <= 32 or ord(char) == 127
                                                for char in base_url):
            raise ValueError("invalid URL characters")
        endpoint = urlsplit(base_url)
        host = endpoint.hostname
        local = host == "localhost"
        if not local and host:
            local = ipaddress.ip_address(host).is_loopback
        if (endpoint.scheme not in ("http", "https") or not local
                or endpoint.username is not None or endpoint.password is not None
                or "?" in base_url or "#" in base_url or endpoint.path != "/v1"
                or (endpoint.port is not None and endpoint.port == 0)):
            raise ValueError("not a local model endpoint")
    except (TypeError, ValueError) as exc:
        raise LLMError("LLM_BASE_URL 只允许无凭据、查询串和片段的本机 /v1 地址") from exc


def qwen_environment() -> tuple[str, str]:
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("LLM_MODEL", os.environ.get("MODEL_NAME", REQUIRED_MODEL))
    validate_qwen_config(base_url, model)
    # MODEL_NAME 同时供原样官方基线使用，不能被 LLM_MODEL 掩盖错误设置。
    if "MODEL_NAME" in os.environ and os.environ["MODEL_NAME"] != REQUIRED_MODEL:
        raise LLMError("MODEL_NAME 与 LLM_MODEL 必须同为 " + REQUIRED_MODEL)
    return base_url, model


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LLMError("本地模型请求不允许重定向")


@dataclass
class Reply:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    finish: str = ""


def redact(text: str) -> str:
    for name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "FPGACHINA_TOKEN"):
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


class LLM:
    def __init__(self) -> None:
        self.base_url, self.model = qwen_environment()
        self.max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "16384"))
        self.temperature = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.generation = load_generation()

    def describe(self) -> dict:
        # 不记录完整 URL：自定义地址可能含查询串凭据。
        endpoint = urlsplit(self.base_url)
        return {"model": self.model, "host": endpoint.hostname,
                "max_tokens": self.max_tokens, "temperature": self.temperature,
                "generation": self.generation,
                "thinking": "manifest_generation", "development_api": False}

    def chat(self, messages: list[dict], timeout_s: float, *, max_tokens: int | None = None) -> Reply:
        validate_qwen_config(self.base_url, self.model)
        if timeout_s <= 0:
            raise LLMError("模型调用没有剩余时间预算")
        limit = self.max_tokens if max_tokens is None else max_tokens
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise LLMError("max_tokens 必须为正整数")
        payload = {"model": self.model, "messages": messages,
                   "max_tokens": min(limit, self.max_tokens), "temperature": self.temperature,
                   "stream": False}
        payload.update(self.generation)
        try:
            run = subprocess.run(
                [sys.executable, "-m", "agent.llm"],
                input=json.dumps(payload, ensure_ascii=False),
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True, encoding="utf-8",
                env=dict(os.environ, PYTHONIOENCODING="utf-8",
                         RTL_LLM_REQUEST_TIMEOUT_S=str(timeout_s)),
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"模型调用超过 {timeout_s:.1f} 秒，已终止") from exc
        if run.returncode:
            # worker 从不输出原始网络异常；仍再做一次凭据替换。
            raise LLMError(redact(run.stderr.strip() or "模型调用子进程失败")[:500])
        try:
            result = json.loads(run.stdout)
            return Reply(**result)
        except (ValueError, TypeError) as exc:
            raise LLMError("模型客户端未返回有效结果") from exc


def _worker() -> int:
    try:
        base_url, model = qwen_environment()
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict) or payload.get("model") != model:
            raise LLMError("请求模型必须为 " + REQUIRED_MODEL)
        headers = {"Content-Type": "application/json"}
        secret = os.environ.get("LLM_API_KEY", "")
        if secret:
            headers["Authorization"] = "Bearer " + secret
        request = urllib.request.Request(
            base_url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"), headers=headers,
        )
        # 父进程施加完整墙钟期限；socket 等待同样受这次调用的剩余预算限制。
        # 本地推理不使用环境代理，也不跟随到其他地址的重定向。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=float(
                os.environ.get("RTL_LLM_REQUEST_TIMEOUT_S", "840"))) as response:
            body = json.loads(response.read())
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
        if not isinstance(content, str):
            raise ValueError("content must be string")
        usage = body.get("usage") or {}
        result = Reply(content, int(usage.get("prompt_tokens") or 0),
                       int(usage.get("completion_tokens") or 0), choice.get("finish_reason") or "")
        print(json.dumps(result.__dict__, ensure_ascii=False))
        return 0
    except LLMError as exc:
        print(str(exc), file=sys.stderr)
    except urllib.error.HTTPError as exc:
        hints = {401: "密钥无效", 402: "余额不足", 429: "服务限流", 404: "模型或地址不可用"}
        print(f"模型服务 HTTP {exc.code}: {hints.get(exc.code, '请求失败')}", file=sys.stderr)
    except Exception as exc:
        # 某些服务错误会回显 Authorization，故只保留异常类型。
        print(f"模型请求失败（{type(exc).__name__}），检查网络和配置", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(_worker())
