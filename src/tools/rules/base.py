from dataclasses import dataclass
import pandas as pd


@dataclass
class RuleResult:
    rule_name: str
    affected_rows: int


class DataRule:
    name: str = "unnamed_rule"
    priority: int = 100

    def apply(self, df: pd.DataFrame) -> tuple[pd.DataFrame, RuleResult]:
        raise NotImplementedError