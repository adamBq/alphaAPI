import json
import boto3
from util.config import config

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(config.get("DYNAMODB_TABLE_NAME"))

def lambda_handler(event, context):
    """
    Fetches crime data for a given suburb from DynamoDB
    """
    try:
        query_params = event.get("queryStringParameters", {})
        suburb = query_params.get("suburb")

        if not suburb:
            return {
                "statusCode" : 400,
                "body" : json.dumps({"error" : "Missing required parameter : suburb"})
            }
        
        # Fetch data from DynamoDB
        response = table.get_item(Key={"suburb" : suburb})

        if "Item" not in response:
            return {
                "statusCode" : 404,
                "body" : json.dumps({"error" : f"No data found for suburb: {suburb}"})
            }
        
        return {
            "statusCode" : 200,
            "body" : json.dumps(response["Item"])
        }
        
    except Exception as e:
        return {
            "statusCode" : 400,
            "body" : json.dumps({"error" : str(e)})
        }