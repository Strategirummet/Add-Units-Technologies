from dataclasses import dataclass
from typing import Iterable

from backend.rules.base import DataRule, PipelineState, RuleContext, RuleResult


@dataclass(frozen=True)
class EngineResult:
    state: PipelineState
    rule_results: list[RuleResult]


class RuleEngine:
    def __init__(self, rules: Iterable[DataRule]) -> None:
        self.rules = sorted(list(rules), key=lambda rule: rule.priority)

    def apply(
        self,
        state: PipelineState,
        context: RuleContext | None = None,
    ) -> EngineResult:
        if context is None:
            context = RuleContext()

        working_state = PipelineState(
            unit_data_df=state.unit_data_df.copy(deep=True),
            differences_df=state.differences_df.copy(deep=True),
            units_added_df=state.units_added_df.copy(deep=True),
        )

        results: list[RuleResult] = []

        for rule in self.rules:
            result = rule.apply(working_state, context)
            results.append(result)

        return EngineResult(
            state=working_state,
            rule_results=results,
        )