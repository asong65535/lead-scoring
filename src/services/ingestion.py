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
