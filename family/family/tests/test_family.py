from family.family import get_family_data, lambda_handler, S3_BUCKET_NAME, S3_CSV_KEY, S3_CODES_KEY
import json
import pytest
import boto3
import pandas as pd
from io import BytesIO
from moto import mock_aws
import os
import sys
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            '..')))


@pytest.fixture
def s3_setup():
    """
    Sets up a mocked S3 environment with a test bucket and places dummy files for:
      - suburb_codes.py containing a SUBURB_CODES_MAP,
      - a CSV file (2021Census_G29_NSW_SAL.csv) containing dummy family data.
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=S3_BUCKET_NAME)

        codes_content = "SUBURB_CODES_MAP = {'001': 'TestSuburb'}"
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CODES_KEY,
            Body=codes_content.encode("utf-8")
        )

        # dummy csv content
        csv_content = (
            "SAL_CODE_2021,Total_F,Total_P,CF_no_children_F,CF_no_children_P,"
            "CF_ChU15_a_Total_F,CF_ChU15_a_Total_P,CF_no_ChU15_a_Total_F,CF_no_ChU15_a_Total_P,"
            "CF_Total_F,CF_Total_P,OPF_ChU15_a_Total_F,OPF_ChU15_a_Total_P,"
            "OPF_no_ChU15_a_Total_F,OPF_no_ChU15_a_Total_P,OPF_Total_F,OPF_Total_P,"
            "Other_family_F,Other_family_P\n"
            "SAL001,10,20,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16\n")
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CSV_KEY,
            Body=csv_content.encode("utf-8")
        )

        yield s3


@pytest.fixture
def set_env_vars():
    """
    If your code were to rely on environment variables for S3 bucket names or keys,
    set them here. In our case, our module uses constants from family.py.
    """
    old_env = dict(os.environ)
    os.environ["S3_BUCKET_NAME"] = S3_BUCKET_NAME
    os.environ["S3_CSV_KEY"] = S3_CSV_KEY
    os.environ["S3_CODES_KEY"] = S3_CODES_KEY
    yield
    os.environ.clear()
    os.environ.update(old_env)


def test_get_family_data_success(s3_setup, set_env_vars):
    """
    Test that get_family_data returns the correct aggregated JSON for a valid suburb.
    The dummy suburb_codes.py maps '001' to "TestSuburb" and the CSV has one row for SAL001.
    """
    result_json = get_family_data("TestSuburb")
    result = json.loads(result_json)

    expected = {
        "suburb": "TestSuburb",
        "totalFamilies": 30,
        "coupleFamilyWithNoChildren": 3,
        "coupleFamilyWithChildrenUnder15": 7,
        "coupleFamilyWithChildrenOver15": 11,
        "totalCoupleFamilies": 15,
        "oneParentWithChildrenUnder15": 19,
        "oneParentWithChildrenOver15": 23,
        "totalOneParentFamilies": 27,
        "otherFamily": 31
    }

    for key, value in expected.items():
        assert result[
            key] == value, f"Expected {key} to be {value}, but got {result.get(key)}"


def test_get_family_data_invalid_suburb(s3_setup, set_env_vars):
    """
    Test that get_family_data returns an error JSON when the suburb is not found in the codes map.
    """
    result_json = get_family_data("NonExistentSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Suburb code not found" in result["error"]


def test_get_family_data_missing_codes_file(
        s3_setup, set_env_vars, monkeypatch):
    """
    Test that get_family_data returns an error if the SUBURB_CODES_MAP is missing from the codes file.
    """
    faulty_codes = "print('No map here')"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CODES_KEY,
        Body=faulty_codes.encode("utf-8")
    )
    result_json = get_family_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "SUBURB_CODES_MAP not found" in result["error"]


def test_get_family_data_no_csv_data(s3_setup, set_env_vars, monkeypatch):
    """
    Test that get_family_data returns an error when the CSV file retrieval fails.
    """
    def fake_get_object_csv(Bucket, Key):
        if Key == S3_CSV_KEY:
            raise Exception("CSV retrieval error")
        if Key == S3_CODES_KEY:
            codes_content = "SUBURB_CODES_MAP = {'001': 'TestSuburb'}"
            return {"Body": BytesIO(codes_content.encode("utf-8"))}
    monkeypatch.setattr(
        "family.family.s3_client.get_object",
        fake_get_object_csv)

    result_json = get_family_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Failed to read CSV file" in result["error"]


def test_get_family_data_no_matching_csv(s3_setup, set_env_vars):
    """
    Test that get_family_data returns an error when no CSV rows match the suburb code.
    """
    dummy_csv = (
        "SAL_CODE_2021,Total_F,Total_P\n"
        "SAL999,10,20\n"
    )
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CSV_KEY,
        Body=dummy_csv.encode("utf-8")
    )

    result_json = get_family_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "No data found for suburb code" in result["error"]


def test_lambda_handler_success(s3_setup, set_env_vars):
    """
    Test that lambda_handler returns a 200 status code and the correct body when given a valid event.
    """
    event = {"pathParameters": {"suburb": "TestSuburb"}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 200

    result = json.loads(response["body"])
    assert result.get("suburb") == "TestSuburb"


def test_lambda_handler_no_suburb(set_env_vars):
    """
    Test that lambda_handler returns a 400 status code if the suburb is not provided.
    """
    event = {"pathParameters": {"suburb": ""}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 400
    result = json.loads(response["body"])
    assert "error" in result


def test_lambda_handler_exception(monkeypatch, set_env_vars):
    """
    Test that lambda_handler returns a 500 status code when an exception occurs.
    """
    def faulty_get_family_data(suburb_name, *args, **kwargs):
        raise Exception("Test exception")
    monkeypatch.setattr(
        "family.family.get_family_data",
        faulty_get_family_data)

    event = {"pathParameters": {"suburb": "TestSuburb"}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 500
    result = json.loads(response["body"])
    assert "An error occurred" in result["error"] or "Test exception" in result["error"]
