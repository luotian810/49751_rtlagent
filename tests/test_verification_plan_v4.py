"""V4 模板执行与边界测试；受控计划不计为模型泛化成绩。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.llm import Reply
from agent.main import main
from agent.verification import CheckResult, Toolchain
from agent.verification_plan import PlanError, build_testbench


def port(name, direction, width=1, signed=False):
    return {"name": name, "direction": direction, "width": width, "signed": signed}


def combo_plan():
    return {
        "ports": [port("a", "input", 5, True), port("b", "input", 5, True),
                  port("sum", "output", 6, True)],
        "clock": None,
        "async_reset": None,
        "variables": [{"name": "stim_a"}, {"name": "stim_b"}],
        "advance": "",
        "expected": {"sum": "$signed(a) + $signed(b)"},
        "stimulus": ("for (stim_a=0; stim_a<32; stim_a=stim_a+1) "
                     "for (stim_b=0; stim_b<32; stim_b=stim_b+1) step(stim_a,stim_b);"),
    }


COMBO_SPEC = """module SignedAdder(input signed [4:0] a,b, output signed [5:0] sum);
Return the exact signed sum of the two five-bit inputs, without overflow."""
COMBO_DUT = """module SignedAdder(input signed [4:0] a,b, output signed [5:0] sum);
assign sum = $signed(a) + $signed(b);
endmodule
"""


def sequential_plan():
    return {
        "ports": [port("tick", "input"), port("clear_n", "input"),
                  port("gate", "input"), port("data", "input"),
                  port("count", "output", 3), port("parity", "output")],
        "clock": {"name": "tick", "edge": "negedge"},
        "async_reset": {"name": "clear_n", "active": 0},
        "variables": [{"name": "ref_count", "width": 3},
                      {"name": "ref_parity", "width": 1}, {"name": "stim_i"}],
        "advance": ("if (!clear_n) begin ref_count=0; ref_parity=0; end "
                    "else if (gate) begin "
                    "if (old_ref_count == 4) ref_count=0; "
                    "else ref_count=old_ref_count+1; "
                    "ref_parity=old_ref_parity ^ data; end"),
        "expected": {"count": "ref_count", "parity": "ref_parity"},
        "stimulus": ("step(0,0,0); "
                     "for (stim_i=0; stim_i<80; stim_i=stim_i+1) begin "
                     "step(1,1,stim_i%2); step(1,0,1); end "
                     "step(0,1,1); step(1,1,1);"),
    }


SEQUENTIAL_SPEC = """module EdgeCounter(input tick, clear_n, gate, data,
output reg [2:0] count, output reg parity);
On each falling edge of tick, if gate is high, increment count modulo five and
XOR data into parity. With gate low, both outputs hold. clear_n is an active-low
asynchronous reset that immediately clears both outputs, with priority over gate.
"""
SEQUENTIAL_DUT = """module EdgeCounter(input tick, clear_n, gate, data,
output reg [2:0] count, output reg parity);
always @(negedge tick or negedge clear_n) begin
  if (!clear_n) begin count<=0; parity<=0; end
  else if (gate) begin
    if (count==4) count<=0; else count<=count+1;
    parity<=parity ^ data;
  end
