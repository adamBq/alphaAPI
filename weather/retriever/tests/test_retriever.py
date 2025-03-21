import os
import json
import pytest
import boto3
from moto import mock_aws  # Use mock_aws instead of mock_s3

from retriever import lambda_handler


@pytest.fixture
def s3_setup():
    """
    Sets up a mocked S3 with a sample rankings file.
    """
    with mock_aws():  # Use `mock_aws()` instead of `@mock_s3`
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        # Minimal file: 2 suburbs, with one having the highest occurrences.
        sample_rankings = [
            {
                "suburb": "Shoalhaven",
                "occurrences": 15,
                "disasterNames": ["Flood1", "Flood2"]
            },
            {
                "suburb": "Eurobodalla",
                "occurrences": 14,
                "disasterNames": ["Storm1"]
            }
        ]
        s3.put_object(
            Bucket="test-bucket",
            Key="test-rankings.json",
            Body=json.dumps(sample_rankings).encode("utf-8"),
            ContentType="application/json"
        )
        yield s3  # Yielding the mocked S3 client


@pytest.fixture
def set_env_vars():
    """
    Environment variables for retriever.
    """
    old_env = dict(os.environ)
    os.environ["S3_BUCKET"] = "test-bucket"
    os.environ["RANKINGS_KEY"] = "test-rankings.json"
    yield
    os.environ.clear()
    os.environ.update(old_env)


def test_retriever_success_raw_lambda(s3_setup, set_env_vars):
    """
    Simulate calling the lambda_handler directly (no 'httpMethod' key).
    """
    event = {
        "suburb": "Shoalhaven",
        "includeHighest": True
    }
    context = {}
    response = lambda_handler(event, context)

    assert isinstance(response, dict)
    assert response["status"] == "success"
    assert response["requestedSuburbData"]["suburb"] == "Shoalhaven"
    assert response["highestSuburbData"]["suburb"] == "Shoalhaven"


def test_retriever_success_proxy(s3_setup, set_env_vars):
    """
    Simulate an API Gateway proxy call with 'httpMethod'.
    """
    event = {
        "suburb": "Shoalhaven",
        "includeHighest": True,
        "httpMethod": "GET"
    }
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert "body" in response

    body = json.loads(response["body"])
    assert body["status"] == "success"
    assert body["requestedSuburbData"]["suburb"] == "Shoalhaven"
    assert body["highestSuburbData"]["suburb"] == "Shoalhaven"


def test_retriever_not_found(s3_setup, set_env_vars):
    """
    Suburb doesn't exist in the file, should return 'not_found'.
    """
    event = {"suburb": "Nowhere", "includeHighest": True}
    context = {}
    response = lambda_handler(event, context)

    if "statusCode" in response:
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "not_found"
        assert body["highestSuburbData"]["suburb"] == "Shoalhaven"
    else:
        assert response["status"] == "not_found"


def test_retriever_no_suburb(s3_setup, set_env_vars):
    """
    Missing 'suburb' key -> error.
    """
    event = {"includeHighest": True}
    context = {}
    response = lambda_handler(event, context)

    if "statusCode" in response:
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "No suburb specified" in body["error"]
    else:
        assert "error" in response
        assert "No suburb specified" in response["error"]


def test_retriever_missing_rankings(s3_setup, set_env_vars):
    """
    If the S3 file doesn't exist, we get a 404 or an error dict.
    """
    s3_setup.delete_object(Bucket="test-bucket", Key="test-rankings.json")

    event = {"suburb": "Shoalhaven"}
    context = {}
    response = lambda_handler(event, context)

    if "statusCode" in response:
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "Could not find test-rankings.json" in body["error"]
    else:
        assert "error" in response
        assert "Could not find test-rankings.json" in response["error"]


def test_retriever_invalid_json(s3_setup, set_env_vars):
    """
    If the file is not a list, retriever returns 500 or an error.
    """
    invalid_content = {"invalid": True}
    s3_setup.put_object(
        Bucket="test-bucket",
        Key="test-rankings.json",
        Body=json.dumps(invalid_content).encode("utf-8"),
        ContentType="application/json"
    )

    event = {"suburb": "Shoalhaven"}
    context = {}
    response = lambda_handler(event, context)

    if "statusCode" in response:
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Invalid format" in body["error"]
    else:
        assert "error" in response
        assert "Invalid format" in response["error"]


def test_retriever_s3_generic_exception_proxy(
        s3_setup, set_env_vars, monkeypatch):
    """
    Test that a generic exception during S3.get_object in proxy mode returns a 500 response.
    """
    # Force lambda_handler to use our Moto S3 client (s3_setup)
    orig_boto_client = boto3.client
    monkeypatch.setattr(boto3,
                        "client",
                        lambda service,
                        *args,
                        **kwargs: s3_setup if service == "s3" else orig_boto_client(service,
                                                                                    *args,
                                                                                    **kwargs))
    # Patch get_object so that it raises a generic exception
    monkeypatch.setattr(
        s3_setup, "get_object",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Generic S3 error"))
    )

    event = {
        "suburb": "Shoalhaven",
        "includeHighest": True,
        "httpMethod": "GET"}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "Generic S3 error" in body["error"]


def test_retriever_missing_rankings_proxy(s3_setup, set_env_vars):
    """
    Test that a missing rankings file in proxy mode returns a 404 response.
    """
    # Remove the rankings file
    s3_setup.delete_object(Bucket="test-bucket", Key="test-rankings.json")

    event = {"suburb": "Shoalhaven", "httpMethod": "GET"}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "Could not find test-rankings.json" in body["error"]


def test_retriever_invalid_json_proxy(s3_setup, set_env_vars):
    """
    Test that an invalid JSON format (not a list) in proxy mode returns a 500 response.
    """
    invalid_content = {"invalid": True}
    s3_setup.put_object(
        Bucket="test-bucket",
        Key="test-rankings.json",
        Body=json.dumps(invalid_content).encode("utf-8"),
        ContentType="application/json"
    )

    event = {"suburb": "Shoalhaven", "httpMethod": "GET"}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "Invalid format" in body["error"]
