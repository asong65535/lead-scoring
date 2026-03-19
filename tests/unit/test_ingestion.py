import pandas as pd
import numpy as np
from src.services.ingestion import replace_placeholders


def test_replace_placeholders_replaces_select():
    df = pd.DataFrame({"Specialization": ["Data Science", "Select", "select"]})
    result = replace_placeholders(df)
    assert result["Specialization"].iloc[0] == "Data Science"
    assert pd.isna(result["Specialization"].iloc[1])
    assert pd.isna(result["Specialization"].iloc[2])


def test_replace_placeholders_replaces_empty_and_whitespace():
    df = pd.DataFrame({"City": ["Mumbai", "", "   "]})
    result = replace_placeholders(df)
    assert result["City"].iloc[0] == "Mumbai"
    assert pd.isna(result["City"].iloc[1])
    assert pd.isna(result["City"].iloc[2])


def test_replace_placeholders_strips_whitespace():
    df = pd.DataFrame({"City": ["  Mumbai  ", "  Specialization  "]})
    result = replace_placeholders(df)
    assert result["City"].iloc[0] == "Mumbai"
    assert result["City"].iloc[1] == "Specialization"


def test_replace_placeholders_ignores_non_string_columns():
    df = pd.DataFrame({"TotalVisits": [5, 0, 3], "City": ["Mumbai", "Select", ""]})
    result = replace_placeholders(df)
    assert result["TotalVisits"].tolist() == [5, 0, 3]
