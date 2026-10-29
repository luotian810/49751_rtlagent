"""Name normalization controls; these hand-written fixtures are not Qwen results."""
import copy
import json
import re
import unittest

from agent.verification_plan import PlanError, build_testbench, _temporary_names
from tests import test_verification_plan_v4 as fixtures
from tests.test_verification_plan_v5 import signed_plan, compact_fixture


def rename_temporaries(plan):
    """Change only fixture symbol spelling, preserving expressions and widths."""
    mapping = {item['name']: item['name'].removeprefix('stim_') for item in plan['temporaries']}
    text = json.dumps(plan)
    return json.loads(re.sub(r'\b[A-Za-z_]\w*\b', lambda m: mapping.get(m[0], m[0]), text))


class TemporaryNamesTests(unittest.TestCase):
    def test_normalization_matches_original_algorithm_and_is_replayable(self):
        for original, top, spec in (
                (signed_plan(), 'SignedAdder', fixtures.COMBO_SPEC),
                (compact_fixture(fixtures.native_parity_group_plan()), 'GroupParity', fixtures.PARITY_SPEC),
                (compact_fixture(fixtures.native_fifo_plan()), 'SmallQueue', fixtures.FIFO_SPEC)):
            plan = rename_temporaries(original)
            before = copy.deepcopy(plan)
            with self.subTest(top=top):
                tb, saved = build_testbench(json.dumps(plan), top, spec)
                self.assertEqual(tb, build_testbench(json.dumps(original), top, spec)[0])
                self.assertEqual(tb, build_testbench(json.dumps(saved), top, spec)[0])
                self.assertEqual(plan, before)

    def test_rejects_port_state_reserved_duplicate_and_alias_collisions(self):
        for name in ('a', 'sum', '__va_tests', 'old_ref_value', 'RTL_AGENT_PASS', 'signed', 'integer'):
            plan = signed_plan()
            plan['temporaries'][0]['name'] = name
            with self.subTest(name=name), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), 'SignedAdder', fixtures.COMBO_SPEC)
        for names in (('total', 'total'), ('total', 'stim_total'), ('stim_total', 'total')):
            plan = signed_plan()
            plan['temporaries'] = [{'name': name, 'width': 6, 'expr': 'a+b'} for name in names]
            with self.subTest(names=names), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), 'SignedAdder', fixtures.COMBO_SPEC)
        plan = signed_plan()
        plan['states'] = [{'name': 'ref_sum', 'width': 6, 'initial': '0', 'next': 'ref_sum'}]
        plan['temporaries'][0]['name'] = 'ref_sum'
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), 'SignedAdder', fixtures.COMBO_SPEC)

    def test_numeral_system_function_comments_and_longer_names_keep_meaning(self):
        spec = 'module Echo(input [7:0] word, output [7:0] result);'
        plan = {'states': [], 'temporaries': [
            {'name': 'hff', 'width': 8, 'expr': "word & 8'hff /* hff stays a comment */"},
            {'name': 'hff2', 'width': 8, 'expr': '$unsigned(hff)'}],
            'expected': {'result': 'hff2'}, 'stimulus': {'mode': 'auto'}}
        _, saved = build_testbench(json.dumps(plan), 'Echo', spec)
        self.assertEqual(saved['temporaries'][0]['expr'], plan['temporaries'][0]['expr'])
        self.assertEqual(saved['temporaries'][1]['expr'], '$unsigned(stim_hff)')
        self.assertEqual(saved['expected'], {'result': 'stim_hff2'})

    def test_output_reads_unknown_self_forward_references_and_stimulus_remain_rejected(self):
        for expression in ('sum', 'total', 'missing', '$random(__va_seed)', 'later'):
            plan = rename_temporaries(signed_plan())
            plan['temporaries'][0]['expr'] = expression
            plan['temporaries'].append({'name': 'later', 'width': 6, 'expr': 'a+b'})
            with self.subTest(expression=expression), self.assertRaises(PlanError):
                build_testbench(json.dumps(plan), 'SignedAdder', fixtures.COMBO_SPEC)
        plan = rename_temporaries(signed_plan())
        plan['stimulus']['random']['values'][0] = 'total'
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), 'SignedAdder', fixtures.COMBO_SPEC)

    def test_decimal_exponent_and_sized_literal_are_not_identifier_substrings(self):
        for name, expression in [('e3', 'e3 + 1e3 + 1.2e3 + 1.0e-3'),
                                 ('hff', "hff & 1_6'hff & 16' hff"),
                                 ('b10', "b10 ^ 8'b10")]:
            plan = {'temporaries': [{'name': name, 'width': 16, 'expr': '0'}],
                    'states': [], 'expected': {'value': expression}}
            with self.subTest(name=name):
                saved = _temporary_names(plan, [])
                self.assertEqual(saved['expected']['value'], 'stim_' + expression)


class TemporaryExecutionTests(unittest.TestCase):
    setUp = fixtures.PlanExecutionTests.setUp
    simulate = fixtures.PlanExecutionTests.simulate

    def test_signed_reference_and_wrong_design_keep_their_outcomes(self):
        plan = rename_temporaries(signed_plan())
        good = self.simulate(plan, fixtures.COMBO_DUT, 'SignedAdder', fixtures.COMBO_SPEC, 'renamed-good')
        bad = self.simulate(plan, fixtures.COMBO_DUT.replace('$signed(a) + $signed(b)', '$signed(a) - $signed(b)'),
                            'SignedAdder', fixtures.COMBO_SPEC, 'renamed-bad')
        self.assertEqual(good.status, 'passed', good.log)
        self.assertEqual(bad.status, 'failed', bad.log)

    def test_width_variations_preserve_bit_patterns_and_reject_wrong_oracle(self):
        for width in (3, 11, 37):
            spec = f'module Echo(input [{width-1}:0] packet, output [{width-1}:0] returned);'
            dut = spec + ' assign returned=packet; endmodule'
            plan = {'states': [], 'temporaries': [{'name': 'word', 'width': width, 'expr': 'packet'}],
                    'expected': {'returned': 'word'}, 'stimulus': {'mode': 'auto'}}
            with self.subTest(width=width):
                good = self.simulate(plan, dut, 'Echo', spec, f'width-{width}')
                self.assertEqual(good.status, 'passed', good.log)
                plan['temporaries'][0]['expr'] = '~packet'
                bad = self.simulate(plan, dut, 'Echo', spec, f'bad-oracle-{width}')
                self.assertEqual(bad.status, 'failed', bad.log)


if __name__ == '__main__':
    unittest.main()
