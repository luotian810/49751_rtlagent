"""归因须绑定真实采样点，且绑定不能被当成 oracle 正确性的证明。"""
import copy
import json
import unittest

from agent.diagnosis import failure_observation, parse_diagnosis


FAIL = "RTL_AGENT_FAIL sample=7 reset=1 enable=1 count=04 expected=00"


def diagnosis(verdict="dut_error"):
    return {
        "verdict": verdict,
        "reason": "复位有效时 DUT 仍递增，违反复位优先级。",
        "spec_rule": "同步复位有效时计数器必须清零。",
        "evidence": {"sample": 7, "stimulus": {"reset": "1", "enable": "1"},
                     "expected": "count=00", "observed": "count=04",
                     "testbench_expected": "count=00"},
    }


def parse(value, log=FAIL):
    return parse_diagnosis(json.dumps(value), failure_log=log)


class DiagnosisTests(unittest.TestCase):
    def test_bound_dut_and_testbench_hypotheses_are_not_semantic_proofs(self):
        dut = diagnosis()
        tb = diagnosis("testbench_error")
        tb["evidence"].update(expected="count=04")
        tb.update(reason="DUT 符合题面，该采样点的测试台期望不符。", spec_rule="保持计数。")
        for value in (dut, tb):
            with self.subTest(verdict=value["verdict"]):
                result = parse(value)
                self.assertEqual(result, {**value, "observation_bound": True, "semantic_verified": False})
        unsure = {"verdict": "uncertain", "reason": "缺少历史激励。", "spec_rule": ""}
        self.assertEqual(parse(unsure, ""), unsure)

    def test_observation_extracts_only_first_actual_failure(self):
        observed = failure_observation("INFO: simulator started\n " + FAIL + " \n"
                                       "RTL_AGENT_FAIL sample=8 reset=0 count=05 expected=01")
        self.assertEqual(observed, {"sample": 7, "stimulus": {"reset": "1", "enable": "1"},
                                   "observed": "count=04", "testbench_expected": "count=00", "line": " " + FAIL + " "})
        self.assertEqual(parse(diagnosis(), observed["line"])["verdict"], "dut_error")

    def test_modelsim_prefix_is_removed_once_but_original_line_is_preserved(self):
        for prefix in ("# ", "  #", "\t#\t "):
            with self.subTest(prefix=prefix):
                original = prefix + FAIL + "  "
                observed = failure_observation("# run -all\n" + original)
                self.assertEqual(observed["line"], original)
                self.assertEqual(parse(diagnosis(), original)["verdict"], "dut_error")

    def test_source_echoes_are_not_failure_records(self):
        for line in ('# $display("' + FAIL + '");', '# ** Warning: source.sv:9: ' + FAIL,
                     '## ' + FAIL, 'source.sv:9: ' + FAIL):
            with self.subTest(line=line):
                self.assertIsNone(failure_observation(line))
                self.assertEqual(parse(diagnosis(), line)["verdict"], "uncertain")

    def test_no_guessing_missing_ambiguous_or_unsupported_log_fields(self):
        logs = ("", "RTL_AGENT_FAIL", "RTL_AGENT_FAIL timeout", "RTL_AGENT_FAIL a=1 expected=1 actual=0",
                "RTL_AGENT_FAIL sample=0 q=1 expected=0", "RTL_AGENT_FAIL sample=2 q=1 expected=0 expected=1",
                "RTL_AGENT_FAIL sample=2 a=0 a=1 q=1 expected=0", "RTL_AGENT_FAIL sample=2 q=1 garbage expected=0",
                "RTL_AGENT_FAIL timeout\n" + FAIL)
        for log in logs:
            with self.subTest(log=log):
                self.assertIsNone(failure_observation(log))
                self.assertEqual(parse(diagnosis(), log)["verdict"], "uncertain")
        self.assertEqual(parse_diagnosis(json.dumps(diagnosis()))["verdict"], "uncertain")

    def test_sample_and_all_stimulus_fields_must_match(self):
        changes = ({"sample": 8}, {"sample": "7"}, {"sample": True},
                   {"stimulus": {"reset": "1"}}, {"stimulus": {"reset": "0", "enable": "1"}},
                   {"stimulus": {"reset": "1", "enable": "1", "past_enable": "0"}},
                   {"stimulus": "reset=1 enable=1"})
        for change in changes:
            with self.subTest(change=change):
                value = diagnosis()
                value["evidence"].update(change)
                self.assertEqual(parse(value)["verdict"], "uncertain")

    def test_invented_output_or_cross_sample_observations_are_rejected(self):
        for change in ({"observed": "count=04 saturated=0"}, {"observed": "count=05"},
                       {"testbench_expected": "count=01"}, {"expected": "saturated=1"}):
            with self.subTest(change=change):
                value = diagnosis()
                value["evidence"].update(change)
                self.assertEqual(parse(value)["verdict"], "uncertain")
        value = diagnosis()
        value["evidence"].update(sample=8, observed="count=05")
        self.assertEqual(parse(value, FAIL + "\nRTL_AGENT_FAIL sample=8 reset=1 enable=1 count=05 expected=00")
                         ["verdict"], "uncertain")

    def test_numeric_equality_does_not_depend_on_padding_or_hex_case(self):
        value = diagnosis()
        value["evidence"].update(expected="count=0", observed="count=0004", testbench_expected="count=0")
        self.assertEqual(parse(value)["verdict"], "dut_error")
        value["evidence"]["expected"] = "count=0004"
        self.assertEqual(parse(value)["verdict"], "uncertain")
        value["evidence"].update(expected="count=0", observed="count=000A")
        self.assertEqual(parse(value, FAIL.replace("count=04", "count=0a"))["verdict"], "dut_error")

    def test_unknown_states_cannot_support_determinate_semantics(self):
        for unknown in ("xx", "z", "0X", "0x0"):
            value = diagnosis()
            value["evidence"]["observed"] = "count=" + unknown
            self.assertEqual(parse(value, FAIL.replace("count=04", "count=" + unknown))["verdict"], "uncertain")

    def test_json_fence_and_thinking_handling(self):
        valid = json.dumps(diagnosis())
        reply = "```json\n" + valid + "\n```"
        self.assertEqual(parse_diagnosis(reply, failure_log=FAIL)["verdict"], "dut_error")
        final = json.dumps({"verdict": "uncertain", "reason": "无法确认采样时刻。", "spec_rule": ""})
        for start in ("<think>", ""):
            result = parse_diagnosis(start + valid + "</think>\n```json\n" + final + "\n```", failure_log=FAIL)
            self.assertEqual(result["verdict"], "uncertain")
            self.assertEqual(result["reason"], "无法确认采样时刻。")
        self.assertEqual(parse_diagnosis("<think>" + valid, failure_log=FAIL)["verdict"], "uncertain")

    def test_invalid_or_ambiguous_json_stays_uncertain(self):
        for reply in ("", "FAIL", "[]", "null", '{"verdict":', json.dumps(diagnosis()) * 2,
                      "Explanation:\n" + json.dumps(diagnosis()), None):
            with self.subTest(reply=reply):
                self.assertEqual(parse_diagnosis(reply, failure_log=FAIL)["verdict"], "uncertain")

    def test_missing_or_invalid_fields_stay_uncertain(self):
        valid = diagnosis()
        cases = [{key: value for key, value in valid.items() if key != missing}
                 for missing in ("verdict", "reason", "spec_rule", "evidence")]
        cases.extend([dict(valid, verdict="DUT_ERROR"), dict(valid, reason=" "), dict(valid, reason=[]),
                      dict(valid, spec_rule=" "), dict(valid, spec_rule=None), dict(valid, evidence={})])
        for key in ("sample", "stimulus", "expected", "observed", "testbench_expected"):
            value = copy.deepcopy(valid)
            del value["evidence"][key]
            cases.append(value)
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(parse(value)["verdict"], "uncertain")


if __name__ == "__main__":
    unittest.main()

