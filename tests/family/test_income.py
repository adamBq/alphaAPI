import family.income.income as income
from family.income.income import get_income_data, lambda_handler, S3_BUCKET_NAME, S3_CSV_KEY, S3_CODES_KEY
import json
import pytest
import boto3
from io import BytesIO
from moto import mock_aws
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def s3_setup(monkeypatch):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=S3_BUCKET_NAME)

        monkeypatch.setattr(income, "s3_client", s3)

        # Suburb codes mapping: 001 → TestSuburb
        codes_content = "SUBURB_CODES_MAP = {'001': 'TestSuburb'}"
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CODES_KEY,
            Body=codes_content.encode("utf-8")
        )

        # Sample census CSV content
        csv_content = (
            "SAL_CODE_2021,P_Tot_Tot,P_PI_NS_Tot,P_650_799_Tot,P_800_999_Tot,"
            "P_1000_1249_Tot,P_1250_1499_Tot,P_1500_1749_Tot,P_1750_1999_Tot,"
            "P_2000_2999_Tot,P_3000_3499_Tot,P_3500_more_Tot\n"
            "SAL001,1000,50,100,150,200,100,50,30,20,10,5\n"
        )
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_CSV_KEY,
            Body=csv_content.encode("utf-8")
        )

        yield s3

@pytest.fixture
def set_env_vars():
    old_env = dict(os.environ)
    os.environ["S3_BUCKET_NAME"] = S3_BUCKET_NAME
    os.environ["S3_CSV_KEY"] = S3_CSV_KEY
    os.environ["S3_CODES_KEY"] = S3_CODES_KEY
    yield
    os.environ.clear()
    os.environ.update(old_env)

# ---------------------------------------------------------------------
# Tests for get_income_data
# ---------------------------------------------------------------------

def test_get_income_data_success(s3_setup, set_env_vars):
    result_json = get_income_data("TestSuburb")
    result = json.loads(result_json)

    assert result["suburb"] == "TestSuburb"
    assert result["suburb_code"] == "SAL001"
    assert result["650_799 range"] == 100
    assert result["800_999 range"] == 150
    assert result["Total_population"] == 1000
    assert result["Partial_income_not_stated"] == 50
    assert isinstance(result["average_income_range"], int)

def test_get_income_data_invalid_suburb(s3_setup, set_env_vars):
    result_json = get_income_data("UnknownSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Suburb code not found" in result["error"]

def test_get_income_data_no_data_match(s3_setup, set_env_vars):
    csv_data = (
        "SAL_CODE_2021,P_Tot_Tot\n"
        "SAL999,200\n"
    )
    boto3.client("s3", region_name="us-east-1").put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CSV_KEY,
        Body=csv_data.encode("utf-8")
    )
    result_json = get_income_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "No data found" in result["error"]

def test_get_income_data_missing_code_map(s3_setup, set_env_vars):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_CODES_KEY,
        Body="print('no map')".encode("utf-8")
    )
    result_json = get_income_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "SUBURB_CODES_MAP" in result["error"]

def test_get_income_data_csv_read_failure(s3_setup, set_env_vars, monkeypatch):
    def broken_get_object(Bucket, Key):
        raise Exception("fail")
    monkeypatch.setattr("family.income.income.s3_client.get_object", broken_get_object)
    result_json = get_income_data("TestSuburb")
    result = json.loads(result_json)
    assert "error" in result
    assert "Failed to read CSV" in result["error"]

# ---------------------------------------------------------------------
# Lambda handler tests
# ---------------------------------------------------------------------

def test_lambda_handler_success(s3_setup, set_env_vars):
    event = {"pathParameters": {"suburb": "TestSuburb"}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["suburb"] == "TestSuburb"

def test_lambda_handler_no_suburb(set_env_vars):
    event = {"pathParameters": {"suburb": ""}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body

def test_lambda_handler_exception(monkeypatch, set_env_vars):
    def broken_function(suburb): raise Exception("boom")
    monkeypatch.setattr("family.income.income.get_income_data", broken_function)
    event = {"pathParameters": {"suburb": "TestSuburb"}}
    response = lambda_handler(event, {})
    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "error" in body