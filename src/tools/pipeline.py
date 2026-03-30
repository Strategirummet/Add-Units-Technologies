from __future__ import annotations

import pandas as pd

from rules.engine import RuleEngine
from rules.registry import get_rules


def run_pipeline(
    provider_df: pd.DataFrame,
    reference_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    df = provider_df.copy(deep=True)

    engine = RuleEngine(get_rules())
    engine_result = engine.apply(df)

    report = {
        "rule_results": [
            {
                "rule_name": result.rule_name,
                "affected_rows": result.affected_rows,
            }
            for result in engine_result.rule_results
        ]
    }

    return engine_result.df, report