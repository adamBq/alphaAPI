import json
import os
import boto3


def lambda_handler(event, context):
    """
    Loads aggregated data (nsw_suburb_disaster_rankings.json) from S3,
    looks up a requested suburb from the event, and optionally includes
    the highest-ranking suburb if event["includeHighest"] is True.
    """
    s3 = boto3.client("s3")
    bucket_name = os.environ.get("S3_BUCKET")
    rankings_key = os.environ.get(
        "RANKINGS_KEY",
        "nsw_suburb_disaster_rankings.json")

    requested_suburb = event.get("suburb")
    include_highest = event.get("includeHighest", False)

    # Read the JSON file from S3
    try:
        response = s3.get_object(Bucket=bucket_name, Key=rankings_key)
        rankings_data = json.loads(response["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        msg = f"❌ Could not find {rankings_key} in bucket {bucket_name}."
        print(msg)
        error_response = {"error": msg}
        # Decide which format to return based on the event
        if "httpMethod" in event or "rawPath" in event:
            return {
                "statusCode": 404,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_response)
            }
        else:
            return error_response
    except Exception as e:
        msg = f"❌ Error reading {rankings_key} from S3: {e}"
        print(msg)
        error_response = {"error": msg}
        if "httpMethod" in event or "rawPath" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_response)
            }
        else:
            return error_response

    # Basic validation
    if not isinstance(rankings_data, list):
        error_response = {
            "error": "Invalid format of the rankings file (expected a JSON list)."}
        if "httpMethod" in event or "rawPath" in event:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_response)
            }
        else:
            return error_response

    # If no suburb specified, return an error
    if not requested_suburb:
        error_response = {"error": "No suburb specified in the request."}
        if "httpMethod" in event or "rawPath" in event:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_response)
            }
        else:
            return error_response

    found_suburb_data = None
    for entry in rankings_data:
        if entry.get("suburb", "").lower() == requested_suburb.lower():
            found_suburb_data = entry
            break

    response_payload = {}
    if found_suburb_data:
        response_payload["status"] = "success"
        response_payload["message"] = f"Data found for suburb '{requested_suburb}'."
        response_payload["requestedSuburbData"] = found_suburb_data
    else:
        response_payload["status"] = "not_found"
        response_payload["message"] = f"No data found for suburb '{requested_suburb}'."

    # If user wants the highest suburb data
    if include_highest and rankings_data:
        highest_suburb_entry = rankings_data[0]
        response_payload["highestSuburbData"] = {
            "suburb": highest_suburb_entry["suburb"],
            "occurrences": highest_suburb_entry["occurrences"],
            "disasterNames": highest_suburb_entry["disasterNames"]
        }

    # If the event is coming from an HTTP source (API Gateway or Lambda Function URL),
    # return the wrapped response. Otherwise, return the raw JSON object.
    if "httpMethod" in event or "rawPath" in event:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_payload)
        }
    else:
        return response_payload
