import pandas as pd
import numpy as np


def replace_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    """Replace placeholder values with NaN in string columns. Strips whitespace."""
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace(
            to_replace=r"(?i)^select$|^$",
            value=np.nan,
            regex=True,
        )
    return df


NUMERIC_COLUMNS = ("TotalVisits", "Total Time Spent on Website", "Page Views Per Visit")


def convert_booleans(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Yes/No and 0/1 columns to boolean."""
    df = df.copy()
    for col in ("Do Not Email", "Do Not Call"):
        if col in df.columns:
            mapped = df[col].map({"Yes": True, "No": False}).fillna(False)
            df[col] = pd.Series([bool(x) for x in mapped], index=df.index, dtype=object)
    if "Converted" in df.columns:
        mapping = {1: True, 0: False, 1.0: True, 0.0: False}
        mapped = df["Converted"].map(mapping)
        df["Converted"] = pd.Series(
            [bool(x) if not pd.isna(x) else np.nan for x in mapped],
            index=df.index,
            dtype=object,
        )
    return df


def coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric columns to float. Invalid values become NaN."""
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


COLUMN_MAP = {
    "Prospect ID": "external_id",
    "Lead Origin": "lead_origin",
    "Lead Source": "lead_source",
    "Do Not Email": "do_not_email",
    "Do Not Call": "do_not_call",
    "Converted": "converted",
    "TotalVisits": "total_visits",
    "Total Time Spent on Website": "total_time_spent",
    "Page Views Per Visit": "page_views_per_visit",
    "Last Activity": "last_activity",
    "Country": "country",
    "Specialization": "specialization",
    "What is your current occupation": "current_occupation",
    "City": "city",
    "Tags": "tags",
}


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename CSV columns to DB column names and drop unmapped columns."""
    df = df.copy()
    mapped = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=mapped)
    return df[list(mapped.values())]


def validate_required_fields(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into valid and rejected rows based on required fields.
    Rejects rows where external_id is missing, empty, or whitespace-only.
    """
    mask = df["external_id"].notna() & (df["external_id"].str.strip() != "")
    return df[mask].copy(), df[~mask].copy()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Orchestrate all cleaning steps in order.
    Order matters:
    1. replace_placeholders — uses CSV column names
    2. convert_booleans — uses CSV column names
    3. coerce_numerics — uses CSV column names
    4. rename_columns — maps to DB names (must be last)
    """
    df = replace_placeholders(df)
    df = convert_booleans(df)
    df = coerce_numerics(df)
    df = rename_columns(df)
    return df
