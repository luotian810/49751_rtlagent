"""主流程：题面 -> RTL -> 独立测试台 -> 工具反馈 -> 有限轮次修复。

阅读顺序建议：main()、solve()、verify()。此模块不读取任务目录里的
tb.sv、ref.sv 或 reference/，生成端只能看到 prompt.txt / interface.txt。
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from enum import IntEnum
import json
import os
from pathlib import Path
import re
import signal
import threading
import time

from .interface import check_interface, extract_verilog, infer_top
from .budget import model_budget
from .diagnosis import DIAGNOSE_FAILURE, failure_observation, parse_diagnosis
from .witness import WITNESS_PROMPT, prepare_witness, parse_witness
from .llm import LLM, LLMError, redact
from .prompts import DESIGN, TESTBENCH, VERIFICATION_PLAN
from .verification_plan import build_testbench, plan_contract, PlanError
from .verification import Toolchain, testbench_tool_error
from .repair import COMPILER_REPAIR, compiler_diagnostic, candidate_fingerprint
from .behavior_plan import BEHAVIOR_PLAN, BehaviorPlanError, needs_behavior_plan, parse_behavior_plan
from .timing_contract import clock_contract, check_clock_contract

ROOT = Path(__file__).resolve().parents[1]


class Evidence(IntEnum):
    """内部候选证据层级，独立于比赛 L0–L3；失败不能冒充功能通过。"""
    INTERFACE = 1
    COMPILED = 2
    ELABORATED = 3
    EXECUTED = 4
    SELFCHECK_PASSED = 5
    SYNTHESIZED = 6


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_solution(path: Path, code: str) -> None:
    """同目录原子替换，超时恰好发生在写入时也不会留下半份 RTL。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(code, encoding="utf-8")
    temporary.replace(path)