end
endmodule
"""


def parity_group_plan():
    return {
        "ports": [port("tick", "input"), port("clear_n", "input"),
                  port("gate", "input"), port("data", "input"),
                  port("parity", "output"), port("valid", "output")],
        "clock": {"name": "tick", "edge": "posedge"},
        "async_reset": {"name": "clear_n", "active": 0},
        "variables": [{"name": "ref_count", "width": 3},
                      {"name": "ref_xor", "width": 1},
                      {"name": "ref_parity", "width": 1},
                      {"name": "ref_valid", "width": 1}, {"name": "stim_i"}],
        "advance": ("if (!clear_n) begin ref_count=0; ref_xor=0; ref_parity=0; ref_valid=0; end "
                    "else begin ref_valid=0; if (gate) begin "
                    "if (old_ref_count==4) begin ref_parity=old_ref_xor ^ data; "
                    "ref_count=0; ref_xor=0; ref_valid=1; end "
                    "else begin ref_count=old_ref_count+1; ref_xor=old_ref_xor ^ data; end "
                    "end end"),
        "expected": {"parity": "ref_parity", "valid": "ref_valid"},
        "stimulus": ("step(0,0,0); "
                     "for (stim_i=0; stim_i<70; stim_i=stim_i+1) begin "
                     "step(1,1,(stim_i%3)==0); step(1,0,1); end"),
    }


PARITY_SPEC = """module GroupParity(input tick, clear_n, gate, data,
output reg parity, output reg valid);
At each rising edge of tick, collect data only if gate is high. After every fifth
accepted bit, parity is the XOR of all five accepted bits including that bit, and
valid is high for that edge only. Begin a fresh group after publishing. Between
groups, parity holds its last published value. valid clears on all other edges,
including pauses. clear_n asynchronously resets all state and outputs low.
"""
PARITY_DUT = """module GroupParity(input tick, clear_n, gate, data,
output reg parity, output reg valid);
reg [2:0] count; reg accum;
always @(posedge tick or negedge clear_n) begin
  if (!clear_n) begin count<=0; accum<=0; parity<=0; valid<=0; end
  else begin
    valid<=0;
    if (gate) begin
      if (count==4) begin
        parity<=accum ^ data; valid<=1; count<=0; accum<=0;
      end else begin count<=count+1; accum<=accum ^ data; end
    end
  end
