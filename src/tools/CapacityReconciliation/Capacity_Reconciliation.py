from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import pandas as pd


# ==============================
# Configuration & Defaults
# ==============================

CAPACITY_COLUMN_INDEX_DEFAULT = 19  # Excel col T (0-based index)
COUNTRY_COLUMN_INDEX = 0            # Country names in reference sheet

# Reference slices: row ranges for each category in the reference sheet
@dataclass(frozen=True)
class ReferenceSlices:
    total_capacity: Tuple[int, int] = (2, 188)

    wind: Tuple[int, int]   = (7373, 7559)
    solar: Tuple[int, int]  = (7562, 7748)
    geothermal: Tuple[int, int] = (7751, 7937)
    hydro: Tuple[int, int]  = (569, 755)

    nuclear: Tuple[int, int] = (1892, 2078)

    # Thermal: totals and CHP
    gas_total: Tuple[int, int]  = (2648, 2834)
    coal_total: Tuple[int, int] = (2270, 2456)
    bio_total: Tuple[int, int]  = (2837, 3023)
    oil_total: Tuple[int, int]  = (3026, 3212)

    gas_chp: Tuple[int, int]  = (4160, 4346)
    coal_chp: Tuple[int, int] = (3782, 3968)
    bio_chp: Tuple[int, int]  = (4349, 4535)
    oil_chp: Tuple[int, int]  = (3971, 4157)


# Default tech placeholders used when imputing
DEFAULT_TECH = {
    "Wind": "On-shore",
    "Solar": "PV",
    "Hydro": "Dam",
    "Geothermal": "Binary cycle",
    "Nuclear": "PWR",
    # Thermal tech placeholders:
    ("Thermal", "Gas"): "GT",
    ("Thermal", "Coal"): "Subcritical",  # could also be IGCC if preferred
    ("Thermal", "Bio"): "Steam",
    ("Thermal", "Oil"): "Combustion Engine",
}

IMPUTED_YEAR_DEFAULT = "2000"


# ==============================
# Public API
# ==============================

