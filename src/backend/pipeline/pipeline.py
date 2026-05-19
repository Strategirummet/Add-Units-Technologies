from __future__ import annotations

import pandas as pd


from backend.pipeline.builders import (
    build_initial_differences_df,
    build_initial_units_added_df,
    build_rule_report_df,
    build_unit_data_diff_df,
)
from backend.pipeline.models import PipelineResult
from backend.pipeline.capacities_context import CapacitiesContextData
from backend.rules.base import PipelineState, RuleContext, ComparisonConfig
from backend.rules.engine import RuleEngine
from backend.rules.registry import get_rules


def run_pipeline(
    unit_data_df,
    capacities_context: CapacitiesContextData,
) -> PipelineResult:
    initial_state = PipelineState(
        unit_data_df=unit_data_df.copy(deep=True),
        differences_df=build_initial_differences_df(),
        units_added_df=build_initial_units_added_df(unit_data_df),
    )

    context = RuleContext(
        capacities_lookup_df=capacities_context.capacities_lookup_df,
        sum_year=capacities_context.sum_year,
        synthetic_commissioning_year=capacities_context.synthetic_commissioning_year,
        comparison_config=ComparisonConfig(
            gap_percent_threshold=0.05,
            skip_synthetic_when_b_is_zero=True,
        ),
    )

    engine = RuleEngine(get_rules())
    engine_result = engine.apply(
        state=initial_state,
        context=context,
    )

    final_state = engine_result.state

    unit_data_processed_df = final_state.unit_data_df
    differences_df = final_state.differences_df
    units_added_df = final_state.units_added_df

    unit_data_diff_df = build_unit_data_diff_df(
        original_df=unit_data_df,
        processed_df=unit_data_processed_df,
    )

    report_df = build_rule_report_df(engine_result.rule_results)

    return PipelineResult(
        unit_data_processed_df=unit_data_processed_df,
        unit_data_diff_df=unit_data_diff_df,
        differences_df=differences_df,
        units_added_df=units_added_df,
        report_df=report_df,
    )
