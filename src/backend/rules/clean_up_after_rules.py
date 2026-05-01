from typing import Final

import pandas as pd

from backend.rules.base import DataRule, PipelineState, RuleContext, RuleResult

"""
This module contains rules that clean up the data by removing internal columns that are not needed for comparison or output. 
These columns may have been added during the data processing steps and are not relevant for the final output or comparison results.
"""


class RemoveInternalColumns(DataRule):
    name = "remove_internal_columns"
    priority = 9999

    INTERNAL_COLUMNS: Final[list[str]] = [
        "LifecycleValidationError",
        "LifecycleValidationMessage",
        "_is_eligible_for_comparison",
        "_excel_b_bucket",
        "_synthetic_category",
        "_synthetic_energy_1",
        "_synthetic_technology",
        "_synthetic_name_template",
        "IsAdded",
    ]

    def apply(self, state: PipelineState, context: RuleContext) -> RuleResult:
        affected = 0

        for df_attr in ["unit_data_df"]:
            df = getattr(state, df_attr)

            columns_to_drop = [
                col for col in self.INTERNAL_COLUMNS if col in df.columns
            ]

            if columns_to_drop:
                df.drop(columns=columns_to_drop, inplace=True)
                affected += len(columns_to_drop)

        return RuleResult(rule_name=self.name, affected_rows=affected)
