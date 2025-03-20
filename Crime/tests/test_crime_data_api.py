import sys
import os
import json
import pytest

# Ensure the correct path is added
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the Lambda function
from CrimeDataAPI.CrimeDataAPI import lambda_handler

@pytest.fixture
def mock_static_response():
    """ Returns a static JSON response for testing """
    return {
        "crimeSummary": {
            "Homicide": {
                "totalNum": 0,
                "Murder": {
                    "totalNum": 0
                }
            }
        },
        "crimeTrends": {
            "Homicide": {
                "Murder": {
                    "trendSlope": 0.0,
                    "trendPercentage": 0.0,
                    "movingAvg": 0.0,
                    "trendCategory": "Stable",
                }
            }
        },
        "totalNumCrimes": 0
    }

def test_lambda_handler_valid_suburb(monkeypatch, mock_static_response):
    """
    Test lambda_handler with a valid suburb query, returning static JSON.
    """
    event = {
        "queryStringParameters": {"suburb": "Sydney"}
    }

    # Mock the DynamoDB get_item function to return static JSON
    def mock_get_item(Key):
        if Key["suburb"] == "Sydney":
            return {"Item": mock_static_response}
        return {}

    # Monkeypatch the table object to use mock function
    monkeypatch.setattr("CrimeDataAPI.CrimeDataAPI.table", 
                        type("MockTable", (), {"get_item": mock_get_item}))

    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == mock_static_response

def test_lambda_handler_missing_suburb():
    """
    Test lambda_handler when suburb is missing in the query parameters.
    """
    event = {"queryStringParameters": {}}
    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {"error": "Missing required parameter : suburb"}

def test_lambda_handler_non_existent_suburb(monkeypatch):
    """
    Test lambda_handler when a non-existent suburb is queried.
    """
    event = {"queryStringParameters": {"suburb": "NonExistent"}}

    # Monkeypatch to return empty response
    monkeypatch.setattr("CrimeDataAPI.CrimeDataAPI.table", 
                        type("MockTable", (), {"get_item": lambda Key: {}}))

    response = lambda_handler(event, None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {"error": "No data found for suburb: NonExistent"}

def test_lambda_handler_exception(monkeypatch):
    """
    Test lambda_handler when an exception is raised.
    """
    def mock_raising_exception(*args, **kwargs):
        raise Exception("Test error")

    # Monkeypatch table to simulate an exception
    monkeypatch.setattr("CrimeDataAPI.CrimeDataAPI.table", 
                        type("MockTable", (), {"get_item": mock_raising_exception}))

    event = {"queryStringParameters": {"suburb": "Sydney"}}
    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert "error" in json.loads(response["body"])

