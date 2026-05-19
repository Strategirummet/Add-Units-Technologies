from pathlib import Path
import pandas as pd


def load_file(
    path: Path,
    sheet_name: str | None = None,
    header: int | None = 0,
) -> pd.DataFrame:
    """
    Load an Excel file into a DataFrame.

    Parameters:
        path:
            Path to the Excel file.
        sheet_name:
            Name of the sheet to load.
            If None, the first sheet is loaded.
        header:
            Row to use as header.
            Use None to keep the raw spreadsheet layout.

    Returns:
        DataFrame with the loaded sheet.
        The loaded sheet name is also stored on df._sheet_name.
    """
    excel_file = pd.ExcelFile(path)

    if sheet_name is None:
        sheet_name = excel_file.sheet_names[0]
    elif sheet_name not in excel_file.sheet_names:
        available_sheets = ", ".join(excel_file.sheet_names)
        raise ValueError(
            f"Sheet '{sheet_name}' was not found in '{path.name}'. "
            f"Available sheets: {available_sheets}"
        )

    df = excel_file.parse(sheet_name, header=header)
    df._sheet_name = sheet_name

    return df