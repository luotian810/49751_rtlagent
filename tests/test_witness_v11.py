"""Known input history can diagnose an unknown DUT output without leaking it."""
import copy
import json
import unittest

from agent.diagnosis import failure_observation
from agent.verification_plan import build_testbench
from agent.witness import parse_witness, prepare_witness
from tests.test_iteration_v7 import witness_reply
from tests.test_skill_v6 import register_case
from tests import test_verification_plan_v4 as fixtures


def reset_failure(width=7, active=0, asynchronous=True, actual='x', after_edge=0):
    plan, dut, top, spec = register_case(width, 'negedge', active, asynchronous)
    _, normalized = build_testbench(json.dumps(plan), top, spec)
    initial = (1 << (width-1)) | 1
    inputs = f'clear_line={active:x} accept_word=0 incoming=0'
    log = (f'RTL_AGENT_SAMPLE sample=1 after_edge={after_edge} {inputs} stored={actual}\n'
           f'RTL_AGENT_FAIL sample=1 {inputs} stored={actual} expected={initial:x}\n')
    return normalized, log, initial, plan, dut, top, spec


class UnknownOutputWitnessTests(unittest.TestCase):
    def test_unknown_output_is_removed_from_complete_reset_context(self):
        for width in (1, 7, 35):
            for actual in ('x', 'Z'):
                for active in (0, 1):
                    plan, log, initial, *_ = reset_failure(width, active, actual=actual)
                    context, reason = prepare_witness(plan, log)
                    with self.subTest(width=width, active=active, actual=actual):
                        self.assertEqual(reason, '')
                        self.assertEqual(context['history'][0]['inputs']['clear_line'], str(active))
                        self.assertNotIn('stored', context['history'][0]['inputs'])
                        self.assertNotIn('observed', json.dumps(context))
                        result = parse_witness(witness_reply(f'{initial:x}',output='stored'),
                                               failure_observation(log), target=context['target'])
                        self.assertEqual(result['verdict'], 'dut_error')
                        self.assertFalse(result['semantic_verified'])

    def test_synchronous_reset_requires_observed_sampling_edge(self):
        plan, before, *_ = reset_failure(asynchronous=False)
        self.assertIsNone(prepare_witness(plan, before)[0])
        after = before.replace('after_edge=0', 'after_edge=1')
        self.assertIsNotNone(prepare_witness(plan, after)[0])

    def test_missing_samples_unknown_inputs_and_unknown_oracle_remain_blocked(self):
        plan, log, *_ = reset_failure()
        for bad in (log.split('\n',1)[1], log.replace('incoming=0','incoming=x'),
                    log.replace('expected=41','expected=x'),
                    log.replace('stored=x expected', 'stored=z expected'),
                    log.replace('clear_line=0','clear_line=1')):
            with self.subTest(log=bad):
                self.assertIsNone(prepare_witness(plan, bad)[0])

    def test_unknown_actual_needs_bound_target_and_agreeing_known_expectation(self):
        plan, log, initial, *_ = reset_failure()
        context, _ = prepare_witness(plan, log)
        observation = failure_observation(log)
        reply = witness_reply(f'{initial:x}',output='stored')
        self.assertEqual(parse_witness(reply,observation)['verdict'],'uncertain')
        for value in ('0','x','80'):
            result = parse_witness(witness_reply(value,output='stored'), observation, target=context['target'])
            self.assertEqual(result['verdict'],'uncertain')
        for wrong in ({'sample':2,'output':context['target']['output']},
                      {'sample':1,'output':{'name':'other','width':7}},
                      {'sample':1,'output':{'name':'stored','width':True}}):
            self.assertEqual(parse_witness(reply,observation,target=wrong)['verdict'],'uncertain')

    def test_mixed_unknown_patterns_obey_port_width_and_renaming(self):
        plan, log, initial, *_ = reset_failure(width=7,actual='3x')
        context, reason = prepare_witness(plan,log)
        self.assertEqual(reason,'')
        self.assertIsNone(prepare_witness(plan,log.replace('3x','8x'))[0])
        renamed = copy.deepcopy(plan)
        for port in renamed['ports']:
            if port['name']=='stored': port['name']='result_bus'
        context, reason = prepare_witness(renamed,log.replace('stored=','result_bus='))
        self.assertEqual(reason,'')
        self.assertEqual(context['target']['output']['name'],'result_bus')


class UnknownOutputSimulationTests(unittest.TestCase):
    setUp = fixtures.PlanExecutionTests.setUp
    simulate = fixtures.PlanExecutionTests.simulate

    def test_real_async_reset_failure_is_bound_and_correct_design_still_passes(self):
        for width, active in ((3,0),(7,1)):
            _, _, initial, plan, good, top, spec = reset_failure(width,active)
            suffix = f'v11-{width}-{active}'
            accepted = self.simulate(plan,good,top,spec,suffix+'-good')
            self.assertEqual(accepted.status,'passed',accepted.log)
            reset_edge = 'posedge' if active else 'negedge'
            wrong = good.replace(f' or {reset_edge} clear_line','')
            rejected = self.simulate(plan,wrong,top,spec,suffix+'-bad')
            self.assertEqual(rejected.status,'failed',rejected.log)
            _, normalized = build_testbench(json.dumps(plan),top,spec)
            context, reason = prepare_witness(normalized,rejected.log)
            self.assertEqual(reason,'')
            observation = failure_observation(rejected.log)
            self.assertIn('x',observation['observed'])
            result = parse_witness(witness_reply(f'{initial:x}',output='stored'),
                                   observation,target=context['target'])
            self.assertEqual(result['verdict'],'dut_error')


if __name__ == '__main__':
    unittest.main()
