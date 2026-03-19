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


def convert_booleans(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Yes/No and 0/1 columns to boolean."""
    df = df.copy()
    for col in ("Do Not Email", "Do Not Call"):
        if col in df.columns:
            df[col] = df[col].map({"Yes": True, "No": False}).fillna(False)
    if "Converted" in df.columns:
        mapping = {1: True, 0: False, 1.0: True, 0.0: False}
        df["Converted"] = df["Converted"].map(mapping)
    return df
