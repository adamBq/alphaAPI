from score.livability_score.main import family_score, crime_score, weather_score, transport_score, handler
import pytest
import requests
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..")))


@patch('score.livability_score.main.requests.get')
def test_family_score(mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "coupleFamilyWithChildrenUnder15": 1000,
        "oneParentWithChildrenUnder15": 500,
        "totalFamilies": 3000
    }
    mock_requests_get.return_value = mock_response
    print(family_score("TestSuburb"))
    assert family_score("TestSuburb") == pytest.approx(10.0)


@patch('score.livability_score.main.requests.get')
def test_crime_score(mock_requests_get):
    mock_crime_response = MagicMock()
    mock_crime_response.status_code = 200
    mock_crime_response.json.return_value = {
        "crimeSummary": {
            "Homicide": {
                "totalNum": 10
            },
            "Disorderly conduct": {
                "totalNum": 10
            }
        }
    }

    mock_population_response = MagicMock()
    mock_population_response.status_code = 200
    mock_population_response.json.return_value = {
        "totalPopulation": 5  # Example population
    }

    mock_requests_get.side_effect = [
        mock_crime_response,
        mock_population_response]

    assert crime_score("TestSuburb") == pytest.approx(10 * ((- 3 / 12.5) + 1))


@patch('score.livability_score.main.requests.post')
def test_weather_score(mock_requests_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "body": "{\"requestedSuburbData\": {\"occurrences\": 5}, \"highestSuburbData\": {\"occurrences\": 10}}"}
    mock_requests_post.return_value = mock_response

    assert isinstance(weather_score("TestSuburb"), (int, float))


@patch('score.livability_score.main.requests.get')
@patch('score.livability_score.main.requests.post')
def test_transport_score(mock_requests_post, mock_requests_get):
    mock_geo_response = MagicMock()
    mock_geo_response.status_code = 200
    mock_geo_response.json.return_value = {"results": [
        {"geometry": {"location": {"lat": -33.86785, "lng": 151.20732}}}]}
    mock_requests_get.return_value = mock_geo_response

    mock_bus_response = MagicMock()
    mock_bus_response.status_code = 200
    mock_bus_response.json.return_value = {"places": [
        {"location": {"latitude": -33.86785, "longitude": 151.20732}}]}

    mock_train_response = MagicMock()
    mock_train_response.status_code = 200
    mock_train_response.json.return_value = {"places": [
        {"location": {"latitude": -33.86785, "longitude": 151.20732}}]}
    mock_requests_post.side_effect = [mock_bus_response, mock_train_response]

    score = transport_score({
        "results":[
            {
            "geometry": {"location": {"lat": -33.86785, "lng": 151.20732}}
            }
        ]
    })

    assert 0.0 <= score <= 10.0


@patch('score.livability_score.main.requests.get')
@patch('score.livability_score.main.transport_score')
@patch('score.livability_score.main.crime_score')
@patch('score.livability_score.main.weather_score')
@patch('score.livability_score.main.family_score')
def test_handler(
        mock_family,
        mock_weather,
        mock_crime,
        mock_transport,
        mock_requests_get):
    mock_geo_response = MagicMock()
    mock_geo_response.status_code = 200
    mock_geo_response.return_value = {
        "results": [{
            "address_components": [{"long_name": "TestSuburb", "types": ["locality"]}]
        }]
    }
    mock_requests_get.return_value = mock_geo_response

    mock_family.return_value = 7.0
    mock_weather.return_value = 6.0
    mock_crime.return_value = 5.0
    mock_transport.return_value = 8.0

    event = {
        "body" : json.dumps({
            "address": "Test Address",
            "weights": {
                "publicTransportation": 0.3,
                "crime": 0.3,
                "weather": 0.2,
                "familyDemographics": 0.2}
        })
    }

    response = handler(event, None)

    parsed_body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert parsed_body["overallScore"] == (
        0.3 * 8.0) + (0.3 * 5.0) + (0.2 * 6) + (0.2 * 7.0)
    assert "breakdown" in parsed_body


@patch('score.livability_score.main.requests.get')
@patch('score.livability_score.main.transport_score')
@patch('score.livability_score.main.crime_score')
@patch('score.livability_score.main.weather_score')
@patch('score.livability_score.main.family_score')
def test_handler_fail(
        mock_family,
        mock_weather,
        mock_crime,
        mock_transport,
        mock_requests_get):
    mock_geo_response = MagicMock()
    mock_geo_response.status_code = 200
    mock_geo_response.return_value = {
        "results": [{
            "address_components": [{"long_name": "TestSuburb", "types": ["locality"]}]
        }]
    }
    mock_requests_get.return_value = mock_geo_response

    mock_family.return_value = 7.0
    mock_weather.return_value = 6.0
    mock_crime.return_value = 5.0
    mock_transport.return_value = None

    event = {
        "body": json.dumps({
            "address": "Test Address",
            "weights": {
                "publicTransportation": 0.3,
                "crime": 0.3,
                "weather": 0.2,
                "familyDemographics": 0.2}
        })}

    response = handler(event, None)

    assert response["statusCode"] == 500


def test_call_endpoint():
    url = 'https://hh6e0mae92.execute-api.ap-southeast-2.amazonaws.com/dev/livability_score'

    body = {
        "address": "49 Beresford Road, Strathfield",
        "weights": {
            "crime": 0.2,
            "weather": 0.1,
            "publicTransportation": 0.3,
            "familyDemographics": 0.3
        }
    }

    response = requests.post(url, json=body)
    assert response.status_code == 200
