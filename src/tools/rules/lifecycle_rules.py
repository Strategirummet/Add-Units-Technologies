from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

from rules.base import DataRule, RuleResult


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    """
    Return the column if it exists, otherwise an NA-filled series aligned to df.index.
    """
    if column in df.columns:
        return df[column]
    return pd.Series(pd.NA, index=df.index, dtype="object")


def _to_year_series(series: pd.Series) -> pd.Series:
    """
    Convert mixed values to nullable integer years.

    Examples:
    - '20-09-2025' -> 2025
    - '2025-09-20' -> 2025
    - '2025' -> 2025
    - invalid / blank -> <NA>
    """
    if series.empty:
        return pd.Series(dtype="Int64")

    as_string = series.astype("string").str.strip()

    parsed_dates = pd.to_datetime(as_string, errors="coerce", dayfirst=True)
    years_from_dates = parsed_dates.dt.year.astype("Int64")

    numeric_years = pd.to_numeric(as_string, errors="coerce").astype("Int64")

    result = years_from_dates.combine_first(numeric_years)
    result = result.where((result >= 1800) & (result <= 2300), pd.NA)

    return result.astype("Int64")


def _count_changed(before: pd.Series, after: pd.Series) -> int:
    """
    Count changed values, treating NA == NA.
    """
    before_cmp = before.astype("object").where(before.notna(), "__NA__")
    after_cmp = after.astype("object").where(after.notna(), "__NA__")
    return int((before_cmp != after_cmp).sum())


@dataclass(frozen=True)
class StatusFallback:
    commissioning_year: int | None = None
    decommissioning_year: int | None = None


