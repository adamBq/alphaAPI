from Crime.crime_data_api.crime_data_api import lambda_handler
import sys
import os
import json
import pytest
import copy

@pytest.fixture
def mock_static_response():
    """ Returns a static JSON response for testing """
    return {
        "totalNumCrimes": 100,
        "crimeSummary": {
            "Homicide": {
                "totalNum": 10,
                "Murder": {
                    "totalNum": 4,
                    "2020": {
                        "totalNum": 2,
                        "Jan": 1,
                        "Feb": 1,
                        "Mar": 0,
                        "Apr": 0,
                        "May": 0,
                        "Jun": 0,
                        "Jul": 0,
                        "Aug": 0,
                        "Sep": 0,
                        "Oct": 0,
                        "Nov": 0,
                        "Dec": 0
                    },
                    "2021": {
                        "totalNum": 2,
                        "Jan": 0,
                        "Feb": 0,
                        "Mar": 1,
                        "Apr": 0,
                        "May": 0,
                        "Jun": 0,
                        "Jul": 0,
                        "Aug": 0,
                        "Sep": 0,
                        "Oct": 0,
                        "Nov": 1,
                        "Dec": 0
                    }
                }
            }
        },
        "crimeTrends": {
            "Homicide": {
                "Murder": {
                    "trendSlope": 0.5,
                    "trendPercentage": 20.0,
                    "movingAvg": 1.5,
                    "trendCategory": "Increasing",
                }
            }
        }
    }


def test_lambda_handler_valid_suburb(monkeypatch, mock_static_response):
    """
    Test lambda_handler with a valid suburb query, returning static JSON.
    """
    event = {
        "pathParameters": {"suburb": "Sydney"}
    }

    # Mock the DynamoDB get_item function to return static JSON
    def mock_get_item(Key):
        if Key["suburb"] == "Sydney":
            return {"Item": mock_static_response}
        return {}

    # Monkeypatch the table object to use mock function
    monkeypatch.setattr("Crime.crime_data_api.crime_data_api.table",
                        type("MockTable", (), {"get_item": mock_get_item}))

    response = lambda_handler(event, None)

    print(response)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == mock_static_response


def test_lambda_handler_missing_suburb():
    """
    Test lambda_handler when suburb is missing in the query parameters.
    """
    event = {"pathParameters": {}}
    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert json.loads(response["body"]) == {
        "error": "Missing required parameter : suburb"}


def test_lambda_handler_non_existent_suburb(monkeypatch):
    """
    Test lambda_handler when a non-existent suburb is queried.
    """
    event = {"pathParameters": {"suburb": "NonExistent"}}

    # Monkeypatch to return empty response
    monkeypatch.setattr("Crime.crime_data_api.crime_data_api.table",
                        type("MockTable", (), {"get_item": lambda Key: {}}))

    response = lambda_handler(event, None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {
        "error": "No data found for suburb: NonExistent"}


def test_lambda_handler_exception(monkeypatch):
    """
    Test lambda_handler when an exception is raised.
    """
    def mock_raising_exception(*args, **kwargs):
        raise Exception("Test error")

    # Monkeypatch table to simulate an exception
    monkeypatch.setattr("Crime.crime_data_api.crime_data_api.table", type(
        "MockTable", (), {"get_item": mock_raising_exception}))

    event = {"pathParameters": {"suburb": "Sydney"}}
    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    assert "error" in json.loads(response["body"])

def test_lambda_handler_detailed_false(monkeypatch, mock_static_response):
    """
    Test lambda_handler with 'detailed=false' to check simplified crimeSummary output.
    """
    event = {
        "pathParameters": {"suburb": "Sydney"},
        "queryStringParameters": {"detailed": "false"}
    }

    # Clone and stringify crimeSummary so it matches production shape
    mock_item = copy.deepcopy(mock_static_response)
    mock_item["crimeSummary"] = json.dumps(mock_item["crimeSummary"])

    def mock_get_item(Key):
        if Key["suburb"] == "Sydney":
            return {"Item": mock_item}
        return {}

    monkeypatch.setattr("Crime.crime_data_api.crime_data_api.table",
                        type("MockTable", (), {"get_item": mock_get_item}))

    response = lambda_handler(event, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert "totalNum" in body["crimeSummary"]["Homicide"]["Murder"]
    assert isinstance(body["crimeSummary"]["Homicide"]["Murder"], dict)
    assert list(body["crimeSummary"]["Homicide"]["Murder"].keys()) == ["totalNum"]