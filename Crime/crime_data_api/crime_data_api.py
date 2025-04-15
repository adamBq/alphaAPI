import json
import boto3
import traceback
import decimal
import urllib.parse

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("crime-data")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

def convert_decimal(obj):
    """Recursively converts Decimal to float or int for JSON serialization."""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, decimal.Decimal):
        return float(obj) if obj % 1 else int(obj)  # Convert to int if it's a whole number
    return obj

def parse_json_fields(item, fields_to_parse=["crimeSummary", "crimeTrends"]):
    """Parses stringified JSON fields into actual dictionaries."""
    for field in fields_to_parse:
        if field in item and isinstance(item[field], str):  # Ensure field exists and is a string
            try:
                item[field] = json.loads(item[field])  # Convert to dictionary
            except json.JSONDecodeError:
                pass  # If parsing fails, leave it as a string
    return item

def filter_summary_data(data):
    """
    Removes per-year and per-month breakdown if detailed=False
    """
    try:
        crime_summary = json.loads(data["crimeSummary"])

        for crime_type in crime_summary:
            for sub_crime in crime_summary[crime_type]:
                if isinstance(crime_summary[crime_type][sub_crime], dict):
                    crime_summary[crime_type][sub_crime] = {
                        "totalNum": crime_summary[crime_type][sub_crime]["totalNum"]}

        data["crimeSummary"] = json.dumps(crime_summary)
        return data
    except Exception as e:
        print(f"Error filtering summary data: {e}")
        return data


def lambda_handler(event, context):
    """
    Fetches crime data for a given suburb from DynamoDB
    """
    try:
        print(json.dumps(event))
        suburb_encoded = event["pathParameters"].get("suburb")
        suburb = None
        if (suburb_encoded is not None):
            suburb = urllib.parse.unquote(suburb_encoded)
            
        query_params = event.get("queryStringParameters", {})
        detailed = True
        if query_params:
            detailed = str(query_params.get("detailed", "true")).lower() == "true"
        
        if not suburb:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps(
                {"error": "Missing required parameter : suburb"})}

        # Fetch data from DynamoDB
        response = table.get_item(Key={"suburb": suburb})

        if "Item" not in response:
            return {
                "statusCode" : 404,
                "headers" : CORS_HEADERS,
                "body" : json.dumps({"error" : f"No data found for suburb: {suburb}"})
            }
        item = response["Item"]

        if not detailed:
            item = filter_summary_data(item)


        print(f"item: \n{item}")
        return {
            "statusCode" : 200,
            "headers" : CORS_HEADERS,
            "body": json.dumps(convert_decimal(parse_json_fields(item)))
        }

    except Exception as e:
        print(f"Error fetching data: {e}")
        traceback.print_exc()
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