def reconcile_capacity_with_reference(
    plants_df: pd.DataFrame,
    reference_path: str = "./DataandPython/strategirummet_dataset.xlsx",
    *,
    capacity_col_index: int = CAPACITY_COLUMN_INDEX_DEFAULT,
    slices: ReferenceSlices = ReferenceSlices(),
    shortfall_threshold: float = 0.95,
    country_col_in_plants: str = "Country",
    status_col: str = "Unit status",
    capacity_col_in_plants: str = "Net capacity (MW)",
    energy_col: str = "Energy 1",
    chp_col: str = "CHP",
    category_col: str = "Category",
    commissioning_year_col: str = "Commissioning Year",
    add_imputed_flag_col: Optional[str] = "Imputed",
) -> pd.DataFrame:
    """
    Compare plant-level operational capacity against national reference totals
    (by technology buckets) and add synthetic rows to fill shortfalls.

    Performance & maintainability:
      - Pre-aggregates plant data with groupby (vectorized)
      - Reads reference once and builds fast dict lookups
      - Batches all new rows and concatenates once

    Parameters
    ----------
    plants_df : pd.DataFrame
        Your plant-level dataset.
    reference_path : str
        Excel workbook path for national capacities.
    capacity_col_index : int
        0-based column index in the reference sheet that holds capacity values.
    slices : ReferenceSlices
        Row slices for each reference category. Keep these updated if the sheet shifts.
    shortfall_threshold : float
        Only reconcile countries whose operational capacity is ≤ threshold * reference_total.
    country_col_in_plants : str
        Column name for country in plants_df.
    status_col : str
        Column name for plant operational status (expects value "Operational").
    capacity_col_in_plants : str
        Column with per-unit capacity in MW.
    energy_col : str
        Column with high-level energy family (e.g., "Wind", "Solar", "Gas", "Coal", "Bio", "Oil", "Nuclear").
    chp_col : str
        Column with CHP flag (expects "1" for CHP; anything else interpreted as non-CHP).
    category_col : str
        Column to write high-level category ("Wind", "Solar", "Nuclear", "Thermal", etc.).
    commissioning_year_col : str
        Column to place a default commissioning year for imputed rows.
    add_imputed_flag_col : Optional[str]
        If set, a boolean column marking imputed rows will be added/filled.

    Returns
    -------
    pd.DataFrame
        The original dataframe plus synthetic rows for missing capacity.
    """

    # 1) Read reference sheet once (no headers; absolute positioning).
    reference_df = pd.read_excel(reference_path, header=None)

    # 2) Build category -> country -> capacity dicts for O(1) lookup.
    ref_maps = _build_reference_maps(reference_df, capacity_col_index, slices)

    # 3) Pre-aggregate plants_df for speed (vectorized groupbys).
    #    We only consider "Operational" units.
    plants_oper = plants_df[plants_df[status_col] == "Operational"].copy()

    # country total
    plant_total_by_country = (
        plants_oper.groupby(country_col_in_plants, as_index=True)[capacity_col_in_plants]
        .sum()
        .to_dict()
    )

    # Renewables + Nuclear by country
    plant_by_country_category = (
        plants_oper.groupby([country_col_in_plants, category_col], as_index=True)[capacity_col_in_plants]
        .sum()
        .unstack(fill_value=0)
    )
    # Thermal by fuel and CHP flag
    # Normalize CHP to clean buckets ("1" -> chp=True, else False)
    chp_series = plants_oper[chp_col].astype(str).eq("1")
    plants_oper = plants_oper.assign(__CHP__=chp_series)

    thermal_mask = plants_oper[category_col].eq("Thermal")
    thermal = plants_oper[thermal_mask]

    # Map detailed thermal fuels from energy_col: expected "Gas", "Coal", "Bio", "Oil"
    thermal_group = (
        thermal.groupby([country_col_in_plants, energy_col, "__CHP__"], as_index=True)[capacity_col_in_plants]
        .sum()
        .unstack(fill_value=0)  # columns: CHP False/True
    )
    # Ensure multi-index exists even if empty
    if thermal_group.empty:
        thermal_group = pd.DataFrame(columns=[False, True])

    # 4) Iterate countries (fast dict lookups, accumulate rows, single concat).
    countries_in_plants: Iterable[str] = plants_df[country_col_in_plants].dropna().unique().tolist()
    new_rows: List[Dict] = []

    for country in countries_in_plants:
        # Reference totals for this country
        ref_total = ref_maps["total_capacity"].get(country, 0.0)
        if ref_total <= 0:
            # If there's no reference, skip reconciliation for this country
            continue

        plant_total = plant_total_by_country.get(country, 0.0)
        if plant_total > shortfall_threshold * ref_total:
            # Within tolerance, skip country
            continue

        # ----- Renewables -----
        for cat in ("Wind", "Solar", "Geothermal", "Hydro"):
            ref_val = ref_maps[cat.lower()].get(country, 0.0)
            plant_val = _safe_get_2d(plant_by_country_category, country, cat)
            diff = max(ref_val - plant_val, 0.0)
            if diff > 0:
                new_rows.append(_make_row(
                    country=country,
                    category=cat,
                    energy_family=cat,  # same as category for RES buckets
                    capacity_mw=diff,
                    technology=DEFAULT_TECH.get(cat, None),
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=None,
                    add_imputed_flag_col=add_imputed_flag_col
                ))

        # ----- Nuclear -----
        ref_nuclear = ref_maps["nuclear"].get(country, 0.0)
        plant_nuclear = _safe_get_2d(plant_by_country_category, country, "Nuclear")
        diff_nuclear = max(ref_nuclear - plant_nuclear, 0.0)
        if diff_nuclear > 0:
            new_rows.append(_make_row(
                country=country,
                category="Nuclear",
                energy_family="Nuclear",
                capacity_mw=diff_nuclear,
                technology=DEFAULT_TECH.get("Nuclear", None),
                commissioning_year=IMPUTED_YEAR_DEFAULT,
                chp=None,
                add_imputed_flag_col=add_imputed_flag_col
            ))

        # ----- Thermal (CHP / non-CHP splits for Gas/Coal/Bio/Oil) -----
        for fuel in ("Gas", "Coal", "Bio", "Oil"):
            ref_total_fuel = ref_maps[f"{fuel.lower()}_total"].get(country, 0.0)
            ref_chp_fuel = ref_maps[f"{fuel.lower()}_chp"].get(country, 0.0)
            ref_nonchp_fuel = max(ref_total_fuel - ref_chp_fuel, 0.0)

            # plant sums
            plant_chp = _safe_get_thermal(thermal_group, country, fuel, chp=True)
            plant_nonchp = _safe_get_thermal(thermal_group, country, fuel, chp=False)

            # diffs
            diff_chp = max(ref_chp_fuel - plant_chp, 0.0)
            diff_nonchp = max(ref_nonchp_fuel - plant_nonchp, 0.0)

            tech = DEFAULT_TECH.get(("Thermal", fuel), None)

            if diff_chp > 0:
                new_rows.append(_make_row(
                    country=country,
                    category="Thermal",
                    energy_family=fuel,
                    capacity_mw=diff_chp,
                    technology=tech,
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=True,
                    add_imputed_flag_col=add_imputed_flag_col
                ))
            if diff_nonchp > 0:
                new_rows.append(_make_row(
                    country=country,
                    category="Thermal",
                    energy_family=fuel,
                    capacity_mw=diff_nonchp,
                    technology=tech,
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=False,
                    add_imputed_flag_col=add_imputed_flag_col
                ))

    # 5) Countries missing entirely in plants_df: add everything from reference
    ref_countries = set(ref_maps["total_capacity"].keys())
    missing_countries = sorted(ref_countries.difference(set(countries_in_plants)))

    for country in missing_countries:
        # Renewables
        for cat in ("Wind", "Solar", "Geothermal", "Hydro"):
            ref_val = ref_maps[cat.lower()].get(country, 0.0)
            if ref_val > 0:
                new_rows.append(_make_row(
                    country=country,
                    category=cat,
                    energy_family=cat,
                    capacity_mw=ref_val,
                    technology=DEFAULT_TECH.get(cat, None),
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=None,
                    add_imputed_flag_col=add_imputed_flag_col
                ))

        # Nuclear
        ref_nuc = ref_maps["nuclear"].get(country, 0.0)
        if ref_nuc > 0:
            new_rows.append(_make_row(
                country=country,
                category="Nuclear",
                energy_family="Nuclear",
                capacity_mw=ref_nuc,
                technology=DEFAULT_TECH.get("Nuclear", None),
                commissioning_year=IMPUTED_YEAR_DEFAULT,
                chp=None,
                add_imputed_flag_col=add_imputed_flag_col
            ))

        # Thermal
        for fuel in ("Gas", "Coal", "Bio", "Oil"):
            ref_total_fuel = ref_maps[f"{fuel.lower()}_total"].get(country, 0.0)
            ref_chp_fuel = ref_maps[f"{fuel.lower()}_chp"].get(country, 0.0)
            ref_nonchp_fuel = max(ref_total_fuel - ref_chp_fuel, 0.0)

            tech = DEFAULT_TECH.get(("Thermal", fuel), None)

            if ref_chp_fuel > 0:
                new_rows.append(_make_row(
                    country=country,
                    category="Thermal",
                    energy_family=fuel,
                    capacity_mw=ref_chp_fuel,
                    technology=tech,
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=True,
                    add_imputed_flag_col=add_imputed_flag_col
                ))
            if ref_nonchp_fuel > 0:
                new_rows.append(_make_row(
                    country=country,
                    category="Thermal",
                    energy_family=fuel,
                    capacity_mw=ref_nonchp_fuel,
                    technology=tech,
                    commissioning_year=IMPUTED_YEAR_DEFAULT,
                    chp=False,
                    add_imputed_flag_col=add_imputed_flag_col
                ))

    # 6) Concatenate once (fast) and return
    if not new_rows:
        # Nothing to add
        return plants_df

    new_df = pd.DataFrame(new_rows)

    # Ensure required columns exist in the original df; create if missing
    for col in (category_col, commissioning_year_col, chp_col):
        if col not in plants_df.columns:
            plants_df[col] = None
    if add_imputed_flag_col and add_imputed_flag_col not in plants_df.columns:
        plants_df[add_imputed_flag_col] = False

    # Normalize column names for merge
    col_rename = {
        "Country": country_col_in_plants,
        "Category": category_col,
        "Commissioning Year": commissioning_year_col,
        "CHP": chp_col,
        "Energy 1": energy_col,
        "Net capacity (MW)": capacity_col_in_plants,
    }
    new_df = new_df.rename(columns=col_rename)

    return pd.concat([plants_df, new_df], ignore_index=True)


