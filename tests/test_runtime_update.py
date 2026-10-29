"""临时 EDA 工作目录的证据保留与失败清理。"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.verification import Toolchain, CheckResult


class WorkspaceTests(unittest.TestCase):
    def test_evidence_survives_and_large_database_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scratch, output = root / "scratch", root / "out"
            scratch.mkdir()
            unrelated = scratch / "other-task.txt"
            unrelated.write_text("keep")

            def check(source, top, work, timeout):
                self.assertEqual(work.parent, scratch)
                for name in ("rtl.sv", "wave.vcd", "synthesized.dcp", "utilization.rpt"):
                    (work / name).write_text("evidence")
                (work / "xsim.dir").mkdir()
                (work / "xsim.dir" / "database").write_text("large intermediate")
                return CheckResult("passed", "fake", "", 0, {"waveform": str(work / "wave.vcd")})

            with patch.dict(os.environ, {"EDA_TMP": str(scratch)}), patch.object(Toolchain, "_simulate") as run:
                run.side_effect = lambda source, tb, top, work, timeout: check(source, top, work, timeout)
                result = Toolchain("none").simulate("source", "tb", "TopModule", output)
            self.assertEqual(list(scratch.iterdir()), [unrelated])
            self.assertTrue(Path(result.details["waveform"]).is_file())
            self.assertTrue((output / "synthesized.dcp").is_file())
            self.assertFalse((output / "xsim.dir").exists())

    def test_cancelled_check_cleans_only_its_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory) / "scratch"

            def cancel(*args):
                work = args[-2]
                (work / "failure.log").write_text("cancelled")
                raise SystemExit(143)

            with patch.dict(os.environ, {"EDA_TMP": str(scratch)}), \
                    patch.object(Toolchain, "_lint", side_effect=cancel):
                with self.assertRaises(SystemExit):
                    Toolchain("none").lint("source", "TopModule", Path(directory) / "out")
            self.assertFalse(list(scratch.iterdir()))
            self.assertEqual((Path(directory) / "out" / "failure.log").read_text(), "cancelled")


if __name__ == "__main__":
    unittest.main()