end
endmodule
"""


def native_parity_group_plan():
    plan = parity_group_plan()
    plan["reset"] = {"name": "clear_n", "active": 0}
    plan["advance"] = {
        "temporary": {},
        "next": {
            "ref_count": "gate ? ((ref_count==4) ? 0 : ref_count+1) : ref_count",
            "ref_xor": "gate ? ((ref_count==4) ? 0 : (ref_xor ^ data)) : ref_xor",
            "ref_parity": "(gate && (ref_count==4)) ? (ref_xor ^ data) : ref_parity",
            "ref_valid": "gate && (ref_count==4)",
        },
        "writes": [],
    }
    plan["stimulus"] = {
        "directed": [{"values": {"clear_n": "0", "gate": "0", "data": "0"}},
                     {"values": {"data": "1", "clear_n": "1", "gate": "1"}, "repeat": 5},
                     {"values": {"clear_n": "1", "gate": "0", "data": "1"}, "repeat": 2}],
        "random": {"cycles": 64, "values": {
            "clear_n": "1", "gate": "(__va_index%3)!=0", "data": "$random(__va_seed)"}},
    }
    return plan


def native_fifo_plan():
    return {
        "ports": [port("clk", "input"), port("rst_n", "input"),
                  port("put", "input"), port("take", "input"), port("word", "input", 3),
                  port("head", "output", 3), port("empty", "output"), port("full", "output")],
        "clock": {"name": "clk", "edge": "posedge"},
        "reset": {"name": "rst_n", "active": 0},
        "async_reset": None,
        "variables": [{"name": "ref_mem", "width": 3, "depth": 2},
                      {"name": "ref_rd", "width": 1}, {"name": "ref_wr", "width": 1},
                      {"name": "ref_count", "width": 2},
                      {"name": "stim_pop", "width": 1}, {"name": "stim_push", "width": 1}],
        "advance": {
            "temporary": {"stim_pop": "take && (ref_count!=0)",
                          "stim_push": "put && ((ref_count<2) || stim_pop)"},
            "next": {"ref_rd": "stim_pop ? (ref_rd ^ 1'b1) : ref_rd",
                     "ref_wr": "stim_push ? (ref_wr ^ 1'b1) : ref_wr",
                     "ref_count": "ref_count + stim_push - stim_pop"},
            "writes": [{"array": "ref_mem", "index": "ref_wr", "value": "word", "when": "stim_push"}],
        },
        "expected": {"head": "(ref_count==0) ? 0 : ref_mem[ref_rd]",
                     "empty": "ref_count==0", "full": "ref_count==2"},
        "stimulus": {
            "directed": [
                {"values": {"rst_n": "0", "put": "0", "take": "0", "word": "0"}},
                {"values": {"word": "1", "take": "0", "put": "1", "rst_n": "1"}},
                {"values": {"rst_n": "1", "put": "1", "take": "0", "word": "6"}},
                {"values": {"rst_n": "1", "put": "1", "take": "1", "word": "3"}},
                {"values": {"rst_n": "1", "put": "0", "take": "1", "word": "0"}, "repeat": 3},
            ],
            "random": {"cycles": 96, "values": {
                "rst_n": "1", "put": "(__va_index%4)!=0", "take": "(__va_index%3)!=0", "word": "__va_index"}},
        },
    }


FIFO_SPEC = """module SmallQueue(input clk, rst_n, put, take, input [2:0] word,
output [2:0] head, output empty, full);
Two-entry FIFO. At a rising clk edge rst_n low synchronously empties the queue.
Otherwise accept a take only if previously nonempty. Accept a put if previously
not full, or if a take is accepted on this same edge. A simultaneous take/put
on a full queue replaces its oldest element and keeps two entries. On an empty
queue a simultaneous put/take stores one element; it does not bypass. head is
the current oldest word or zero when empty; full/empty reflect current occupancy.
"""
FIFO_DUT = """module SmallQueue(input clk, rst_n, put, take, input [2:0] word,
output [2:0] head, output empty, full);
reg [2:0] mem [0:1]; reg rd, wr; reg [1:0] count;
wire pop_ok = take && (count!=0);
wire push_ok = put && ((count<2) || pop_ok);
assign empty=(count==0); assign full=(count==2);
assign head=empty ? 3'd0 : mem[rd];
always @(posedge clk) begin
  if (!rst_n) begin rd<=0; wr<=0; count<=0; end
  else begin
    if(pop_ok) rd<=~rd;
    if(push_ok) begin mem[wr]<=word; wr<=~wr; end
    case ({push_ok,pop_ok})
      2'b10: count<=count+1;
      2'b01: count<=count-1;
      default: count<=count;
    endcase
  end
