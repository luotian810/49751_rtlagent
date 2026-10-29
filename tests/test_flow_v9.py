"""V9 flow controls: bounded input evidence and no repeated tool work."""
import json
import unittest
from unittest.mock import patch

from agent.llm import Reply
from agent.verification import CheckResult
from tests import test_flow_v2 as legacy
from tests import test_iteration_v7 as v7
from tests.test_iteration_v7 import COMBO_LOG, witness_reply
from tests.test_verification_plan_v4 import COMBO_DUT
from tests.test_verification_plan_v5 import signed_plan


class V9FlowTests(unittest.TestCase):
    run_flow = v7.V7FlowTests.run_flow

    def test_repair_gets_bound_history_and_rule_but_no_oracle_algorithm(self):
        wrong = COMBO_DUT.replace('$signed(a) + $signed(b)', "6'b0")
        failed = CheckResult('failed', 'fake', COMBO_LOG, 0,
                             {'simulation_executed': True, 'assertion_failed': True, 'stage': 'simulate'})
        out, summary, calls = self.run_flow(
            [Reply(wrong), Reply(json.dumps(signed_plan())), Reply(witness_reply()), Reply(COMBO_DUT)],
            [failed, CheckResult('passed', 'fake', 'RTL_AGENT_PASS', 0)])
        self.assertTrue(summary['selfcheck_passed'])
        repair = calls[3].args[0][1]['content']
        for evidence in ('"sample": 1', '"observed": "sum=00"', '"testbench_expected": "sum=03"',
                         '"history"', '"sampling"', '"inputs": {"a": "01", "b": "02"}', '题面依据'):
            self.assertIn(evidence, repair)
        for oracle in ('stim_total', 'module tb', '__va_expected', 'HIDDEN_ANSWER'):
            self.assertNotIn(oracle, repair)
        self.assertIn('stim_total', (out/'generated_tb.sv').read_text(encoding='utf-8'))
        self.assertEqual(len(calls), 4)

    def test_name_only_plan_normalization_does_not_spend_recovery_call(self):
        plan = signed_plan()
        plan['temporaries'][0]['name'] = 'total'
        plan['expected']['sum'] = 'total'
        out, summary, calls = self.run_flow(
            [Reply(COMBO_DUT), Reply(json.dumps(plan))],
            [CheckResult('passed', 'fake', 'RTL_AGENT_PASS', 0)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(len(calls), 2)
        self.assertFalse((out/'round_01/testbench_format_repair_reply.txt').exists())


class RepeatedCandidateTests(unittest.TestCase):
    run_flow = legacy.FlowTests.run_flow

    def test_comment_and_space_repair_does_not_run_tools_again(self):
        failure = CheckResult('failed', 'fake', 'ERROR: syntax error [rtl.sv:1]', 0,
                              {'stage': 'compile', 'compile_passed': False})
        with patch('builtins.print'):
            out, summary, calls, simulations = self.run_flow(
                [Reply(legacy.DUT), Reply(legacy.DUT.replace('assign q=a;', '/* comment */ assign  q = a ;'))],
                [], lint=[failure])
        self.assertEqual(summary['stop_reason'], 'repeated_candidate')
        self.assertEqual(summary['unique_candidates'], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(simulations, [])
        self.assertFalse((out/'round_02/lint').exists())
        events = [json.loads(line) for line in (out/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        event = next(e for e in events if e['tool'] == 'no_progress')
        self.assertEqual(event['previous_round'], 1)
        self.assertEqual(event['comparison'], 'tokens')


if __name__ == '__main__':
    unittest.main()
