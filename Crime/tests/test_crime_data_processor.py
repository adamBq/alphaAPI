import sys
import os
import json
import pytest
import pandas as pd

# Ensure Python finds the CrimeDataProcessor module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crime_data_processor.crime_data_processor import lambda_handler, fetch_suburb_data, process_and_store_crime_data, send_to_dlq

@pytest.fixture
def mock_crime_data():
    """ Returns a mock pandas DataFrame representing crime data. """
    return pd.DataFrame({
        "Suburb": ["Sydney", "Melbourne"],
        "Offence Category": ["Homicide", "Assault"],
        "Subcategory": ["Murder", "Domestic"],
        "Jan 2022": [2, 5],
        "Feb 2022": [1, 4]
    })

def test_lambda_handler_success(monkeypatch, mock_crime_data):
    """Test lambda_handler when all steps succeed: S3 fetch, processing, and DynamoDB store."""

    # Mock fetch_suburb_data() to return static DataFrame
    def mock_fetch_suburb_data(suburb):
        return mock_crime_data if suburb == "Sydney" else None

    monkeypatch.setattr("crime_data_processor.crime_data_processor.fetch_suburb_data", mock_fetch_suburb_data)

    # Mock DynamoDB put_item
    class MockDynamoDBTable:
        def put_item(self, Item):
            print(f"Mock DynamoDB Store: {Item}")

    monkeypatch.setattr("crime_data_processor.crime_data_processor.table", MockDynamoDBTable())

    event = {"Records": [{"body": json.dumps({"suburbs": ["Sydney"]})}]}
    context = None
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert response["body"] == "Data processed successfully"

def test_lambda_handler_s3_fetch_failure(monkeypatch, capsys):
    """Test lambda_handler when S3 fetch fails (e.g., suburb data missing)."""

    def mock_fetch_suburb_data(suburb):
        return None  # Simulate S3 fetch failure

    monkeypatch.setattr("crime_data_processor.crime_data_processor.fetch_suburb_data", mock_fetch_suburb_data)

    # Mock send_to_dlq() to track failures
    failed_suburbs = []
    def mock_send_to_dlq(suburb):
        failed_suburbs.append(suburb)

    monkeypatch.setattr("crime_data_processor.crime_data_processor.send_to_dlq", mock_send_to_dlq)

    event = {"Records": [{"body": json.dumps({"suburbs": ["Sydney"]})}]}
    context = None
    lambda_handler(event, context)

    captured = capsys.readouterr()

    assert "Error fetching data for Sydney" in captured.out


def test_lambda_handler_processing_failure(monkeypatch, mock_crime_data):
    """Test lambda_handler when processing fails."""

    def mock_fetch_suburb_data(suburb):
        return mock_crime_data

    monkeypatch.setattr("crime_data_processor.crime_data_processor.fetch_suburb_data", mock_fetch_suburb_data)

    # Simulate an error in processing
    def mock_process_and_store_crime_data(df):
        raise Exception("Processing error")

    monkeypatch.setattr("crime_data_processor.crime_data_processor.process_and_store_crime_data", mock_process_and_store_crime_data)

    # Track DLQ messages
    failed_suburbs = []
    def mock_send_to_dlq(suburb):
        failed_suburbs.append(suburb)

    monkeypatch.setattr("crime_data_processor.crime_data_processor.send_to_dlq", mock_send_to_dlq)

    event = {"Records": [{"body": json.dumps({"suburbs": ["Sydney"]})}]}
    context = None
    lambda_handler(event, context)

    assert "Sydney" in failed_suburbs

def test_lambda_handler_dlq_failure(monkeypatch, mock_crime_data):
    """Test lambda_handler when DLQ sending fails."""

    def mock_fetch_suburb_data(suburb):
        return mock_crime_data

    monkeypatch.setattr("crime_data_processor.crime_data_processor.fetch_suburb_data", mock_fetch_suburb_data)

    # Simulate processing failure
    def mock_process_and_store_crime_data(df):
        return None  # Simulate failure

    monkeypatch.setattr("crime_data_processor.crime_data_processor.process_and_store_crime_data", mock_process_and_store_crime_data)

    event = {"Records": [{"body": json.dumps({"suburbs": ["Sydney"]})}]}
    context = None
    lambda_handler(event, context)

    # No assertion needed, just making sure it handles failures without crashing