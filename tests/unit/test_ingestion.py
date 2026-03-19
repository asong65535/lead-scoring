import pandas as pd
import numpy as np
from src.services.ingestion import replace_placeholders, convert_booleans, coerce_numerics


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


def test_convert_booleans_do_not_email():
    df = pd.DataFrame({"Do Not Email": ["Yes", "No", "maybe", np.nan]})
    result = convert_booleans(df)
    assert result["Do Not Email"].tolist() == [True, False, False, False]


def test_convert_booleans_do_not_call():
    df = pd.DataFrame({"Do Not Call": ["Yes", "No", "nah", ""]})
    result = convert_booleans(df)
    assert result["Do Not Call"].tolist() == [True, False, False, False]


def test_convert_booleans_converted_nullable():
    df = pd.DataFrame({"Converted": [1, 0, 99, np.nan]})
    result = convert_booleans(df)
    assert result["Converted"].iloc[0] is True
    assert result["Converted"].iloc[1] is False
    assert pd.isna(result["Converted"].iloc[2])
    assert pd.isna(result["Converted"].iloc[3])


def test_coerce_numerics_valid_values():
    df = pd.DataFrame({
        "TotalVisits": ["5", "3", "0"],
        "Total Time Spent on Website": ["300", "120", "0"],
        "Page Views Per Visit": ["2.5", "1.5", "0"],
    })
    result = coerce_numerics(df)
    assert result["TotalVisits"].tolist() == [5.0, 3.0, 0.0]
    assert result["Total Time Spent on Website"].tolist() == [300.0, 120.0, 0.0]
    assert result["Page Views Per Visit"].tolist() == [2.5, 1.5, 0.0]


def test_coerce_numerics_invalid_become_nan():
    df = pd.DataFrame({
        "TotalVisits": ["abc", "5", ""],
        "Total Time Spent on Website": ["not_a_number", "120", None],
        "Page Views Per Visit": ["xyz", "1.5", ""],
    })
    result = coerce_numerics(df)
    assert pd.isna(result["TotalVisits"].iloc[0])
    assert result["TotalVisits"].iloc[1] == 5.0
    assert pd.isna(result["TotalVisits"].iloc[2])