# ==============================
# Helpers
# ==============================

def _build_reference_maps(
    reference_df: pd.DataFrame,
    capacity_col_index: int,
    slices: ReferenceSlices,
) -> Dict[str, Dict[str, float]]:
    """
    Build a dict of dicts: key is category key, value is {country: capacity}.
    """
    def _slice_to_map(row_slice: Tuple[int, int]) -> Dict[str, float]:
        block = reference_df.iloc[row_slice[0]:row_slice[1], :]
        # Expect: COUNTRY in col 0, CAPACITY in capacity_col_index
        # Drop rows where country or capacity is NaN
        sub = block[[COUNTRY_COLUMN_INDEX, capacity_col_index]].dropna()
        # Cast country to str, capacity to float
        sub[COUNTRY_COLUMN_INDEX] = sub[COUNTRY_COLUMN_INDEX].astype(str)
        sub[capacity_col_index] = pd.to_numeric(sub[capacity_col_index], errors="coerce").fillna(0.0)
        return dict(zip(sub[COUNTRY_COLUMN_INDEX], sub[capacity_col_index]))

    return {
        "total_capacity": _slice_to_map(slices.total_capacity),

        "wind": _slice_to_map(slices.wind),
        "solar": _slice_to_map(slices.solar),
        "geothermal": _slice_to_map(slices.geothermal),
        "hydro": _slice_to_map(slices.hydro),

        "nuclear": _slice_to_map(slices.nuclear),

        "gas_total": _slice_to_map(slices.gas_total),
        "coal_total": _slice_to_map(slices.coal_total),
        "bio_total": _slice_to_map(slices.bio_total),
        "oil_total": _slice_to_map(slices.oil_total),

        "gas_chp": _slice_to_map(slices.gas_chp),
        "coal_chp": _slice_to_map(slices.coal_chp),
        "bio_chp": _slice_to_map(slices.bio_chp),
        "oil_chp": _slice_to_map(slices.oil_chp),
    }