class ResolveLifecycle(DataRule):
    """
    Resolve lifecycle values in one ordered rule.

    Order:
    1. Normalize commissioning/decommissioning to year-only
    2. Fill commissioning from decommissioning - YEAR_GAP
    3. Fill from UnitStatus fallbacks
    4. Re-run commissioning fill, because UnitStatus may have filled decommissioning
    5. Add validation helper columns

    Important:
    - Never infer decommissioning from commissioning
    - None in a fallback means: leave that column unchanged
    """
    name = "resolve_lifecycle"
    priority = 10

    COMMISSIONING_COLUMN: Final[str] = "Date of Commissioning from"
    DECOMMISSIONING_COLUMN: Final[str] = "Date of Decommissioning from"
    UNIT_STATUS_COLUMN: Final[str] = "Unit status"

    VALIDATION_ERROR_COLUMN: Final[str] = "LifecycleValidationError"
    VALIDATION_MESSAGE_COLUMN: Final[str] = "LifecycleValidationMessage"

    YEAR_GAP: Final[int] = 20
    MIN_YEAR: Final[int] = 1500
    MAX_YEAR: Final[int] = 2500

    # Default fallback for the common statuses
    DEFAULT_STATUS_FALLBACK: Final[StatusFallback] = StatusFallback(
        commissioning_year=2025,
        decommissioning_year=None,
    )

    # These statuses use the default fallback above
    DEFAULT_FALLBACK_STATUSES: Final[set[str]] = {
        "Authorized",
        "Bidding process",
        "Announced",
        "FID",
        "PPA signed",
        "Under construction",
    }

    # Specific overrides
    STATUS_FALLBACKS: Final[dict[str, StatusFallback]] = {
        "Stopped": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Cancelled": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Mothballed": StatusFallback(commissioning_year=1990, decommissioning_year=None),
        "Frozen": StatusFallback(commissioning_year=1990, decommissioning_year=None),  
        "Suspended construction": StatusFallback(commissioning_year=1990, decommissioning_year=None), 
        "Operating": StatusFallback(commissioning_year=2010, decommissioning_year=None),
        "Submitted": StatusFallback(commissioning_year=2010, decommissioning_year=None),
        "Synchronized": StatusFallback(commissioning_year=2010, decommissioning_year=None),
    }

    def apply(self, df: pd.DataFrame) -> tuple[pd.DataFrame, RuleResult]:
        df = df.copy()

        before_commissioning = _safe_series(df, self.COMMISSIONING_COLUMN)
        before_decommissioning = _safe_series(df, self.DECOMMISSIONING_COLUMN)

        # Ensure both columns exist
        df[self.COMMISSIONING_COLUMN] = _safe_series(df, self.COMMISSIONING_COLUMN)
        df[self.DECOMMISSIONING_COLUMN] = _safe_series(df, self.DECOMMISSIONING_COLUMN)

        # 1. Normalize date-like values to year-only
        df[self.COMMISSIONING_COLUMN] = _to_year_series(df[self.COMMISSIONING_COLUMN])
        df[self.DECOMMISSIONING_COLUMN] = _to_year_series(df[self.DECOMMISSIONING_COLUMN])

        total_affected = (
            _count_changed(before_commissioning, df[self.COMMISSIONING_COLUMN]) +
            _count_changed(before_decommissioning, df[self.DECOMMISSIONING_COLUMN])
        )

        # 2. Fill commissioning from decommissioning - 20
        total_affected += self._fill_commissioning_from_decommissioning(df)

        # 3. Fill remaining missing values from UnitStatus
        total_affected += self._fill_from_unit_status(df)

        # 4. Re-run one-way inference because UnitStatus may have filled decommissioning
        total_affected += self._fill_commissioning_from_decommissioning(df)

        # 5. Validation flags
        total_affected += self._add_validation_columns(df)

        # Final stable dtypes
        df[self.COMMISSIONING_COLUMN] = pd.to_numeric(
            df[self.COMMISSIONING_COLUMN], errors="coerce"
        ).astype("Int64")

        df[self.DECOMMISSIONING_COLUMN] = pd.to_numeric(
            df[self.DECOMMISSIONING_COLUMN], errors="coerce"
        ).astype("Int64")

        return df, RuleResult(rule_name=self.name, affected_rows=total_affected)

    def _fill_commissioning_from_decommissioning(self, df: pd.DataFrame) -> int:
        mask = (
            df[self.COMMISSIONING_COLUMN].isna()
            & df[self.DECOMMISSIONING_COLUMN].notna()
        )

        affected = int(mask.sum())
        if affected:
            df.loc[mask, self.COMMISSIONING_COLUMN] = (
                df.loc[mask, self.DECOMMISSIONING_COLUMN] - self.YEAR_GAP
            )

        return affected

    def _get_fallback_for_status(self, status_value: str) -> StatusFallback | None:
        """
        Return the override fallback if it exists.
        Otherwise return the default fallback if the status is in the allowed default set.
        Otherwise return None.
        """
        if status_value in self.STATUS_FALLBACKS:
            return self.STATUS_FALLBACKS[status_value]

        if status_value in self.DEFAULT_FALLBACK_STATUSES:
            return self.DEFAULT_STATUS_FALLBACK

        return None

    def _fill_from_unit_status(self, df: pd.DataFrame) -> int:
        status_series = _safe_series(df, self.UNIT_STATUS_COLUMN).astype("string").str.strip()
        affected = 0

        unique_statuses = status_series.dropna().unique()

        for status_value in unique_statuses:
            fallback = self._get_fallback_for_status(status_value)
            if fallback is None:
                continue

            status_mask = status_series.eq(status_value)

            if fallback.commissioning_year is not None:
                commissioning_mask = (
                    status_mask
                    & df[self.COMMISSIONING_COLUMN].isna()
                )
                count = int(commissioning_mask.sum())
                if count:
                    df.loc[commissioning_mask, self.COMMISSIONING_COLUMN] = fallback.commissioning_year
                    affected += count

            if fallback.decommissioning_year is not None:
                decommissioning_mask = (
                    status_mask
                    & df[self.DECOMMISSIONING_COLUMN].isna()
                )
                count = int(decommissioning_mask.sum())
                if count:
                    df.loc[decommissioning_mask, self.DECOMMISSIONING_COLUMN] = fallback.decommissioning_year
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

        old_error = _safe_series(df, self.VALIDATION_ERROR_COLUMN)
        old_message = _safe_series(df, self.VALIDATION_MESSAGE_COLUMN)

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