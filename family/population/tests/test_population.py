from population.population import get_suburb_population, lambda_handler, S3_BUCKET_NAME, S3_CSV_KEY, S3_CODES_KEY
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


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def s3_setup():
    """
    Sets up a mocked S3 environment with a test bucket and uploads dummy files for:
      - suburb_codes.py containing a SUBURB_CODES_MAP,
      - A CSV file (2021Census_G01_NSW_SAL.csv) containing dummy census population data.
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=S3_BUCKET_NAME)

        # Dummy suburb_codes.py content: mapping code '001' to "TestSuburb"
        codes_content = "SUBURB_CODES_MAP = {'001': 'TestSuburb'}"
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CODES_KEY,
            Body=codes_content.encode("utf-8")
        )

        # dummy csv content
        csv_content = (
            "SAL_CODE_2021,Tot_P_M,Tot_P_F\n"
            "SAL001,100,200\n"
        )
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CSV_KEY,
            Body=csv_content.encode("utf-8")
        )

        yield s3


@pytest.fixture
def set_env_vars():
    """
    Sets environment variables if your module relies on them.
    """
    old_env = dict(os.environ)
    os.environ["S3_BUCKET_NAME"] = S3_BUCKET_NAME
    os.environ["S3_CSV_KEY"] = S3_CSV_KEY
    os.environ["S3_CODES_KEY"] = S3_CODES_KEY
    yield
    os.environ.clear()
    os.environ.update(old_env)

# ---------------------------------------------------------------------
# Tests for get_suburb_population
# ---------------------------------------------------------------------


def test_get_suburb_population_success(s3_setup, set_env_vars):
    """
    Test that get_suburb_population returns the correct aggregated JSON for a valid suburb.
    The dummy suburb_codes.py maps '001' to "TestSuburb" and the CSV has one row for SAL001.
    """
    result_json = get_suburb_population("TestSuburb")
    result = json.loads(result_json)

    expected = {
        "suburb": "TestSuburb",
        "totalPopulation": 300,
        "male": 100,
        "female": 200
    }

    for key, value in expected.items():
        assert result.get(
            key) == value, f"Expected {key} to be {value}, but got {result.get(key)}"


def test_get_suburb_population_invalid_suburb(s3_setup, set_env_vars):
    """
    Test that get_suburb_population returns an error when the suburb is not found in the codes map.
    """
    result_json = get_suburb_population("NonExistentSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Suburb code not found" in result["error"]


def test_get_suburb_population_missing_codes_file(s3_setup, set_env_vars):
    """
    Test that get_suburb_population returns an error if the SUBURB_CODES_MAP is missing from the codes file.
    """
    faulty_codes = "print('No map here')"
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CODES_KEY,
        Body=faulty_codes.encode("utf-8")
    )
    result_json = get_suburb_population("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "No SUBURB_CODES_MAP found" in result["error"]


def test_get_suburb_population_no_csv_data(
        s3_setup, set_env_vars, monkeypatch):
    """
    Test that get_suburb_population returns an error when the CSV retrieval fails.
    """
    def fake_get_object(Bucket, Key):
        if Key == S3_CSV_KEY:
            raise Exception("CSV retrieval error")
        if Key == S3_CODES_KEY:
            codes_content = "SUBURB_CODES_MAP = {'001': 'TestSuburb'}"
            return {"Body": BytesIO(codes_content.encode("utf-8"))}

    monkeypatch.setattr(
        "population.population.s3_client.get_object",
        fake_get_object)
    result_json = get_suburb_population("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Failed to read CSV file" in result["error"]


def test_get_suburb_population_no_matching_csv(s3_setup, set_env_vars):
    """
    Test that get_suburb_population returns an error when no CSV rows match the suburb code.
    """
    # Overwrite the CSV file with data that does not contain the matching SAL
    # code.
    dummy_csv = (
        "SAL_CODE_2021,Tot_P_M,Tot_P_F\n"
        "SAL999,100,200\n"
    )
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CSV_KEY,
        Body=dummy_csv.encode("utf-8")
    )
    result_json = get_suburb_population("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "No data found for suburb with code" in result["error"]

# ---------------------------------------------------------------------
# Tests for lambda_handler
# ---------------------------------------------------------------------


def test_lambda_handler_success(s3_setup, set_env_vars):
    """
    Test that lambda_handler returns a 200 status code and correct body when given a valid event.
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
    Test that lambda_handler returns a 500 status code when an exception occurs in get_suburb_population.
    """
    def faulty_get_suburb_population(suburb_name, *args, **kwargs):
        raise Exception("Test exception")
    monkeypatch.setattr(
        "population.population.get_suburb_population",
        faulty_get_suburb_population)

    event = {"pathParameters": {"suburb": "TestSuburb"}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 500
    result = json.loads(response["body"])
    # The error response should contain the exception message.
    assert "An error occurred" in result["error"] or "Test exception" in result["error"]
