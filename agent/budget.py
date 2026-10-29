"""按调用用途分配剩余时间，让验证和修复有机会完成。

这里是单次调用上限，不是固定占用：模型提前返回的时间会留给后续步骤。
总预算仍由 run.sh / 服务传入；官方 baseline 不使用这些策略。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CallBudget:
    timeout_s: float
    max_tokens: int


def model_budget(purpose: str, remaining_s: float) -> CallBudget:
    # (可用时间占比，单次秒数上限，输出 token 上限)
    policies = {
        "behavior_plan": (0.15, 30.0, 1536),
        "design": (0.50, 360.0, 8192),
        "repair": (0.65, 360.0, 8192),
        "independent_testbench": (0.45, 120.0, 3072),
        "testbench_format_repair": (0.25, 60.0, 3072),
        "testbench_syntax_repair": (0.35, 90.0, 3072),
        "failure_diagnosis": (0.20, 45.0, 768),
    }
    fraction, maximum, tokens = policies[purpose]
    return CallBudget(min(maximum, max(0.0, remaining_s) * fraction), tokens)
