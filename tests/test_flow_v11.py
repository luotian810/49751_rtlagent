"""Default flow is one design call followed by independent checking."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.llm import Reply
from agent.main import main
from agent.verification import CheckResult
from tests.test_flow_v10 import SPEC, DUT, TB, PASS
from tests import test_flow_v9 as v9
from tests.test_iteration_v7 import COMBO_LOG, witness_reply
from tests.test_verification_plan_v4 import COMBO_DUT
from tests.test_verification_plan_v5 import signed_plan


class V11DefaultFlowTests(unittest.TestCase):
    def test_default_sequential_design_uses_no_separate_planning_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); task=root/'task'; task.mkdir(); out=root/'out'
            (task/'prompt.txt').write_text(SPEC,encoding='utf-8')
            (task/'ref.sv').write_text('HIDDEN_REFERENCE',encoding='utf-8')
            with patch('agent.main.LLM.chat',side_effect=[Reply(DUT),Reply(TB)]) as model, \
                    patch('agent.main.Toolchain') as constructor, patch('builtins.print'):
                tools=constructor.return_value; tools.describe.return_value={'backend':'fake'}
                tools.lint.return_value=PASS
                tools.simulate.return_value=CheckResult('passed','fake','RTL_AGENT_PASS',0)
                main(['--input',str(task),'--output',str(out),'--deadline','240','--verification-mode','legacy'])
            summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
            events=[json.loads(line) for line in (out/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(summary['selfcheck_passed'])
            self.assertEqual(summary['behavior_planning'],'disabled')
            self.assertEqual([e['purpose'] for e in events if e['tool']=='llm'],['design','independent_testbench'])
            self.assertFalse((out/'round_00').exists())
            self.assertNotIn(DUT,model.call_args_list[1].args[0][1]['content'])
            self.assertNotIn('HIDDEN_REFERENCE',str(model.call_args_list))

    def test_unknown_output_witness_can_gate_one_repair_without_exposing_actual(self):
        # Controlled replies test plumbing, not Qwen capability.
        runner=v9.V9FlowTests(methodName='test_repair_gets_bound_history_and_rule_but_no_oracle_algorithm')
        self.addCleanup(runner.doCleanups)
        wrong=COMBO_DUT.replace('$signed(a) + $signed(b)',"6'bxxxxxx")
        failed=CheckResult('failed','fake',COMBO_LOG.replace('sum=00','sum=xx'),0,
                           {'simulation_executed':True,'assertion_failed':True,'stage':'simulate'})
        out,summary,calls=runner.run_flow([Reply(wrong),Reply(json.dumps(signed_plan())),
                                         Reply(witness_reply()),Reply(COMBO_DUT)],
                                        [failed,CheckResult('passed','fake','RTL_AGENT_PASS',0)])
        self.assertTrue(summary['selfcheck_passed'])
        self.assertEqual(len(calls),4)
        payload=json.loads(calls[2].args[0][1]['content'])
        self.assertEqual(payload['target']['output']['width'],6)
        for private in ('sum=xx','stim_total','observed','testbench_expected'):
            self.assertNotIn(private,json.dumps(payload))
        self.assertEqual(json.loads((out/'round_01/diagnosis.json').read_text(encoding='utf-8'))['verdict'],'dut_error')


if __name__ == '__main__':
    unittest.main()
