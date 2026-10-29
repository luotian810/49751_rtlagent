"""模型锁定回归：全部使用 mock，不访问真实模型或外部网络。"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

from agent.llm import (DEFAULT_BASE_URL, LLM, LLMError, REQUIRED_MODEL,
                       _NoRedirect, _worker)


class QwenOnlyTests(unittest.TestCase):
    def worker(self, payload, environment=None):
        output, errors = io.StringIO(), io.StringIO()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "choices": [{"message": {"content": "local fixture"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict(os.environ, environment or {}, clear=True), \
                patch("agent.llm.sys.stdin", io.StringIO(json.dumps(payload))), \
                patch("agent.llm.urllib.request.build_opener", return_value=opener) as build, \
                patch("agent.llm.urllib.request.urlopen") as urlopen, \
                redirect_stderr(errors), redirect_stdout(output):
            status = _worker()
        return status, output.getvalue(), errors.getvalue(), build, opener, urlopen

    def test_defaults_select_only_the_declared_local_qwen(self):
        with patch.dict(os.environ, {}, clear=True):
            model = LLM()
        self.assertEqual(model.base_url, DEFAULT_BASE_URL)
        self.assertEqual(model.model, REQUIRED_MODEL)
        self.assertFalse(model.describe()["development_api"])

    def test_parent_refuses_wrong_provider_or_model_before_subprocess_or_network(self):
        for environment in (
                {"LLM_BASE_URL": "https://api.deepseek.com/v1"},
                {"LLM_MODEL": "deepseek-flash"},
                {"MODEL_NAME": "another-local-model"},
                {"LLM_MODEL": REQUIRED_MODEL, "MODEL_NAME": "another-local-model"}):
            with self.subTest(environment=environment), \
                    patch.dict(os.environ, environment, clear=True), \
                    patch("agent.llm.subprocess.run") as run, \
                    patch("agent.llm.urllib.request.urlopen") as urlopen, \
                    patch("agent.llm.urllib.request.build_opener") as build:
                with self.assertRaises(LLMError):
                    LLM()
                run.assert_not_called()
                urlopen.assert_not_called()
                build.assert_not_called()

    def test_parent_refuses_credentials_queries_fragments_and_nonlocal_urls(self):
        for address in (
                "http://user:password@127.0.0.1:8000/v1",
                "http://127.0.0.1:8000/v1?key=private",
                "http://127.0.0.1:8000/v1?",
                "http://127.0.0.1:8000/v1#fragment",
                "http://127.0.0.1:8000/v1#",
                "http://127.0.0.1.evil.example:8000/v1",
                "http://192.168.1.2:8000/v1",
                "http://127.0.0.1:8000/other",
                "file:///v1", "http://127.0.0.1:0/v1",
                "http://127.0.0.1:99999/v1", " http://127.0.0.1:8000/v1"):
            with self.subTest(address=address), \
                    patch.dict(os.environ, {"LLM_BASE_URL": address}, clear=True):
                with self.assertRaises(LLMError):
                    LLM()

    def test_loopback_ipv4_ipv6_and_localhost_are_allowed(self):
        for address in ("http://127.0.0.1:12345/v1", "http://127.0.0.2:8000/v1",
                        "http://[::1]:8000/v1", "http://localhost:8000/v1/"):
            with self.subTest(address=address), \
                    patch.dict(os.environ, {"LLM_BASE_URL": address}, clear=True):
                self.assertEqual(LLM().model, REQUIRED_MODEL)

    def test_chat_revalidates_mutated_model_before_subprocess(self):
        with patch.dict(os.environ, {}, clear=True):
            model = LLM()
            model.model = "different-model"
            with patch("agent.llm.subprocess.run") as run:
                with self.assertRaises(LLMError):
                    model.chat([], 5)
                run.assert_not_called()

    def test_worker_refuses_remote_endpoint_before_constructing_transport(self):
        status, _out, errors, build, opener, urlopen = self.worker(
            {"model": REQUIRED_MODEL}, {"LLM_BASE_URL": "https://api.deepseek.com/v1"})
        self.assertEqual(status, 1)
        self.assertIn("本机", errors)
        build.assert_not_called()
        opener.open.assert_not_called()
        urlopen.assert_not_called()

    def test_worker_refuses_forged_or_missing_model_before_any_network(self):
        for payload in ({"model": "deepseek-flash"}, {}, [], {"model": None}):
            with self.subTest(payload=payload):
                status, _out, errors, build, opener, urlopen = self.worker(payload)
                self.assertEqual(status, 1)
                self.assertIn(REQUIRED_MODEL, errors)
                build.assert_not_called()
                opener.open.assert_not_called()
                urlopen.assert_not_called()

    def test_worker_does_not_use_inherited_deepseek_credentials_or_thinking(self):
        payload = {"model": REQUIRED_MODEL, "messages": [],
                   "chat_template_kwargs": {"enable_thinking": False}}
        status, output, errors, build, opener, _urlopen = self.worker(payload, {
            "DEEPSEEK_API_KEY": "inherited-old-provider-key",
            "DEEPSEEK_THINKING": "enabled", "HTTPS_PROXY": "http://outside.invalid:1"})
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)["text"], "local fixture")
        request = opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(json.loads(request.data), payload)
        handlers = build.call_args.args
        self.assertIsInstance(handlers[0], urllib.request.ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], _NoRedirect)
        self.assertNotIn("inherited-old-provider-key", output + errors)

    def test_worker_uses_only_explicit_local_service_key(self):
        status, _out, errors, _build, opener, _urlopen = self.worker(
            {"model": REQUIRED_MODEL}, {"LLM_API_KEY": "local-service-key",
                                        "DEEPSEEK_API_KEY": "unused-old-key"})
        self.assertEqual(status, 0, errors)
        self.assertEqual(opener.open.call_args.args[0].get_header("Authorization"),
                         "Bearer local-service-key")

    def test_local_service_cannot_redirect_requests_to_a_remote_provider(self):
        with self.assertRaises(LLMError):
            _NoRedirect().redirect_request(None, None, 302, "Found", {},
                                           "https://api.deepseek.com/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
