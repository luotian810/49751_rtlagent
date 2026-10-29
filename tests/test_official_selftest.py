"""适配器回归：保留官方判据、异常排除与 manifest 路径语义。"""

import importlib.util
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("official_selftest", ROOT / "scripts/official_selftest.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class OfficialAdapterTests(unittest.TestCase):
    def test_vendored_source_matches_original(self):
        original = ROOT.parent / "rtlagent2026/selftest"
        if not original.is_dir():
            self.skipTest("upstream checkout is not present")
        for relative in ("judge.py", "judge/veval-judge", "judge/l3_synth.tcl", "judge/PROVENANCE.md"):
            self.assertEqual((original / relative).read_bytes(), (module.VENDOR / relative).read_bytes())

    def test_vendored_tasks_match_original(self):
        original = ROOT.parent / "rtlagent2026/tasks"
        if not original.is_dir():
            self.skipTest("upstream task checkout is not present; standalone ZIP uses the bundled fixtures")
        expected = [Path("README.md")]
        for name in ("ex01_popcount8", "ex02_detect_1101", "ex03_lfsr8"):
            expected.extend(path.relative_to(original) for path in (original / name).rglob("*") if path.is_file())
        bundled = {path.relative_to(module.DEFAULT_TASKS) for path in module.DEFAULT_TASKS.rglob("*") if path.is_file()}
        self.assertEqual(bundled, set(expected))
        for relative in expected:
            self.assertEqual((original / relative).read_bytes(), (module.DEFAULT_TASKS / relative).read_bytes(), str(relative))

    def test_builtin_reference_tasks_are_complete_without_an_upstream_checkout(self):
        args = SimpleNamespace(tasks=module.DEFAULT_TASKS, only=None)
        tasks = module.collect_tasks(args, None)
        self.assertEqual({config["task_id"] for _, config, _ in tasks},
                         {"ex01_popcount8", "ex02_detect_1101", "ex03_lfsr8"})
        for task_dir, config, reference in tasks:
            self.assertTrue(reference.is_relative_to(module.DEFAULT_TASKS))
            self.assertTrue((task_dir / "prompt.txt").is_file())
            self.assertTrue((task_dir / config["reference_module"]).is_file())
            self.assertTrue((task_dir / config["testbench"]).is_file())

    def test_original_simulation_verdicts_survive_adapter(self):
        cases = [
            ("Mismatches: 0 in 42 samples\n", False, "L2"),
            ("Mismatches: 1 in 42 samples\n", False, "L1"),
            ("Mismatches: 0 in 0 samples\n", False, "L1"),
            ("Simulation completed\n", False, "L1"),
            ("Mismatches: 0 in 42 samples\nTIMEOUT\n", True, "L1"),
            ("Could not obtain the necessary license for Simulator.\n", False, "LICENSE_ERROR"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index, (output, timeout, expected) in enumerate(cases):
                class Runner:
                    def version(self):
                        return "2025.2"

                    def run(self, command, cwd, log, limit, tag):
                        log.write(f"\n===== [{tag}] test =====\n")
                        if tag == "xsim":
                            log.write(output)
                        log.flush()
                        return (124 if timeout and tag == "xsim" else 0), timeout and tag == "xsim", 0.0

                official, adapter = module.load_judges(Runner())
                source = root / "source.sv"
                source.write_text("module TopModule; endmodule", encoding="utf-8")
                args = SimpleNamespace(workdir=str(root / str(index)), clean=False,
                                       dut=str(source), ref=str(source), test=str(source), level=2,
                                       timeout_compile=1, timeout_elab=1, timeout_sim=1)
                raw = official.judge(args)
                self.assertEqual(raw["verdict"], expected)
                adapted = module.translate_result(adapter, raw, {"task_id": "test"})
                self.assertEqual(adapted["verdict"], expected)
                self.assertEqual(adapted["excluded_from_score"], expected == "LICENSE_ERROR")

    def test_metrics_do_not_change_grade(self):
        official, adapter = module.load_judges(SimpleNamespace(run=None, version=None))
        raw = {"level": 3, "verdict": "L3", "stages": {"synth": {"status": "OK", "LUT": 0, "WNS_ns": -1.0}}}
        result = module.translate_result(adapter, raw, {"task_id": "test"})
        self.assertEqual(result["level"], 3)
        self.assertEqual(result["synthesis_metrics"], {"LUT": 0, "WNS_ns": -1.0})

    def test_windows_heap_crash_is_local_environment_error_without_changing_raw_verdict(self):
        _, adapter = module.load_judges(SimpleNamespace(run=None, version=None))
        for rc in (3221226356, -1073740940):
            raw = {"level": 2, "verdict": "L2", "mismatches": 0, "samples": 257,
                   "stages": {"synth": {"status": "SYNTH_FAIL", "rc": rc}}}
            before = copy.deepcopy(raw)
            result = module.translate_result(adapter, raw, {"task_id": "test"})
            self.assertEqual(raw, before)
            self.assertEqual(result["verdict"], "L2")
            self.assertEqual(result["upstream_level"], 2)
            self.assertEqual(result["local_status"], "TOOL_CRASH")
            self.assertEqual(result["local_environment_error"]["exit_code"], rc)
            self.assertTrue(result["excluded_from_score"])
            self.assertIsNone(result["level"])
            self.assertIsNone(result["coefficient"])
            self.assertTrue(result["stages"]["simulate"])
            self.assertFalse(result["stages"]["synth"])

    def test_ordinary_synthesis_failure_is_not_reclassified_as_tool_crash(self):
        _, adapter = module.load_judges(SimpleNamespace(run=None, version=None))
        raw = {"level": 2, "verdict": "L2", "stages": {"synth": {"status": "SYNTH_FAIL", "rc": 1}}}
        result = module.translate_result(adapter, raw, {"task_id": "test"})
        self.assertEqual(result["level"], 2)
        self.assertIsNone(result["local_environment_error"])
        self.assertFalse(result["excluded_from_score"])

    def test_manifest_paths_are_relative_to_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "solutions.json"
            manifest.write_text(json.dumps({"task": "subdir/solution.v"}), encoding="utf-8")
            paths = module.load_solutions(SimpleNamespace(reference=False, generated=False, solution_manifest=manifest))
            self.assertEqual(paths["task"], (manifest.parent / "subdir/solution.v").resolve())


if __name__ == "__main__":
    unittest.main()
