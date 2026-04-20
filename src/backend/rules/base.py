from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class RuleResult:
    rule_name: str
    affected_rows: int


@dataclass
class PipelineState:
    unit_data_df: pd.DataFrame
    differences_df: pd.DataFrame
    units_added_df: pd.DataFrame


@dataclass(frozen=True)
class ComparisonConfig:
    # Add synthetic unit only if missing gap is above this threshold.
    gap_percent_threshold: float = 0.05

    # If reference capacity B is 0, skip synthetic-unit logic.
    skip_synthetic_when_b_is_zero: bool = True


@dataclass(frozen=True)
class RuleContext:
    # Flattened lookup from capacities file.
    capacities_lookup_df: pd.DataFrame | None = None

    # Excel B cell B1.
    sum_year: int | None = None

    # Excel B cell D1.
    synthetic_commissioning_year: int | None = None

    # Rule config for comparison logic.
    comparison_config: ComparisonConfig = ComparisonConfig()


class DataRule:
    name: str = "unnamed_rule"
    priority: int = 100

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        raise NotImplementedError
