from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from rules.base import DataRule, RuleResult


@dataclass
class EngineResult:
    df: pd.DataFrame
    rule_results: list[RuleResult]


class RuleEngine:
    def __init__(self, rules: Iterable[DataRule]) -> None:
        self.rules = sorted(list(rules), key=lambda rule: rule.priority)

    def apply(self, df: pd.DataFrame) -> EngineResult:
        """
        Run all rules once, in priority order.
        """
        working_df = df.copy(deep=True)
        results: list[RuleResult] = []

        for rule in self.rules:
            working_df, result = rule.apply(working_df)
            results.append(result)

        return EngineResult(
            df=working_df,
            rule_results=results,
        )