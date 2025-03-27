import os
import json
import pytest
import requests
from requests.exceptions import HTTPError
from unittest.mock import patch, MagicMock
import boto3
from moto import mock_aws  # Use mock_aws instead of mock_s3

from collector import lambda_handler


@pytest.fixture
def s3_setup():
    """
    Sets up a mocked S3 environment with a default bucket/key
    and returns the moto S3 client for test assertions.
    """
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        # Put a sample historical file in the mocked S3 bucket
        historical_data = [
            {
                "year": "fy-2020-21",
                "last_updated": "2025-02-25T12:00:00Z",
                "disasters": [
                    {
                        "AGRN": "1001",
                        "disasterType": "Storm",
                        "disasterName": "Test Storm",
                        "localGovernmentArea": "TestCouncil"
                    }
                ]
            }
        ]
        s3.put_object(
            Bucket="test-bucket",
            Key="test-historical.json",
            Body=json.dumps(historical_data).encode("utf-8"),
            ContentType="application/json"
        )
        yield s3  # Yielding the mocked S3 client


@pytest.fixture
def set_env_vars():
    """
    Sets environment variables used by collector.py.
    """
    old_env = dict(os.environ)
    os.environ["S3_BUCKET"] = "test-bucket"
    os.environ["HISTORICAL_KEY"] = "test-historical.json"
    os.environ["OUTPUT_KEY"] = "test-output.json"
    # We'll mock requests
    os.environ["LIVE_URL"] = "https://example.com/fake-page"
    yield
    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture
def mock_requests_success(monkeypatch):
    """
    Mocks requests.get() to return a fake HTML containing a table with 1 row.
    """
    def fake_get(*args, **kwargs):
        class FakeResponse:
            def __init__(self):
                self.text = """
                <html>
                  <body>
                    <table>
                      <tbody>
                        <tr>
                          <td>AGRN-2000</td>
                          <td>Flood</td>
                          <td>Test Flood</td>
                          <td>MockCouncil1</td>
                        </tr>
                      </tbody>
                    </table>
                  </body>
                </html>
                """
                self.status_code = 200

            def raise_for_status(self):
                if self.status_code != 200:
                    raise HTTPError("Not OK")

        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)


@pytest.fixture
def mock_requests_no_table(monkeypatch):
    """
    Mocks requests.get() to return a fake HTML with no <table>.
    """
    def fake_get(*args, **kwargs):
        class FakeResponse:
            def __init__(self):
                self.text = "<html><body>No table here!</body></html>"
                self.status_code = 200

            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)


def test_collector_success(s3_setup, set_env_vars, mock_requests_success):
    """
    Test a successful run of the collector, verifying it merges historical data
    with newly scraped data and writes to S3.
    """
    event = {}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert "Aggregated data saved" in response["body"]

    # Validate the new S3 object
    s3_client = s3_setup
    result = s3_client.get_object(Bucket="test-bucket", Key="test-output.json")
    output_content = json.loads(result["Body"].read().decode("utf-8"))

    # We expect 2 suburbs total: "TestCouncil" (historical) + "MockCouncil1"
    # (scraped)
    suburb_names = [entry["suburb"] for entry in output_content]
    assert "TestCouncil" in suburb_names
    assert "MockCouncil1" in suburb_names


def test_collector_missing_historical(
        s3_setup,
        set_env_vars,
        mock_requests_success):
    """
    If the historical file is missing, we should handle gracefully (empty list).
    """
    # Delete the historical file from S3
    s3_setup.delete_object(Bucket="test-bucket", Key="test-historical.json")

    event = {}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert "Aggregated data saved" in response["body"]


def test_collector_no_table(s3_setup, set_env_vars, mock_requests_no_table):
    """
    If there's no table in the HTML, we should see a console print
    but still proceed with empty new data.
    """
    event = {}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 200
    assert "Aggregated data saved" in response["body"]


def test_collector_scrape_failure(s3_setup, set_env_vars, monkeypatch):
    """
    If an HTTP error occurs (requests.get fails), we should return 500.
    """
    def fake_get_fail(*args, **kwargs):
        raise HTTPError("Mocked HTTP error")

    monkeypatch.setattr(requests, "get", fake_get_fail)

    event = {}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    assert "Error scraping live URL" in response["body"]


def test_collector_s3_write_failure(
        s3_setup,
        set_env_vars,
        mock_requests_success,
        monkeypatch):
    """
    If writing to S3 fails, we should return 500.
    """
    # Save the original boto3.client function
    orig_boto_client = boto3.client

    # Patch boto3.client so that any request for "s3" returns our existing
    # s3_setup client.
    monkeypatch.setattr(boto3,
                        "client",
                        lambda service,
                        *args,
                        **kwargs: s3_setup if service == "s3" else orig_boto_client(service,
                                                                                    *args,
                                                                                    **kwargs))

    # Patch the put_object method of our s3_setup client to raise an exception.
    monkeypatch.setattr(
        s3_setup, "put_object",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Mock S3 write error"))
    )

    event = {}
    context = {}
    response = lambda_handler(event, context)

    assert response["statusCode"] == 500
    assert "Error writing to S3" in response["body"]
