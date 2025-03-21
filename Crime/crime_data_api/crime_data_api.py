import json
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("CrimeData")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

def filter_summary_data(data):
    """
    Removes per-year and per-month breakdown if detailed=False
    """
    try:
        crime_summary = json.loads(data["crimeSummary"])

        for crime_type in crime_summary:
            for sub_crime in crime_summary[crime_type]:
                if isinstance(crime_summary[crime_type][sub_crime], dict):
                    crime_summary[crime_type][sub_crime] = {"totalNum" : crime_summary[crime_type][sub_crime]["totalNum"]}
        
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
        query_params = event.get("queryStringParameters", {})
        suburb = query_params.get("suburb")
        detailed = query_params.get("detailed", "true").lower() == "true"

        if not suburb:
            return {
                "statusCode" : 400,
                "headers" : CORS_HEADERS,
                "body" : json.dumps({"error" : "Missing required parameter : suburb"})
            }
        
        # Fetch data from DynamoDB
        response = table.get_item(Key={"suburb" : suburb})

        if "Item" not in response:
            return {
                "statusCode" : 404,
                "headers" : CORS_HEADERS,
                "body" : json.dumps({"error" : f"No data found for suburb: {suburb}"})
            }
        
        return {
            "statusCode" : 200,
            "heders" : CORS_HEADERS,
            "body" : json.dumps(response["Item"])
        }
        
    except Exception as e:
        return {
            "statusCode" : 400,
            "headers" : CORS_HEADERS,
            "body" : json.dumps({"error" : str(e)})
        }