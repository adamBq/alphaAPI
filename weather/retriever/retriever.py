import json
import os
import boto3

def lambda_handler(event, context):
    """
    Loads aggregated data (nsw_suburb_disaster_rankings.json) from S3,
    looks up a requested suburb, optionally returns highest suburb.
    """
    s3 = boto3.client("s3")
    bucket_name = os.environ.get("S3_BUCKET")
    rankings_key = os.environ.get("RANKINGS_KEY", "nsw_suburb_disaster_rankings.json")

    # -------------------------------------------------------
    # 1) Figure out where the input (suburb, includeHighest) is
    # -------------------------------------------------------
    if "httpMethod" in event or "rawPath" in event:
        # This is an API Gateway or Lambda URL invocation
        body = {}
        if "body" in event and event["body"]:
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError:
                # Return a 400 if JSON is invalid
                error_response = {"error": "Invalid JSON in request body."}
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(error_response)
                }
        requested_suburb = body.get("suburb")
        include_highest = body.get("includeHighest", False)
    else:
        # Possibly invoked directly (no API Gateway)
        requested_suburb = event.get("suburb")
        include_highest = event.get("includeHighest", False)

    # -------------------------------------------------------
    # 2) Load the JSON file from S3
    # -------------------------------------------------------
    try:
        response = s3.get_object(Bucket=bucket_name, Key=rankings_key)
        rankings_data = json.loads(response["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        msg = f"❌ Could not find {rankings_key} in bucket {bucket_name}."
        print(msg)
        error_response = {"error": msg}
        return _maybe_proxy_response(event, error_response, status_code=404)
    except Exception as e:
        msg = f"❌ Error reading {rankings_key} from S3: {e}"
        print(msg)
        error_response = {"error": msg}
        return _maybe_proxy_response(event, error_response, status_code=500)

    # -------------------------------------------------------
    # 3) Validate the data
    # -------------------------------------------------------
    if not isinstance(rankings_data, list):
        error_response = {"error": "Invalid format of the rankings file (expected a JSON list)."}
        return _maybe_proxy_response(event, error_response, status_code=500)

    # -------------------------------------------------------
    # 4) Check suburb
    # -------------------------------------------------------
    if not requested_suburb:
        error_response = {"error": "No suburb specified in the request."}
        return _maybe_proxy_response(event, error_response, status_code=400)

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

    # -------------------------------------------------------
    # 5) Include highest suburb if requested
    # -------------------------------------------------------
    if include_highest and rankings_data:
        highest_suburb_entry = rankings_data[0]
        response_payload["highestSuburbData"] = {
            "suburb": highest_suburb_entry["suburb"],
            "occurrences": highest_suburb_entry["occurrences"],
            "disasterNames": highest_suburb_entry["disasterNames"]
        }

    # -------------------------------------------------------
    # 6) Return final response
    # -------------------------------------------------------
    return _maybe_proxy_response(event, response_payload, status_code=200)


def _maybe_proxy_response(event, payload, status_code):
    """
    Helper function: if it's an HTTP invocation (API Gateway),
    wrap the payload in statusCode/body; else return raw dict.
    """
    if "httpMethod" in event or "rawPath" in event:
        return {
            "statusCode": status_code,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",  
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            },
            "body": json.dumps(payload)
        }
    else:
        return payload
