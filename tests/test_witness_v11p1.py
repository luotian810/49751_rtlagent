"""V11 regression: hex padding is formatting, not additional signal bits."""
import json
import unittest

from agent.diagnosis import failure_observation
from agent.llm import Reply
from agent.verification import CheckResult
from agent.witness import parse_witness, prepare_witness
from tests import test_iteration_v7 as v7
from tests.test_verification_plan_v4 import COMBO_DUT
from tests.test_verification_plan_v5 import signed_plan
from tests.test_witness_v11 import reset_failure


def wire_failure(width, value, output='delivered', padding=0):
    plan = {'clock': None, 'ports': [
        {'name': 'incoming', 'direction': 'input', 'width': width},
        {'name': output, 'direction': 'output', 'width': width}]}
    actual = f'{value:0{padding}x}'
    expected = f'{value ^ 1:0{padding}x}'
    inputs = f'incoming={actual}'
    log = (f'RTL_AGENT_SAMPLE sample=1 after_edge=0 {inputs} {output}={actual}\n'
           f'RTL_AGENT_FAIL sample=1 {inputs} {output}={actual} expected={expected}\n')
    return plan, log


class PaddedHexWitnessTests(unittest.TestCase):
    def test_known_reply_padding_matches_unpadded_across_widths_and_names(self):
        for width in (1, 3, 4, 7, 8, 35):
            for name in ('delivered', 'renamed_bus'):
                for value in (0, (1 << width) - 1):
                    plan, log = wire_failure(width, value, name)
                    context, reason = prepare_witness(plan, log)
                    self.assertEqual(reason, '')
                    observation = failure_observation(log)
                    results = [parse_witness(v7.witness_reply(text, output=name), observation,
                                             target=context['target'])
                               for text in (f'{value:x}', '000000' + f'{value:x}')]
                    with self.subTest(width=width, name=name, value=value):
                        self.assertEqual([r['verdict'] for r in results], ['testbench_error'] * 2)
                        self.assertTrue(all(r['observation_bound'] and not r['semantic_verified']
                                            for r in results))

    def test_padding_does_not_prevent_bound_unknown_output_diagnosis(self):
        for width in (1, 3, 4, 7, 8, 35):
            plan, log, initial, *_ = reset_failure(width=width)
            context, reason = prepare_witness(plan, log)
            self.assertEqual(reason, '')
            observation = failure_observation(log)
            reply = v7.witness_reply('0000' + f'{initial:x}', output='stored')
            with self.subTest(width=width):
                self.assertEqual(parse_witness(reply, observation,
                                               target=context['target'])['verdict'], 'dut_error')
                self.assertEqual(parse_witness(reply, observation)['verdict'], 'uncertain')

    def test_padded_input_and_observation_keep_complete_reset_history(self):
        plan, log, initial, *_ = reset_failure(width=3, active=1, actual='0')
        for name, value in (('clear_line', '1'), ('accept_word', '0'),
                            ('incoming', '0'), ('stored', '0'), ('expected', f'{initial:x}')):
            log = log.replace(f'{name}={value}', f'{name}=0000{value}')
        context, reason = prepare_witness(plan, log)
        self.assertEqual(reason, '')
        self.assertEqual(context['history'][0]['inputs'],
                         {'clear_line': '00001', 'accept_word': '00000', 'incoming': '00000'})
        self.assertEqual(parse_witness(v7.witness_reply('0000', output='stored'),
                                      failure_observation(log), target=context['target'])['verdict'],
                         'testbench_error')
        self.assertIsNone(prepare_witness(plan, log.replace('clear_line=00001', 'clear_line=00000'))[0])

    def test_real_overflow_malformed_and_unknown_padding_remain_rejected(self):
        for width in (1, 3, 4, 7, 8, 35):
            plan, log = wire_failure(width, 0, padding=8)
            context, reason = prepare_witness(plan, log)
            self.assertEqual(reason, '')
            for expected in ('0000' + f'{1 << width:x}', '-1', '0x0', '', '00x'):
                with self.subTest(width=width, expected=expected):
                    reply = v7.witness_reply(expected, output='delivered')
                    self.assertEqual(parse_witness(reply, failure_observation(log),
                                                   target=context['target'])['verdict'], 'uncertain')
            _, overflow_log = wire_failure(width, 1 << width)
            self.assertIsNone(prepare_witness(plan, overflow_log)[0])
        plan, log, *_ = reset_failure(width=7, actual='00x')
        self.assertIsNone(prepare_witness(plan, log)[0])


class PaddedHexFlowTests(unittest.TestCase):
    run_flow = v7.V7FlowTests.run_flow

    def test_correct_candidate_survives_padded_blind_reply_without_dut_repair(self):
        plan = signed_plan()
        plan['expected']['sum'] = "6'b0"
        plan['stimulus'] = {'mode': 'auto'}
        log = ('RTL_AGENT_SAMPLE sample=1 after_edge=0 a=03 b=04 sum=07\n'
               'RTL_AGENT_FAIL sample=1 a=03 b=04 sum=07 expected=00\n')
        failed = CheckResult('failed', 'fake', log, 0,
                             {'simulation_executed': True, 'assertion_failed': True, 'stage': 'simulate'})
        out, summary, calls = self.run_flow(
            [Reply(COMBO_DUT), Reply(json.dumps(plan)), Reply(v7.witness_reply('000007'))], [failed])
        self.assertEqual(summary['stop_reason'], 'selfcheck_testbench_error')
        self.assertEqual(len(calls), 3)
        self.assertEqual((out / 'solution.v').read_text(encoding='utf-8').strip(), COMBO_DUT.strip())
        self.assertFalse((out / 'round_02').exists())


if __name__ == '__main__':
    unittest.main()
