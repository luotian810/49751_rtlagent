"""Explicit prose interfaces: complete binding or conservative abstention."""
import json
import unittest

from agent.interface import check_interface, specification_ports
from agent.verification_plan import PlanError, build_testbench, plan_contract


def listed(top='DataRelay', width=7, default=True, signed=False):
    return (f'I would like you to implement a module named {top} with the following\ninterface.\n'
            + ('All input and output ports are one bit unless otherwise\nspecified.\n' if default else '')
            + f'\n - input {"signed " if signed else ""}incoming ({width} bits)\n'
            + f' - output {"signed " if signed else ""}published ({width} bits)\n\n'
            + 'The output is the input bit pattern without a clock.')


class ListedInterfaceTests(unittest.TestCase):
    def test_explicit_names_widths_and_signs_are_shared_with_plan_contract(self):
        for top in ('DataRelay', 'Renamed_Unit'):
            for width in (1, 7, 35):
                for signed in (False, True):
                    spec = listed(top, width, default=False, signed=signed)
                    ports = specification_ports(spec, '', top)
                    with self.subTest(top=top, width=width, signed=signed):
                        self.assertEqual([p['width'] for p in ports], [width, width])
                        self.assertEqual([p['signed'] for p in ports], [signed, signed])
                        self.assertEqual(plan_contract(spec, '', top)['ports'], ports)

    def test_omitted_width_requires_explicit_local_scalar_default(self):
        spec = listed(width=1).replace(' (1 bits)', '')
        self.assertTrue(plan_contract(spec, '', 'DataRelay')['ports_fixed'])
        absent = spec.replace('All input and output ports are one bit unless otherwise\nspecified.\n', '')
        self.assertIsNone(specification_ports(absent, '', 'DataRelay'))
        outside = 'All input and output ports are one bit unless otherwise specified.\n'+absent
        self.assertIsNone(specification_ports(outside, '', 'DataRelay'))

    def test_body_prose_starting_with_input_is_not_an_extra_port(self):
        spec = listed() + '\ninput incoming is sampled on each active clock edge.'
        self.assertEqual(len(specification_ports(spec, '', 'DataRelay')), 2)
        for declaration in ('output later (2 bits)', 'input hidden (WIDTH bits)',
                            'output signed later', '+ output later (2 bits)'):
            with self.subTest(declaration=declaration):
                self.assertIsNone(specification_ports(spec+'\n'+declaration, '', 'DataRelay'))

    def test_incomplete_duplicate_or_complex_lists_abstain(self):
        source = listed()
        variants = [source.replace('published (7 bits)', 'published (WIDTH bits)'),
                    source.replace('published (7 bits)', 'published (0 bits)'),
                    source.replace('published (7 bits)', 'published (4097 bits)'),
                    source.replace('published (7 bits)', 'published, another (7 bits)'),
                    source.replace('- output', 'output'),
                    source.replace('- output', '- inout'),
                    source.replace('- output', '* output'),
                    source.replace('published (7 bits)', 'incoming (7 bits)'),
                    source+'\n- output later (2 bits)',
                    source+'\nmodule named Another with the following interface.\n- input d (1 bit)',
                    source.replace('interface.', 'interface. An optional port may be omitted.')]
        for spec in variants:
            with self.subTest(spec=spec):
                self.assertIsNone(specification_ports(spec, '', 'DataRelay'))

    def test_ambiguous_hdl_never_falls_back_to_prose_list(self):
        for declaration in ('module DataRelay(input [W-1:0] incoming, output published);',
                            'module Helper(input x);',
                            'module DataRelay(input incoming, output published);\n'
                            'module DataRelay(input [2:0] incoming, output published);'):
            self.assertIsNone(specification_ports(listed()+'\n'+declaration, '', 'DataRelay'))
        explicit = 'module DataRelay(input [4:0] source, output result);'
        self.assertEqual(specification_ports(listed(), explicit, 'DataRelay')[0]['name'], 'source')

    def test_strict_complete_lists_reject_missing_width_direction_and_signed_drift(self):
        spec = listed(width=7, signed=True)
        good = 'module DataRelay(input signed [6:0] incoming, output signed [6:0] published); assign published=incoming; endmodule'
        self.assertTrue(check_interface(good, spec, '', 'DataRelay')[0])
        for bad in (good.replace('published', 'other'), good.replace('[6:0]', '[7:0]', 1),
                    good.replace('input signed', 'output signed'), good.replace('input signed', 'input')):
            with self.subTest(bad=bad):
                self.assertFalse(check_interface(bad, spec, '', 'DataRelay')[0])

    def test_incomplete_prose_remains_advisory(self):
        spec = 'module named DataRelay\n- input incoming (7 bits)\n- output published (7 bits)'
        bad = 'module DataRelay(input incoming, output published); assign published=incoming; endmodule'
        self.assertIsNone(specification_ports(spec, '', 'DataRelay'))
        self.assertTrue(check_interface(bad, spec, '', 'DataRelay')[0])

    def test_plan_omits_redundant_ports_but_still_rejects_inconsistent_ports(self):
        spec = listed(width=11)
        plan = {'clock':None, 'temporaries':[], 'states':[],
                'expected':{'published':'incoming'}, 'stimulus':{'mode':'auto'}}
        tb, saved = build_testbench(json.dumps(plan), 'DataRelay', spec)
        self.assertEqual(saved['ports'][0]['width'], 11)
        self.assertIn('DataRelay dut(', tb)
        plan['ports'] = [dict(p) for p in saved['ports']]
        plan['ports'][0]['width'] = 12
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), 'DataRelay', spec)


if __name__ == '__main__':
    unittest.main()
