from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from backend.rules.base import DataRule, PipelineState, RuleContext, RuleResult


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(pd.NA, index=df.index, dtype="object")


def _count_changed(before: pd.Series, after: pd.Series) -> int:
    before_cmp = before.astype("object").where(before.notna(), "__NA__")
    after_cmp = after.astype("object").where(after.notna(), "__NA__")
    return int((before_cmp != after_cmp).sum())


@dataclass(frozen=True)
class StatusFallback:
    commissioning_year: int | None = None
    decommissioning_year: int | None = None


class ResolveLifecycle(DataRule):
    name = "resolve_lifecycle"
    priority = 1

    COMMISSIONING_COLUMN: Final[str] = "Year of commissioning"
    DECOMMISSIONING_COLUMN: Final[str] = "Year of decommissioning"
    UNIT_STATUS_COLUMN: Final[str] = "Unit status"

    VALIDATION_ERROR_COLUMN: Final[str] = "LifecycleValidationError"
    VALIDATION_MESSAGE_COLUMN: Final[str] = "LifecycleValidationMessage"

    YEAR_GAP: Final[int] = 20
    MIN_YEAR: Final[int] = 1500
    MAX_YEAR: Final[int] = 2500

    DEFAULT_STATUS_FALLBACK: Final[StatusFallback] = StatusFallback(
        commissioning_year=2025,
        decommissioning_year=None,
    )

    DEFAULT_FALLBACK_STATUSES: Final[set[str]] = {
        "Authorized",
        "Bidding process",
        "Announced",
        "FID",
        "PPA signed",
        "Under construction",
    }

    STATUS_FALLBACKS: Final[dict[str, StatusFallback]] = {
        "Stopped": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Cancelled": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Mothballed": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Frozen": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Suspended construction": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Operational": StatusFallback(commissioning_year=2010, decommissioning_year=None),
        "Submitted": StatusFallback(commissioning_year=2010, decommissioning_year=None),
        "Synchronized": StatusFallback(commissioning_year=2010, decommissioning_year=None),
    }

    def apply(
        self,
        state: PipelineState,
        context: RuleContext,
    ) -> RuleResult:
        df = state.unit_data_df

        before_commissioning = _safe_series(df, self.COMMISSIONING_COLUMN).copy()
        before_decommissioning = _safe_series(df, self.DECOMMISSIONING_COLUMN).copy()

        df[self.COMMISSIONING_COLUMN] = _safe_series(df, self.COMMISSIONING_COLUMN)
        df[self.DECOMMISSIONING_COLUMN] = _safe_series(df, self.DECOMMISSIONING_COLUMN)

        total_affected = 0

        total_affected += self._fill_commissioning_from_decommissioning(df)
        total_affected += self._fill_from_unit_status(df)
        total_affected += self._fill_commissioning_from_decommissioning(df)
        total_affected += self._add_validation_columns(df)

        total_affected += _count_changed(before_commissioning, df[self.COMMISSIONING_COLUMN])
        total_affected += _count_changed(before_decommissioning, df[self.DECOMMISSIONING_COLUMN])

        return RuleResult(rule_name=self.name, affected_rows=total_affected)

    def _fill_commissioning_from_decommissioning(self, df: pd.DataFrame) -> int:
        commissioning_num = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")
        decommissioning_num = pd.to_numeric(df[self.DECOMMISSIONING_COLUMN], errors="coerce")

        mask = commissioning_num.isna() & decommissioning_num.notna()

        affected = int(mask.sum())
        if affected:
            # Keep values simple; let pandas store them naturally in the existing column dtype
            df.loc[mask, self.COMMISSIONING_COLUMN] = decommissioning_num.loc[mask] - self.YEAR_GAP

        return affected

    def _get_fallback_for_status(self, status_value: str) -> StatusFallback | None:
        if status_value in self.STATUS_FALLBACKS:
            return self.STATUS_FALLBACKS[status_value]

        if status_value in self.DEFAULT_FALLBACK_STATUSES:
            return self.DEFAULT_STATUS_FALLBACK

        return None

    def _fill_from_unit_status(self, df: pd.DataFrame) -> int:
        status_series = _safe_series(df, self.UNIT_STATUS_COLUMN).astype("string").str.strip()
        commissioning_num = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")
        decommissioning_num = pd.to_numeric(df[self.DECOMMISSIONING_COLUMN], errors="coerce")

        affected = 0

        unique_statuses = status_series.dropna().unique()

        for status_value in unique_statuses:
            fallback = self._get_fallback_for_status(status_value)
            if fallback is None:
                continue

            status_mask = status_series.eq(status_value)

            if fallback.commissioning_year is not None:
                commissioning_mask = status_mask & commissioning_num.isna()
                count = int(commissioning_mask.sum())
                if count:
                    df.loc[commissioning_mask, self.COMMISSIONING_COLUMN] = fallback.commissioning_year
                    commissioning_num = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")
                    affected += count

            if fallback.decommissioning_year is not None:
                decommissioning_mask = status_mask & decommissioning_num.isna()
                count = int(decommissioning_mask.sum())
                if count:
                    df.loc[decommissioning_mask, self.DECOMMISSIONING_COLUMN] = fallback.decommissioning_year
                    decommissioning_num = pd.to_numeric(df[self.DECOMMISSIONING_COLUMN], errors="coerce")
                    affected += count

        return affected

    def _add_validation_columns(self, df: pd.DataFrame) -> int:
        commissioning = pd.to_numeric(df[self.COMMISSIONING_COLUMN], errors="coerce")
        decommissioning = pd.to_numeric(df[self.DECOMMISSIONING_COLUMN], errors="coerce")

        invalid_order_mask = (
            commissioning.notna()
            & decommissioning.notna()
            & (commissioning > decommissioning)
        )

        invalid_commissioning_mask = (
            commissioning.notna()
            & ((commissioning < self.MIN_YEAR) | (commissioning > self.MAX_YEAR))
        )

        invalid_decommissioning_mask = (
            decommissioning.notna()
            & ((decommissioning < self.MIN_YEAR) | (decommissioning > self.MAX_YEAR))
        )

        any_error_mask = (
            invalid_order_mask
            | invalid_commissioning_mask
            | invalid_decommissioning_mask
        )

        old_error = _safe_series(df, self.VALIDATION_ERROR_COLUMN).copy()
        old_message = _safe_series(df, self.VALIDATION_MESSAGE_COLUMN).copy()

        df[self.VALIDATION_ERROR_COLUMN] = any_error_mask

        messages = pd.Series("", index=df.index, dtype="string")

        messages.loc[invalid_order_mask] = (
            messages.loc[invalid_order_mask] + "Commissioning year is after decommissioning year; "
        )
        messages.loc[invalid_commissioning_mask] = (
            messages.loc[invalid_commissioning_mask] + "Commissioning year outside valid range; "
        )
        messages.loc[invalid_decommissioning_mask] = (
            messages.loc[invalid_decommissioning_mask] + "Decommissioning year outside valid range; "
        )

        df[self.VALIDATION_MESSAGE_COLUMN] = messages.str.strip().str.rstrip(";")

        affected = (
            _count_changed(old_error, df[self.VALIDATION_ERROR_COLUMN]) +
            _count_changed(old_message, df[self.VALIDATION_MESSAGE_COLUMN])
        )

        return affected