def _safe_get_2d(pivot: pd.DataFrame, row: str, col: str) -> float:
    if pivot is None or pivot.empty:
        return 0.0
    try:
        return float(pivot.loc[row, col])
    except KeyError:
        return 0.0
    except Exception:
        return 0.0


def _safe_get_thermal(thermal_group: pd.DataFrame, country: str, fuel: str, *, chp: bool) -> float:
    """
    thermal_group index: (country, fuel), columns: [False, True] for CHP flag
    """
    if thermal_group is None or thermal_group.empty:
        return 0.0
    try:
        val = thermal_group.loc[(country, fuel), chp]
        return float(val)
    except KeyError:
        return 0.0
    except Exception:
        return 0.0


def _make_row(
    *,
    country: str,
    category: str,
    energy_family: Optional[str],
    capacity_mw: float,
    technology: Optional[str],
    commissioning_year: str,
    chp: Optional[bool],
    add_imputed_flag_col: Optional[str],
) -> Dict:
    """
    Create a synthetic row (as dict) with consistent fields.
    """
    row = {
        "Country": country,
        "Category": category,
        "Energy 1": energy_family,
        "Net capacity (MW)": capacity_mw,
        "Technology": technology,
        "Commissioning Year": commissioning_year,
    }
    if chp is not None:
        row["CHP"] = "1" if chp else "0"
    else:
        row["CHP"] = None

    if add_imputed_flag_col:
        row[add_imputed_flag_col] = True

    return row
