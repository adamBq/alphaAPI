from Crime.crime_data_fetcher.crime_data_fetcher import lambda_handler, fetch
import sys
import os
import json
import pytest
import pandas as pd
import requests
import zipfile
from unittest.mock import patch, MagicMock

# Ensure Python finds the CrimeDataFetcher module
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))


@pytest.fixture
def mock_crime_data():
    """ Returns a mock pandas DataFrame representing crime data. """
    return pd.DataFrame({
        "Suburb": ["Sydney", "Melbourne", "Brisbane"],
        "CrimeType": ["Homicide", "Assault", "Robbery"],
        "Count": [5, 10, 7]
    })


def test_lambda_handler_success(monkeypatch, mock_crime_data):
    """Test lambda_handler when all steps succeed: data fetch, S3 upload, and SQS queuing."""

    # Mock fetch() to return static DataFrame
    def mock_fetch():
        return mock_crime_data

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.fetch",
        mock_fetch)

    # Mock S3 put_object
    class MockS3Client:
        def put_object(self, Bucket, Key, Body):
            print(f"Mock S3 Upload: {Key}")

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.s3",
        MockS3Client())

    # Mock SQS send_message
    class MockSQSClient:
        def send_message(self, QueueUrl, MessageBody):
            print(f"Mock SQS Message: {MessageBody}")

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.sqs",
        MockSQSClient())

    event = {}
    context = None
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert response["body"] == "Data fetched successfully"


def test_lambda_handler_fetch_failure(monkeypatch):
    """Test lambda_handler when fetch() fails to simulate network issues."""

    def mock_fetch():
        return None  # Simulate fetch failure

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.fetch",
        mock_fetch)

    event = {}
    context = None
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    assert response["body"] == "Error fetching crime data"


def test_lambda_handler_s3_failure(monkeypatch, mock_crime_data):
    """Test lambda_handler when S3 upload fails."""

    def mock_fetch():
        return mock_crime_data

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.fetch",
        mock_fetch)

    # Simulate S3 failure
    class MockS3Client:
        def put_object(self, Bucket, Key, Body):
            raise Exception("S3 upload failed")

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.s3",
        MockS3Client())

    # Still need to mock SQS client to avoid unexpected calls
    class MockSQSClient:
        def send_message(self, QueueUrl, MessageBody):
            pass  # Shouldn't be called in this test

    monkeypatch.setattr(
        "Crime.crime_data_fetcher.crime_data_fetcher.sqs",
        MockSQSClient())

    event = {}
    context = None
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    assert response["body"] == "Error uploading data"


def test_fetch_live_real_zip():
    """
    Actually runs the fetch method with real data from the live URL.
    Skipped if offline or data format changes.
    """
    df = fetch()

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "Suburb" in df.columns

@patch("Crime.crime_data_fetcher.crime_data_fetcher.requests.get")
def test_fetch_request_exception(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Network error")

    df = fetch()

    assert df is None

@patch("Crime.crime_data_fetcher.crime_data_fetcher.requests.get")
def test_fetch_bad_zip(mock_get):
    mock_response = MagicMock()
    mock_response.content = b"not a zip file"
    mock_response.raise_for_status = lambda: None

    mock_get.return_value = mock_response

    df = fetch()

    assert df is None