class Trace:
    """每次调用立即落盘，超时中断也能查到已完成步骤。"""
    def __init__(self, path: Path):
        self.path = path
        path.write_text("", encoding="utf-8")

    def write(self, tool: str, **fields) -> None:
        event = {"ts": round(time.time(), 3), "tool": tool, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(redact(json.dumps(event, ensure_ascii=False)) + "\n")


def compiler_feedback(log: str) -> str:
    """兼容只传日志的诊断调用；主流程另提供源码位置与前轮诊断。"""
    return compiler_diagnostic(log, "", "compile")["feedback"]


def code_problem(code: str, *, testbench: bool = False) -> str:
    """只运行自包含 HDL；避免模型把脚本或外部文件访问塞入仿真。"""
    prohibited = r"\$system\b|\$fopen\b|\$fwrite\b|\$readmem[hb]\b|\$writemem[hb]\b|`include\b"
    if re.search(prohibited, code):
        return "代码含外部文件/系统调用；本工程仅接受自包含 HDL"
    if not testbench and re.search(r"\$(?:display|write|finish|fatal|stop)\b|RTL_AGENT_(?:PASS|FAIL)", code):
        return "DUT 含测试控制或通过标记，请仅实现可综合硬件"
    if testbench:
        from .interface import without_comments
        names = re.findall(r"\bmodule\s+(\w+)", without_comments(code))
        if names != ["tb"]:
            return "独立测试台必须仅声明 tb，不能重复实现 DUT"
        if "RTL_AGENT_PASS" not in code or "RTL_AGENT_FAIL" not in code:
            return "测试台缺少明确的通过/失败标记"
    return ""


def solve(args, trace: Trace, output: Path) -> dict:
    started = time.monotonic()
    end = started + args.deadline
    reserve = min(5.0, args.deadline / 10)

    def remaining() -> float:
        return max(0.0, end - time.monotonic() - reserve)

    prompt_path = Path(args.input) / "prompt.txt"
    prompt = prompt_path.read_text(encoding="utf-8-sig").strip()
    if not prompt:
        raise ValueError("prompt.txt 不能为空")
    interface_path = Path(args.input) / "interface.txt"
    interface = interface_path.read_text(encoding="utf-8-sig") if interface_path.is_file() else ""
    top = infer_top(prompt, interface)
    task = prompt + ("\n\nExplicit interface:\n" + interface if interface.strip() else "")
    llm, tools = LLM(), Toolchain(args.backend)
    trace.write("start", top=top, llm=llm.describe(), toolchain=tools.describe(), deadline_s=args.deadline)
    rules = (ROOT / "skill" / "rtl_rules.md").read_text(encoding="utf-8")
    verification_rules = (ROOT / "skill" / "verification_rules.md").read_text(encoding="utf-8")
    structured = args.verification_mode == "structured"
    contract = plan_contract(prompt, interface, top)
    sampling_constraint = clock_contract(task, contract.get("ports"))
    if sampling_constraint:
        contract["sampling_constraint"] = sampling_constraint
    design_task = task
    if contract["ports_fixed"]:
        design_task += ("\n\n固定接口契约（从规格可靠提取，设计和修复都必须保持）：\n" +
                       json.dumps({"top": top, "ports": contract["ports"]}, ensure_ascii=False))
    if sampling_constraint:
        design_task += ("\n\n题面明确给出的采样沿约束：\n" +
                        json.dumps(sampling_constraint, ensure_ascii=False))
    trace.write("skills", loaded=["rtl_rules.md", "verification_rules.md"],
                design=["rtl_rules.md"], testbench=["verification_rules.md"],
                verification_mode=args.verification_mode)
    best_code, best_rank, best_round = "", -1, 0
    best_checks: dict = {}
    feedback, previous, tb = "", "", ""
    tb_attempted = False
    # 格式重写和编译修复共享一次机会，避免测试台消耗全部解题预算。
    tb_recovery_used = False
    last_testbench_reply = ""
    diagnosed = False
    latest_finish = ""
    stop_reason = "max_rounds"
    total_tokens_in = total_tokens_out = 0
    seen_candidates: dict[tuple[str, ...], int] = {}
    repair_stage = ""
    previous_diagnostic: dict | None = None
    planning_status = "not_required"

    def testbench_messages(instruction: str = "", **details) -> list[dict]:
        # 原题是规格数据；“只提交 DUT”等原始交付要求不覆盖独立验证角色。
        # 此入口不接收待测 DUT、隐藏测试台或参考实现。
        return [
            {"role": "system", "content": (VERIFICATION_PLAN if structured else TESTBENCH)
             + "\n" + verification_rules + "\n" + instruction},
            {"role": "user", "content": json.dumps({"specification": task,
             **({"contract": contract} if structured else {}), **details}, ensure_ascii=False)},
        ]

    def decode_testbench(text: str) -> tuple[str, str]:
        if structured:
            try:
                candidate, plan = build_testbench(text, top, prompt, interface)
                if sampling_constraint:
                    clock = plan.get("clock")
                    if not isinstance(clock, dict) or any(
                        clock.get(key) != sampling_constraint[key] for key in ("name", "edge")
                    ):
                        raise PlanError("clock 与题面明确采样沿不一致：要求 " +
                                        sampling_constraint["edge"] + " " + sampling_constraint["name"])
                save_json(output / "verification_plan.json", plan)
                return candidate, code_problem(candidate, testbench=True)
            except PlanError as exc:
                return "", str(exc)
        candidate = extract_verilog(text, "tb")
        return candidate, code_problem(candidate, testbench=True) if candidate else "未生成 module tb"

    def call_model(messages: list[dict], purpose: str, round_no: int) -> str:
        nonlocal total_tokens_in, total_tokens_out, latest_finish
        budget = model_budget(purpose, remaining())
        latest_finish = ""
        t0 = time.monotonic()
        try:
            reply = llm.chat(messages, timeout_s=budget.timeout_s, max_tokens=budget.max_tokens)
        except LLMError as exc:
            trace.write("llm", purpose=purpose, round=round_no, rc=1,
                        timeout_s=round(budget.timeout_s, 3), max_tokens=budget.max_tokens,
                        excerpt=str(exc), elapsed_s=round(time.monotonic() - t0, 3))
            raise
        latest_finish = reply.finish
        total_tokens_in += reply.tokens_in
        total_tokens_out += reply.tokens_out
        (output / f"round_{round_no:02d}" / f"{purpose}_reply.txt").write_text(reply.text, encoding="utf-8")
        trace.write("llm", purpose=purpose, round=round_no, rc=0,
                    timeout_s=round(budget.timeout_s, 3), max_tokens=budget.max_tokens,
                    tokens_in=reply.tokens_in, tokens_out=reply.tokens_out,
                    finish=reply.finish, empty_content=not reply.text,
                    elapsed_s=round(time.monotonic() - t0, 3))
        return reply.text

    def request_testbench(purpose: str, round_no: int, instruction: str = "", **details) -> str:
        """三种验证请求共用解析、记录和启用路径；失败时不覆盖已有测试台。"""
        nonlocal tb, last_testbench_reply
        reply = call_model(testbench_messages(instruction, **details), purpose, round_no)
        last_testbench_reply = reply
        candidate, problem = decode_testbench(reply)
        trace.write("check_testbench", round=round_no, rc=1 if problem else 0, excerpt=problem)
        if not problem:
            tb = candidate
            (output / "generated_tb.sv").write_text(tb, encoding="utf-8")
        return problem

    def verify(kind: str, code: str, round_dir: Path, round_no: int):
        work = round_dir / kind
        if kind == "simulate":
            result = tools.simulate(code, tb, top, work, remaining())
        elif kind == "lint":
            # 在请求模型测试台之前检查整个 DUT 层级；默认 lint 仍供旧判题流程使用。
            result = tools.lint(code, top, work, remaining(), elaborate=True)
        else:
            result = getattr(tools, kind)(code, top, work, remaining())
        # 每个工具目录保留原始日志；trace 仅保留摘要，降低下一轮上下文成本。
        work.mkdir(parents=True, exist_ok=True)
        (work / "tool.log").write_text(redact(result.log), encoding="utf-8")
        value = asdict(result)
        value["log"] = redact(value["log"])
        save_json(work / "result.json", value)
        trace.write(kind, round=round_no, status=result.status, backend=result.backend,
                    stage=result.details.get("stage"),
                    elapsed_s=result.elapsed_s, excerpt=redact(result.log[-2000:]))
        return result

    def compilation_feedback(result, code: str, round_dir: Path, round_no: int) -> str:
        nonlocal previous_diagnostic, repair_stage
        repair_stage = result.details.get("stage", "compile")
        diagnostic = compiler_diagnostic(result.log, code, repair_stage, previous_diagnostic)
        previous_diagnostic = diagnostic
        save_json(round_dir / "compiler_diagnostic.json", diagnostic)
        trace.write("compiler_diagnostic", round=round_no, stage=repair_stage,
                    category=diagnostic["category"], repeated=diagnostic["repeated"])
        return diagnostic["feedback"]

    def preserve(code: str, rank: int, round_no: int, checks: dict):
        nonlocal best_code, best_rank, best_round, best_checks
        # 同等级保留先前候选，修复稿必须通过更强验证才能替换。
        # 同一份代码继续验证时及时更新事实，不能隐去后续发现的失败。
        same = code == best_code
        selected = (same and rank >= best_rank) or rank > best_rank
        trace.write("candidate", round=round_no, rank=rank, selected=selected,
                    reason=("same_candidate_evidence" if same else
                            "stronger_evidence" if selected else "keep_previous_evidence"))
        if selected:
            evidence = {**best_checks, **checks} if same else dict(checks)
            best_code, best_rank, best_round, best_checks = code, rank, round_no, evidence
            # 及时保存目前最好的候选，外层服务超时仍可返回它。
            save_solution(output / "solution.v", code)

    # 为明确时序任务先形成状态/事件/输出模型。只用于设计，不传给独立验证；
    # 规划是同一千问的待核对推导，格式合法不构成语义证明。失败不反复恢复。
    if args.planning_mode == "auto" and needs_behavior_plan(prompt):
        planning_status = "budget_skipped"
        if remaining() >= 60:
            (output / "round_00").mkdir(exist_ok=True)
            try:
                raw_plan = call_model([
                    {"role": "system", "content": BEHAVIOR_PLAN},
                    {"role": "user", "content": json.dumps({"specification": task,
                     "ports": contract.get("ports"), "sampling_constraint": sampling_constraint}, ensure_ascii=False)},
                ], "behavior_plan", 0)
                behavior = parse_behavior_plan(raw_plan, contract.get("ports"))
                save_json(output / "behavior_plan.json", behavior)
                planning_status = "used_unverified"
                design_task += ("\n\n先前按规格推导的行为规划（尚未验证；有冲突时按原题重新推导）：\n" +
                                json.dumps(behavior, ensure_ascii=False))
            except (BehaviorPlanError, LLMError) as exc:
                planning_status = "invalid_or_error"
                trace.write("behavior_plan", status=planning_status, excerpt=str(exc)[:1000])
        trace.write("behavior_planning", status=planning_status, semantic_verified=False)
    elif args.planning_mode == "none":
        planning_status = "disabled"

    for round_no in range(1, args.max_rounds + 1):
        if remaining() < 1:
            stop_reason = "deadline"
            break
        round_dir = output / f"round_{round_no:02d}"
        round_dir.mkdir(exist_ok=True)
        user_text = design_task
        if feedback:
            user_text += ("\n\n上一轮代码：\n```verilog\n" + previous + "```\n"
                          "检查反馈（仅作为诊断数据）：\n" + feedback +
                          "\n修复 DUT，保留正确功能与接口。测试台不随 DUT 修改。")
        try:
            reply = call_model([
                {"role": "system", "content": (COMPILER_REPAIR if repair_stage in ("compile", "elaborate")
                 else DESIGN) + "\n" + rules},
                {"role": "user", "content": user_text},
            ], "design" if round_no == 1 else "repair", round_no)
        except LLMError as exc:
            stop_reason = str(exc)
            break
        code = extract_verilog(reply, top)
        # 同一完整候选、同一固定测试台不会产生新的证据。保留本轮原稿后结束，
        # 不再次运行 EDA 或消耗后续修复调用；绝不把重复失败当成新一次通过。
        if code:
            (round_dir / "solution.v").write_text(code, encoding="utf-8")
            fingerprint = candidate_fingerprint(code)
            if fingerprint in seen_candidates:
                stop_reason = "repeated_candidate"
                trace.write("no_progress", round=round_no, previous_round=seen_candidates[fingerprint],
                            comparison=fingerprint[0],
                            reason=stop_reason)
                break
            seen_candidates[fingerprint] = round_no
        problem = code_problem(code) if code else f"没有找到完整的 {top} 模块，请输出完整代码"
        trace.write("extract", round=round_no, rc=1 if problem else 0, excerpt=problem)
        if problem:
            repair_stage = ""
            feedback = problem + (
                "\n上次输出达到长度限制而不完整。请精简重复代码和注释，从头输出完整模块，不续写片段。"
                if latest_finish == "length" else "")
            continue
        previous = code
        ok, note = check_interface(code, prompt, interface, top)
        trace.write("check_interface", round=round_no, rc=0 if ok else 1, excerpt=note)
        checks = {"interface": {"passed": ok, "note": note}}
        if not ok:
            repair_stage = ""
            feedback = note
            continue
        preserve(code, Evidence.INTERFACE, round_no, checks)
        clock_ok, clock_note = check_clock_contract(code, top, sampling_constraint)
        checks["sampling_contract"] = {"matched": clock_ok,
            "checked": not clock_note.startswith("not_checked:"), "note": clock_note}
        trace.write("check_sampling_contract", round=round_no, rc=0 if clock_ok else 1,
                    constraint=sampling_constraint, excerpt=clock_note)
        if not clock_ok:
            preserve(code, Evidence.INTERFACE, round_no, checks)
            repair_stage = ""
            feedback = "采样沿与题面明确约束冲突：\n" + clock_note
            continue
        if remaining() < 1:
            stop_reason = "deadline"
            break
        lint = verify("lint", code, round_dir, round_no)
        checks["lint"] = lint.status
        compiled = lint.status == "passed" or lint.details.get("compile_passed") is True
        checks["compilation"] = "passed" if compiled else lint.status
        checks["elaboration"] = ("passed" if lint.status == "passed" else
                                 lint.status if compiled else "not_run")
        rank = Evidence.ELABORATED if lint.status == "passed" else (
            Evidence.COMPILED if compiled else Evidence.INTERFACE)
        preserve(code, rank, round_no, checks)
        if lint.status != "passed":
            if lint.status in ("unavailable", "error", "timeout"):
                stop_reason = f"lint_{lint.status}"
                break
            feedback = note + "\n" + compilation_feedback(lint, code, round_dir, round_no)
            continue
        repair_stage = ""

        if not tb_attempted and remaining() >= 1:
            # 只读题面，不把 DUT 交给测试模型；固定测试台，防止修复时移动判定标准。
            tb_attempted = True
            try:
                tb_error = request_testbench("independent_testbench", round_no)
                if tb_error:
                    if remaining() >= 20:
                        tb_recovery_used = True
                        tb_error = request_testbench("testbench_format_repair", round_no,
                            ("上次验证计划结构不合格。依据规格、previous_plan_text 与 validation_error，"
                             "只修正有依据的错误字段，再输出完整紧凑JSON；不得输出完整TB或声明语句。"
                             "保留无关的参考算法与边界；不能把未知符号猜成输入/输出。"
                             if structured else
                             "上次回复不完整或格式不合格。仅依据规格，从头输出更紧凑的完整自检查测试台；"
                             "不要续写片段，不要减少参考模型、定向边界或 PASS/FAIL 检查。"),
                            validation_error=tb_error, previous_finish=latest_finish,
                            **({"previous_plan_text": last_testbench_reply[:16000]} if structured else {}),
                        )
                    else:
                        trace.write("testbench_recovery", allowed=False, reason="remaining_budget",
                                    remaining_s=round(remaining(), 3))
                if tb_error:
                    stop_reason = "testbench_invalid: " + tb_error
            except LLMError as exc:
                stop_reason = "testbench_error: " + str(exc)
        if not tb or remaining() < 1:
            if remaining() < 1:
                stop_reason = "deadline"
            break
        sim = verify("simulate", code, round_dir, round_no)
        if (sim.status == "failed" and testbench_tool_error(sim.log)
                and not tb_recovery_used and remaining() >= 20):
            # 测试台尚未正确执行时，允许一次语法修复；不把这类问题反馈为 DUT 错误。
            # 模型仍看不到 DUT，不允许通过修改期望值来处理功能断言失败。
            tb_recovery_used = True
            (output / "generated_tb_before_syntax_repair.sv").write_text(tb, encoding="utf-8")
            try:
                problem = request_testbench("testbench_syntax_repair", round_no,
                    ("只修复验证计划的编译问题，输出完整JSON。保持接口、参考算法和激励检查含义不变。"
                     if structured else "现在只修复测试台的编译/系统任务参数错误。保持参考算法、接口、激励和检查条件不变。"),
                    **({"repair_plan": json.loads((output / "verification_plan.json").read_text(encoding="utf-8"))}
                       if structured else {"repair_testbench": tb}), tool_diagnostics=sim.log[-3000:],
                )
                if not problem:
                    repaired_dir = round_dir / "testbench_syntax_repair"
                    repaired_dir.mkdir(exist_ok=True)
                    sim = verify("simulate", code, repaired_dir, round_no)
            except LLMError as exc:
                stop_reason = "testbench_repair_error: " + str(exc)
                break
        checks["simulation"] = sim.status
        checks["simulation_stage"] = sim.details.get("stage", "unknown")
        # 仅启动进程或等待到超时不是更强的功能证据，必须实际完成检查。
        checked = sim.details.get("simulation_executed") and sim.details.get("assertion_failed")
        sim_rank = Evidence.EXECUTED if checked else Evidence.ELABORATED
        preserve(code, sim_rank, round_no, checks)
        if sim.status != "passed":
            diagnosis_note = ""
            if testbench_tool_error(sim.log):
                stop_reason = "testbench_tool_error"
                break
            if sim.status in ("unavailable", "error", "timeout"):
                stop_reason = f"simulation_{sim.status}"
                break
            # 编译/展开失败与未打印断言的异常退出不是功能失配，不能让模型
            # 根据不存在的采样点归因。明确 DUT 源码错误仍可走编译修复。
            if not (sim.details.get("simulation_executed") and sim.details.get("assertion_failed")):
                if sim.details.get("failure_source") == "dut":
                    feedback = note + "\nDUT 编译/展开诊断：\n" + compilation_feedback(sim, code, round_dir, round_no)
                    continue
                stop_reason = "simulation_" + sim.details.get("stage", "unknown") + "_failed"
                break
            observation = failure_observation(sim.log)
            if not observation:
                stop_reason = "selfcheck_missing_observation"
                break
            repair_observation = {"observed_failure": observation}
            if diagnosed:
                # 上一轮诊断只支持上一采样点的一次修复；失败后不能把它当成
                # 后续所有失配都由 DUT 引起的通行证。
                stop_reason = "selfcheck_repair_failed"
                break
            if round_no < args.max_rounds and not diagnosed:
                # 自建 TB 也可能出错。只诊断一次，证据充分才允许按它修复 DUT；
                # 不通过改期望值或反复生成 TB 把当前答案“测成正确”。
                diagnosed = True
                try:
                    if structured:
                        plan = json.loads((output / "verification_plan.json").read_text(encoding="utf-8"))
                        witness, reason = prepare_witness(plan, sim.log)
                        trace.write("witness_context", round=round_no, available=witness is not None,
                                    reason=reason, samples=len(witness["history"]) if witness else 0)
                        if witness is None:
                            stop_reason = "selfcheck_missing_history"
                            break
                        payload = {"specification": task, **witness}
                        repair_observation.update(sampling=witness["sampling"], history=witness["history"])
                        save_json(round_dir / "witness_request.json", payload)
                        diagnosis = parse_witness(call_model([
                            {"role": "system", "content": WITNESS_PROMPT},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                        ], "failure_diagnosis", round_no), observation, target=witness["target"])
                    else:
                        diagnosis = parse_diagnosis(call_model([
                            {"role": "system", "content": DIAGNOSE_FAILURE},
                            {"role": "user", "content": task + "\nDUT:\n" + code +
                             "\n固定自建测试台:\n" + tb + "\n失败日志:\n" + sim.log[-4000:] +
                             "\nobserved_failure（工具实测）：\n" + json.dumps(observation, ensure_ascii=False)},
                        ], "failure_diagnosis", round_no), failure_log=sim.log)
                except LLMError as exc:
                    stop_reason = "diagnosis_error: " + str(exc)
                    break
                save_json(round_dir / "diagnosis.json", diagnosis)
                trace.write("failure_diagnosis", round=round_no, **diagnosis)
                if diagnosis["verdict"] != "dut_error":
                    stop_reason = "selfcheck_" + diagnosis["verdict"]
                    break
                diagnosis_note = ("\n失败归因：" + diagnosis["reason"] +
                                  "\n题面依据：" + diagnosis["spec_rule"] +
                                  "\n失败激励证据：" + json.dumps(diagnosis["evidence"], ensure_ascii=False))
            # 修复只接收绑定的观测/真实输入历史与规格复核依据。完整 TB 和日志
            # 仍落盘，但不把可能错误的 oracle 算法再次注入 DUT 修复上下文。
            feedback = (note + diagnosis_note + "\n工具观测与采样历史（诊断数据）：\n" +
                        json.dumps(repair_observation, ensure_ascii=False) +
                        "\n按题面修复；独立期望仍可能有误，不能照抄测试台假设。")
            repair_stage = ""
            continue
        preserve(code, Evidence.SELFCHECK_PASSED, round_no, checks)
        if args.synth and remaining() >= 1:
            synth = verify("synth", code, round_dir, round_no)
            checks["synthesis"] = synth.status
            preserve(code, Evidence.SELFCHECK_PASSED, round_no, checks)
            if synth.status == "failed":
                feedback = note + "\n" + synth.log[-4000:]
                continue
            if synth.status == "passed":
                preserve(code, Evidence.SYNTHESIZED, round_no, checks)
            else:
                stop_reason = f"synthesis_{synth.status}"
                break
        stop_reason = "selfcheck_passed"
        break

    summary = {
        "top": top, "model": llm.model, "toolchain": tools.describe(),
        "selected_round": best_round, "checks": best_checks,
        "evidence_level": Evidence(best_rank).name.lower() if best_rank > 0 else "none",
        "selfcheck_passed": best_checks.get("simulation") == "passed",
        "official_evaluation": "not_run", "stop_reason": stop_reason,
        "verification_mode": args.verification_mode,
        "behavior_planning": planning_status,
        "unique_candidates": len(seen_candidates),
        "tokens_in": total_tokens_in, "tokens_out": total_tokens_out,
        "elapsed_s": round(time.monotonic() - started, 3),
        "note": "模型生成的测试台可能漏测或误判；自检通过不等于官方 L2/L3，也不构成功能证明。",
    }
    trace.write("done", **summary)
    return summary


def _cancel(signum, frame):
    raise SystemExit(128 + signum)


def main(argv=None) -> int:
    # 外层比赛服务取消任务时，让工具封装的 finally 有机会终止 EDA 子进程。
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _cancel)
    parser = argparse.ArgumentParser(description="生成可读 RTL，并用独立测试台仿真修复")
    parser.add_argument("--input", required=True, help="包含 prompt.txt 的任务目录")
    parser.add_argument("--output", required=True, help="每次建议使用新的输出目录")
    parser.add_argument("--backend", choices=["auto", "vivado", "modelsim", "iverilog", "none"],
                        default=os.environ.get("RTL_SIMULATOR", "auto"))
    parser.add_argument("--max-rounds", type=int, default=int(os.environ.get("AGENT_MAX_ROUNDS", "3")))
    parser.add_argument("--deadline", type=float, default=float(os.environ.get("AGENT_DEADLINE_S", "900")))
    parser.add_argument("--synth", action="store_true", help="自检成功后额外调用 Vivado 综合")
    parser.add_argument("--verification-mode", choices=["structured", "legacy"], default="structured",
                        help="structured 使用固定调度骨架；legacy 仅用于旧版流程回归对照")
    parser.add_argument("--planning-mode", choices=["auto", "none"], default="none",
                        help="默认 none 在同次设计中核对行为；auto 显式启用历史独立规划流程供对照")
    args = parser.parse_args(argv)
    if args.deadline <= 0 or not 1 <= args.max_rounds <= 10:
        parser.error("deadline 必须大于 0，max-rounds 必须在 1..10")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    trace = Trace(output / "trace.jsonl")
    save_solution(output / "solution.v", "")
    try:
        summary = solve(args, trace, output)
    except Exception as exc:
        # 输入/环境失败仍产出协议要求的文件，绝不伪报检查通过。
        summary = {"selfcheck_passed": False, "official_evaluation": "not_run",
                   "stop_reason": redact(f"{type(exc).__name__}: {exc}")[:500]}
        trace.write("error", **summary)
    save_json(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