end
endmodule
"""


class PlanBoundaryTests(unittest.TestCase):
    def test_complete_json_with_or_without_fence_preserves_port_contract(self):
        payload = json.dumps(combo_plan())
        plain_tb, plain = build_testbench(payload, "SignedAdder", COMBO_SPEC)
        fenced_tb, fenced = build_testbench("```json\n" + payload + "\n```", "SignedAdder", COMBO_SPEC)
        self.assertEqual(plain, fenced)
        self.assertEqual(plain_tb, fenced_tb)
        self.assertIn("module tb;", plain_tb)
        self.assertEqual(plain_tb.count("RTL_AGENT_PASS"), 1)

    def test_rejects_missing_outputs_duplicate_ports_and_wrong_contract(self):
        mutations = []
        missing = combo_plan()
        missing["expected"] = {}
        mutations.append(missing)
        duplicate = combo_plan()
        duplicate["ports"].append(copy.deepcopy(duplicate["ports"][0]))
        mutations.append(duplicate)
        wrong_width = combo_plan()
        wrong_width["ports"][0]["width"] = 4
        mutations.append(wrong_width)
        unsupported = combo_plan()
        unsupported["ports"][0]["direction"] = "inout"
        mutations.append(unsupported)
        bad_clock = combo_plan()
        bad_clock["clock"] = {"name": "a", "edge": "posedge"}
        mutations.append(bad_clock)
        for plan in mutations:
            with self.subTest(plan=plan):
                with self.assertRaises(PlanError):
                    build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_model_fragments_cannot_take_over_harness_or_read_outputs(self):
        cases = [
            ("advance", "a=0;"),
            ("advance", "ref_temp=sum;"),
            ("advance", "integer ref_temp; ref_temp=0;"),
            ("advance", "#1;"),
            ("advance", "$finish;"),
            ("advance", "ref_temp=dut.hidden;"),
            ("stimulus", 'step(0,0); $display("RTL_AGENT_PASS");'),
            ("stimulus", "step(a,b);"),
            ("stimulus", "ref_counter=0; step(0,0);"),
        ]
        for field, value in cases:
            plan = combo_plan()
            plan[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(PlanError):
                    build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)
        plan = combo_plan()
        plan["expected"]["sum"] = "sum"
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_reference_initialization_cannot_depend_on_dut_output(self):
        plan = combo_plan()
        plan["variables"].append({"name": "ref_value", "initial": "sum"})
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_incomplete_or_non_object_reply_is_a_plan_error(self):
        for reply in ('{"ports":', '[]', 'module tb; endmodule'):
            with self.subTest(reply=reply):
                with self.assertRaises(PlanError):
                    build_testbench(reply, "SignedAdder", COMBO_SPEC)

    def test_state_update_cannot_reuse_fresh_count_or_accumulator(self):
        for old_state, fresh_state in (("old_ref_count", "ref_count"), ("old_ref_xor", "ref_xor")):
            plan = parity_group_plan()
            plan["advance"] = plan["advance"].replace(old_state, fresh_state)
            with self.subTest(state=fresh_state):
                with self.assertRaises(PlanError):
                    build_testbench(json.dumps(plan), "GroupParity", PARITY_SPEC)

    def test_array_write_index_cannot_hide_a_fresh_reference_state_read(self):
        plan = combo_plan()
        plan["variables"] += [{"name": "ref_count", "width": 2},
                              {"name": "ref_mem", "width": 5, "depth": 4}]
        plan["advance"] = "ref_count=old_ref_count+1; ref_mem[ref_count]=a;"
        with self.assertRaises(PlanError):
            build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)

    def test_data_stimulus_rejects_invalid_arity_counts_and_state_reads(self):
        valid_stimulus = {
            "directed": [{"values": ["0", "0"], "repeat": 2}],
            "random": {"cycles": 64, "values": ["$random(__va_seed)", "__va_index"]},
        }
        invalid = []
        for section in ("directed", "random"):
            stimulus = copy.deepcopy(valid_stimulus)
            if section == "directed":
                stimulus["directed"][0]["values"] = ["0"]
            else:
                stimulus["random"]["values"] = ["0"]
            invalid.append(stimulus)
        for cycles in (63, 257):
            stimulus = copy.deepcopy(valid_stimulus)
            stimulus["random"]["cycles"] = cycles
            invalid.append(stimulus)
        for count in (0, 129):
            stimulus = copy.deepcopy(valid_stimulus)
            stimulus["directed"][0]["repeat"] = count
            invalid.append(stimulus)
        too_many = copy.deepcopy(valid_stimulus)
        too_many["directed"] = [{"values": ["0", "0"]} for _ in range(25)]
        invalid.append(too_many)
        for expression in ("a", "ref_hidden", "stim_i"):
            stimulus = copy.deepcopy(valid_stimulus)
            stimulus["random"]["values"][0] = expression
            invalid.append(stimulus)
        for stimulus in invalid:
            plan = combo_plan()
            plan["stimulus"] = stimulus
            with self.subTest(stimulus=stimulus):
                with self.assertRaises(PlanError):
                    build_testbench(json.dumps(plan), "SignedAdder", COMBO_SPEC)


class PlanExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tools = Toolchain("iverilog")
        if not self.tools.describe()["available"]:
            self.skipTest("Icarus is unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def simulate(self, plan, source, top, specification, tag):
        testbench, _ = build_testbench(json.dumps(plan), top, specification)
        return self.tools.simulate(source, testbench, top, self.root / tag, 30)

    def test_signed_width_oracle_passes_reference_and_rejects_truncation(self):
        good = self.simulate(combo_plan(), COMBO_DUT, "SignedAdder", COMBO_SPEC, "signed-good")
        # The five-bit intermediate loses the carry/sign before six-bit assignment.
        mutant = COMBO_DUT.replace("assign sum = $signed(a) + $signed(b);",
                                  "wire signed [4:0] short_sum = a+b; assign sum=short_sum;")
        bad = self.simulate(combo_plan(), mutant, "SignedAdder", COMBO_SPEC, "signed-mutant")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)
        self.assertIn("RTL_AGENT_FAIL", bad.log)

    def test_negedge_async_reset_and_pause_use_actual_sampling_contract(self):
        good = self.simulate(sequential_plan(), SEQUENTIAL_DUT, "EdgeCounter", SEQUENTIAL_SPEC, "seq-good")
        sync_mutant = SEQUENTIAL_DUT.replace("negedge tick or negedge clear_n", "negedge tick")
        bad = self.simulate(sequential_plan(), sync_mutant, "EdgeCounter", SEQUENTIAL_SPEC, "seq-sync-reset")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)
        self.assertIn("RTL_AGENT_FAIL", bad.log)

    def test_too_few_checks_cannot_emit_a_successful_result(self):
        plan = combo_plan()
        plan["stimulus"] = "step(0,0);"
        result = self.simulate(plan, COMBO_DUT, "SignedAdder", COMBO_SPEC, "too-short")
        self.assertEqual(result.status, "failed", result.log)
        self.assertIn("insufficient_checks", result.log)

    def test_group_boundary_uses_old_state_once_including_current_bit(self):
        good = self.simulate(parity_group_plan(), PARITY_DUT, "GroupParity", PARITY_SPEC, "group-good")
        mutant = PARITY_DUT.replace("parity<=accum ^ data;", "parity<=accum;")
        bad = self.simulate(parity_group_plan(), mutant, "GroupParity", PARITY_SPEC, "group-missing-last-bit")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)
        self.assertIn("RTL_AGENT_FAIL", bad.log)

    def test_data_stimulus_generates_repeats_and_seeded_random_checks(self):
        plan = combo_plan()
        plan["stimulus"] = {
            "directed": [{"values": ["5'd15", "5'd15"], "repeat": 2},
                         {"values": ["5'd16", "5'd31"]}],
            "random": {"cycles": 64, "values": ["$random(__va_seed)", "__va_index"]},
        }
        result = self.simulate(plan, COMBO_DUT, "SignedAdder", COMBO_SPEC, "data-combo")
        self.assertEqual(result.status, "passed", result.log)
        self.assertIn("CHECKS=67", result.log)

    def test_data_stimulus_retains_negedge_and_async_reset_timing(self):
        plan = sequential_plan()
        plan["stimulus"] = {
            "directed": [{"values": ["0", "1", "1"]},
                         {"values": ["1", "1", "1"], "repeat": 5},
                         {"values": ["1", "0", "1"], "repeat": 3}],
            "random": {"cycles": 64,
                       "values": ["1", "(__va_index%3)!=0", "$random(__va_seed)"]},
        }
        good = self.simulate(plan, SEQUENTIAL_DUT, "EdgeCounter", SEQUENTIAL_SPEC, "data-negedge")
        mutant = SEQUENTIAL_DUT.replace("negedge tick or negedge clear_n", "negedge tick")
        bad = self.simulate(plan, mutant, "EdgeCounter", SEQUENTIAL_SPEC, "data-sync-reset")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)

    def test_unknown_actual_or_expected_cannot_pass_when_both_match(self):
        for unknown in ("x", "z"):
            for actual, expected in ((unknown * 6, unknown * 6), (unknown * 6, "000000"),
                                     ("000000", unknown * 6)):
                with self.subTest(actual=actual, expected=expected):
                    plan = combo_plan()
                    plan["expected"]["sum"] = "6'b" + expected
                    dut = COMBO_DUT.replace("$signed(a) + $signed(b)", "6'b" + actual)
                    result = self.simulate(plan, dut, "SignedAdder", COMBO_SPEC,
                                           "unknown-" + actual + "-" + expected)
                    self.assertEqual(result.status, "failed", result.log)
                    self.assertIn("RTL_AGENT_FAIL", result.log)


class StructuredFlowTests(unittest.TestCase):
    def run_flow(self, verification_replies):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        task = root / "task"
        task.mkdir()
        (task / "prompt.txt").write_text(COMBO_SPEC, encoding="utf-8")
        (task / "tb.sv").write_text("HIDDEN_ORACLE_SENTINEL", encoding="utf-8")
        (task / "reference.v").write_text("REFERENCE_ANSWER_SENTINEL", encoding="utf-8")
        dut = COMBO_DUT.replace("assign sum", "/* IMPLEMENTATION_ONLY_SENTINEL */ assign sum")
        passed = CheckResult("passed", "fake", "RTL_AGENT_PASS", 0)
        with patch("agent.main.LLM.chat", side_effect=[Reply(dut), *verification_replies]) as model, \
                patch("agent.main.Toolchain") as constructor, patch("builtins.print"):
            tools = constructor.return_value
            tools.describe.return_value = {"backend": "fake"}
            tools.lint.return_value = passed
            tools.simulate.return_value = passed
            rc = main(["--input", str(task), "--output", str(root / "out"), "--deadline", "120"])
            calls = list(model.call_args_list)
            simulation_count = tools.simulate.call_count
        self.assertEqual(rc, 0)
        out = root / "out"
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (out / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
        return out, summary, events, calls, simulation_count

    def assert_specification_only(self, calls):
        for call in calls[1:]:
            messages = call.args[0]
            self.assertNotIn("IMPLEMENTATION_ONLY_SENTINEL", str(messages))
            self.assertEqual(json.loads(messages[1]["content"])["specification"], COMBO_SPEC.strip())
        self.assertNotIn("HIDDEN_ORACLE_SENTINEL", str(calls))
        self.assertNotIn("REFERENCE_ANSWER_SENTINEL", str(calls))

    def test_default_mode_persists_plan_and_harness_without_leaking_dut(self):
        out, summary, events, calls, simulations = self.run_flow([Reply(json.dumps(combo_plan()))])
        self.assertEqual(summary["verification_mode"], "structured")
        self.assertTrue(summary["selfcheck_passed"])
        self.assertEqual(simulations, 1)
        self.assertTrue((out / "verification_plan.json").is_file())
        self.assertTrue((out / "generated_tb.sv").is_file())
        self.assertEqual([e["purpose"] for e in events if e["tool"] == "llm"],
                         ["design", "independent_testbench"])
        self.assert_specification_only(calls)

    def test_two_invalid_plans_use_one_retry_and_keep_compiled_candidate(self):
        out, summary, events, calls, simulations = self.run_flow([Reply("{bad"), Reply("{bad")])
        self.assertFalse(summary["selfcheck_passed"])
        self.assertTrue(summary["stop_reason"].startswith("testbench_invalid:"))
        self.assertEqual(simulations, 0)
        self.assertIn("IMPLEMENTATION_ONLY_SENTINEL", (out / "solution.v").read_text(encoding="utf-8"))
        self.assertEqual([e["purpose"] for e in events if e["tool"] == "llm"],
                         ["design", "independent_testbench", "testbench_format_repair"])
        self.assert_specification_only(calls)


class NativeTransitionTests(unittest.TestCase):
    setUp = PlanExecutionTests.setUp
    simulate = PlanExecutionTests.simulate

    def test_combinational_temporaries_keep_width_and_named_input_binding(self):
        specification = """module CarrySum(input [5:0] lhs,rhs, input carry_in,
output [5:0] low, output carry_out); Return the exact unsigned sum as carry_out:low."""
        dut = """module CarrySum(input [5:0] lhs,rhs, input carry_in,
output [5:0] low, output carry_out);
assign {carry_out,low} = {1'b0,lhs} + {1'b0,rhs} + carry_in;
endmodule"""
        plan = {
            "ports": [port("lhs", "input", 6), port("rhs", "input", 6),
                      port("carry_in", "input"), port("low", "output", 6), port("carry_out", "output")],
            "clock": None, "reset": None, "async_reset": None,
            "variables": [{"name": "stim_total", "width": 7}],
            "advance": {"temporary": {"stim_total": "{1'b0,lhs} + {1'b0,rhs} + carry_in"},
                        "next": {}, "writes": []},
            "expected": {"low": "stim_total[5:0]", "carry_out": "stim_total[6]"},
            "stimulus": {
                "directed": [{"values": {"carry_in": "1", "rhs": "63", "lhs": "0"}},
                             {"values": {"lhs": "63", "rhs": "63", "carry_in": "1"}}],
                "random": {"cycles": 64, "values": {
                    "rhs": "$random(__va_seed)", "carry_in": "__va_index%2", "lhs": "__va_index"}},
            },
        }
        good = self.simulate(plan, dut, "CarrySum", specification, "native-combo")
        mutant = dut.replace(" + carry_in", "")
        bad = self.simulate(plan, mutant, "CarrySum", specification, "native-combo-no-carry")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)

    def test_native_group_updates_are_simultaneous_and_reset_without_model_statements(self):
        plan = native_parity_group_plan()
        good = self.simulate(plan, PARITY_DUT, "GroupParity", PARITY_SPEC, "native-group")
        mutant = PARITY_DUT.replace("parity<=accum ^ data;", "parity<=accum;")
        bad = self.simulate(plan, mutant, "GroupParity", PARITY_SPEC, "native-group-no-final-bit")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)

    def test_native_array_writes_keep_old_head_and_accept_full_replacement(self):
        plan = native_fifo_plan()
        good = self.simulate(plan, FIFO_DUT, "SmallQueue", FIFO_SPEC, "native-fifo")
        mutant = FIFO_DUT.replace("mem[wr]<=word", "mem[~wr]<=word")
        bad = self.simulate(plan, mutant, "SmallQueue", FIFO_SPEC, "native-fifo-wrong-slot")
        self.assertEqual(good.status, "passed", good.log)
        self.assertEqual(bad.status, "failed", bad.log)

    def test_native_mapping_rejects_unknown_state_targets_and_named_input_mismatches(self):
        malformed = []
        unknown_next = native_fifo_plan()
        unknown_next["advance"]["next"]["ref_missing"] = "0"
        malformed.append(unknown_next)
        array_next = native_fifo_plan()
        array_next["advance"]["next"]["ref_mem"] = "0"
        malformed.append(array_next)
        unknown_array = native_fifo_plan()
        unknown_array["advance"]["writes"][0]["array"] = "ref_missing"
        malformed.append(unknown_array)
        missing_input = native_fifo_plan()
        del missing_input["stimulus"]["random"]["values"]["word"]
        malformed.append(missing_input)
        explicit_clock = native_fifo_plan()
        explicit_clock["stimulus"]["random"]["values"]["clk"] = "0"
        malformed.append(explicit_clock)
        for plan in malformed:
            with self.subTest(plan=plan):
                with self.assertRaises(PlanError):
                    build_testbench(json.dumps(plan), "SmallQueue", FIFO_SPEC)


if __name__ == "__main__":
    unittest.main()
