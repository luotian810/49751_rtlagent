"""V10 planning/timing flow controls; controlled replies are not Qwen results."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.llm import LLMError, Reply
from agent.main import main
from agent.verification import CheckResult, Toolchain
from agent.verification_plan import build_testbench


SPEC = ('module EdgeUnit(input strobe, input clear, input incoming, output emitted);\n'
        'All state updates on the falling edge of strobe. clear is active high asynchronous reset. '
        'On reset emitted is zero, otherwise store incoming.')
DUT = ('module EdgeUnit(input strobe, input clear, input incoming, output reg emitted);\n'
       'always @(negedge strobe or posedge clear) if(clear) emitted<=0; else emitted<=incoming;\nendmodule')
TB = 'module tb; initial $display("RTL_AGENT_PASS"); // RTL_AGENT_FAIL\nendmodule'
PLAN = {'states':[{'name':'held','meaning':'PLAN_ONLY_SENTINEL: last accepted input','reset':'zero'}],
        'events':[{'when':'reset','next':'held becomes zero','outputs':'publish zero'},
                  {'when':'active sampling edge without reset','next':'accept incoming','outputs':'publish new held'}],
        'outputs':{'emitted':{'kind':'registered','rule':'publish after the sampling edge'}}}
PASS = CheckResult('passed','fake','',0,{'stage':'elaborate','compile_passed':True})


def reference_plan(edge='negedge'):
    return {'clock':{'name':'strobe','edge':edge},
            'reset':{'name':'clear','active':1}, 'async_reset':{'name':'clear','active':1},
            'temporaries':[],
            'states':[{'name':'ref_held','width':1,'signed':False,'initial':"1'b0",'next':'incoming'}],
            'expected':{'emitted':'ref_held'}, 'stimulus':{'mode':'auto'}}


class V10FlowTests(unittest.TestCase):
    def run_flow(self, replies, *, deadline=240, mode='auto', verification='legacy'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        task, output = root/'task', root/'out'
        task.mkdir()
        (task/'prompt.txt').write_text(SPEC,encoding='utf-8')
        (task/'ref.sv').write_text('HIDDEN_REFERENCE_SENTINEL',encoding='utf-8')
        (task/'tb.sv').write_text('HIDDEN_TESTBENCH_SENTINEL',encoding='utf-8')
        with patch('agent.main.LLM.chat',side_effect=replies) as model, patch('agent.main.Toolchain') as constructor, patch('builtins.print'):
            tools = constructor.return_value
            tools.describe.return_value = {'backend':'fake'}
            tools.lint.return_value = PASS
            tools.simulate.return_value = CheckResult('passed','fake','RTL_AGENT_PASS',0)
            self.assertEqual(main(['--input',str(task),'--output',str(output),
                '--verification-mode',verification,'--deadline',str(deadline),'--planning-mode',mode]),0)
            lint_calls, sim_calls = tools.lint.call_args_list, tools.simulate.call_args_list
        summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
        events = [json.loads(line) for line in (output/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
        return output, summary, model.call_args_list, lint_calls, sim_calls, events

    def test_plan_precedes_design_and_never_enters_independent_testbench(self):
        out, summary, calls, lint, sim, events = self.run_flow([Reply(json.dumps(PLAN)),Reply(DUT),Reply(TB)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['behavior_planning'],'used_unverified')
        self.assertEqual(len(calls),3)
        self.assertLessEqual(calls[0].kwargs['max_tokens'],1536)
        self.assertLessEqual(calls[0].kwargs['timeout_s'],30)
        self.assertNotIn('PLAN_ONLY_SENTINEL',calls[0].args[0][1]['content'])
        self.assertIn('PLAN_ONLY_SENTINEL',calls[1].args[0][1]['content'])
        self.assertNotIn('PLAN_ONLY_SENTINEL',str(calls[2].args[0]))
        self.assertNotIn(DUT,str(calls[0].args[0]))
        for call in calls:
            self.assertNotIn('HIDDEN_',str(call.args[0]))
        self.assertEqual([event['purpose'] for event in events if event['tool']=='llm'],
                         ['behavior_plan','design','independent_testbench'])
        self.assertTrue((out/'round_00/behavior_plan_reply.txt').is_file())
        self.assertTrue((out/'behavior_plan.json').is_file())

    def test_malformed_plan_falls_back_without_format_repair(self):
        _, summary, calls, _, _, events = self.run_flow([Reply('not JSON'),Reply(DUT),Reply(TB)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['behavior_planning'],'invalid_or_error')
        self.assertEqual(len(calls),3)
        self.assertFalse(any(e.get('purpose')=='testbench_format_repair' for e in events))

    def test_planner_service_error_does_not_discard_first_design_opportunity(self):
        _, summary, calls, _, _, _ = self.run_flow([LLMError('controlled planner error'),Reply(DUT),Reply(TB)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['behavior_planning'],'invalid_or_error')
        self.assertEqual(len(calls),3)

    def test_small_budget_skips_plan_and_preserves_design_budget(self):
        _, summary, calls, _, _, _ = self.run_flow([Reply(DUT),Reply(TB)],deadline=45)
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['behavior_planning'],'budget_skipped')
        self.assertEqual(len(calls),2)

    def test_explicit_opt_out_keeps_comparison_flow(self):
        _, summary, calls, _, _, _ = self.run_flow([Reply(DUT),Reply(TB)],mode='none')
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['behavior_planning'],'disabled')
        self.assertEqual(len(calls),2)

    def test_wrong_edge_is_repaired_before_eda_or_testbench(self):
        wrong = DUT.replace('negedge strobe','posedge strobe')
        out, summary, calls, lint, sim, events = self.run_flow(
            [Reply(json.dumps(PLAN)),Reply(wrong),Reply(DUT),Reply(TB)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(summary['selected_round'],2)
        self.assertEqual(len(lint),1)
        self.assertEqual(lint[0].args[0],DUT+'\n')
        self.assertEqual(len(sim),1)
        self.assertIn('negedge',calls[2].args[0][1]['content'])
        self.assertFalse((out/'round_01/lint').exists())
        checks = [e for e in events if e['tool']=='check_sampling_contract']
        self.assertEqual([e['rc'] for e in checks],[1,0])
        self.assertTrue(summary['checks']['sampling_contract']['checked'])

    def test_independent_plan_cannot_override_specified_sampling_edge(self):
        out, summary, calls, _, sim, events = self.run_flow(
            [Reply(DUT),Reply(json.dumps(reference_plan('posedge'))),
             Reply(json.dumps(reference_plan()))],mode='none',verification='structured')
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual([e['rc'] for e in events if e['tool']=='check_testbench'],[1,0])
        self.assertEqual(len(sim),1)
        saved = json.loads((out/'verification_plan.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['clock'],{'name':'strobe','edge':'negedge'})
        self.assertIn('采样沿不一致',str(calls[2].args[0]))
        self.assertNotIn(DUT,str(calls[2].args[0]))


class ClockExecutionTests(unittest.TestCase):
    def test_real_reference_and_wrong_edge_have_different_results(self):
        tb, _ = build_testbench(json.dumps(reference_plan()),'EdgeUnit',SPEC)
        with tempfile.TemporaryDirectory() as temp:
            tools = Toolchain('iverilog')
            good = tools.simulate(DUT,tb,'EdgeUnit',Path(temp)/'correct',15)
            bad = tools.simulate(DUT.replace('negedge strobe','posedge strobe'),
                                 tb,'EdgeUnit',Path(temp)/'wrong_edge',15)
        self.assertEqual(good.status,'passed',good.log)
        self.assertEqual(bad.status,'failed',bad.log)
        self.assertIn('RTL_AGENT_FAIL',bad.log)


if __name__ == '__main__':
    unittest.main()
