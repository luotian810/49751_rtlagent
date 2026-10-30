"""Check clean-shell configuration and idempotent startup without model generation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
git_exe = shutil.which("git")
git_bash = Path(git_exe).parents[1] / "bin/bash.exe" if git_exe else Path("/missing")
BASH = os.environ.get("BASH_EXE") or (str(git_bash) if git_bash.is_file() else shutil.which("bash"))


@unittest.skipUnless(BASH, "Bash required for the Linux entry points")
class StartupDefaultsTests(unittest.TestCase):
    def environment(self, directory):
        env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "TEMP", "TMP")
               if key in os.environ}
        env.update(PYTHON_EXE=sys.executable.replace("\\", "/"),
                   AGENT_TMP=directory, EDA_TMP=directory + "/eda",
                   MSYS_ENV_CONV_EXCL="*")
        return env

    def shell(self, arguments, env):
        return subprocess.run([BASH, *arguments], cwd=ROOT, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)

    def test_clean_shell_defaults_match_declared_model_and_preserve_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory.replace("\\", "/"))
            code = ('source serve/defaults.sh; "$PYTHON_EXE" -c '
                    "'import json,os; print(json.dumps({k:os.environ[k] for k in "
                    '["MODEL","MODEL_NAME","LLM_MODEL","INFERENCE_BACKEND","MAX_LEN","HIP_VISIBLE_DEVICES"]}))' + "'")
            result = self.shell(["-c", code], env)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = json.loads(result.stdout)
            manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(values["MODEL_NAME"], manifest["model"]["name"])
            self.assertEqual(values["LLM_MODEL"], values["MODEL_NAME"])
            self.assertEqual(values["INFERENCE_BACKEND"], manifest["serving"]["backend"])
            self.assertEqual(int(values["MAX_LEN"]), manifest["context"]["max_model_len"])
            self.assertEqual(values["HIP_VISIBLE_DEVICES"], "0")
            env["MODEL"] = directory.replace("\\", "/") + "/weights/Qwen3-14B-Q4_K_M.gguf"
            override = json.loads(self.shell(["-c", code], env).stdout)
            self.assertEqual(override["MODEL"], env["MODEL"])
            self.assertEqual(override["MODEL_NAME"], values["MODEL_NAME"])

    def test_start_reuses_ready_model_without_manual_model_variables(self):
        class Models(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"data":[{"id":"Qwen3-14B-Q4_K_M"}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Models)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                env = self.environment(directory.replace("\\", "/"))
                env["PORT"] = str(server.server_port)
                # The ready path must not need the binary or start another model.
                env["LLAMA_SERVER"] = "/does-not-exist"
                result = self.shell(["serve/start.sh"], env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("already ready", result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_inconsistent_names_fail_before_starting_a_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.environment(directory.replace("\\", "/"))
            env.update(MODEL_NAME="wrong", LLM_MODEL="Qwen3-14B-Q4_K_M")
            result = self.shell(["serve/start.sh"], env)
            self.assertEqual(result.returncode, 2)
            self.assertIn("same local served model name", result.stderr)


if __name__ == "__main__":
    unittest.main()
