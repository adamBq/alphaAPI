
import os
import json
import sys
import boto3
import pandas as pd
import urllib.parse
from io import StringIO

s3_client = boto3.client('s3')

S3_BUCKET_NAME = 'family-data-alpha'
S3_CSV_KEY = '2021Census_G17C_NSW_SAL.csv'
S3_CODES_KEY = 'suburb_codes.py'

INCOME_BRACKETS = {
    "650_799": ("P_650_799_Tot", 725),
    "800_999": ("P_800_999_Tot", 900),
    "1000_1249": ("P_1000_1249_Tot", 1125),
    "1250_1499": ("P_1250_1499_Tot", 1375),
    "1500_1749": ("P_1500_1749_Tot", 1625),
    "1750_1999": ("P_1750_1999_Tot", 1875),
    "2000_2999": ("P_2000_2999_Tot", 2500),
    "3000_3499": ("P_3000_3499_Tot", 3250),
    "3500_more": ("P_3500_more_Tot", 3750)
}

def get_income_data(
    suburb_name,
    bucket_name=S3_BUCKET_NAME,
    csv_key=S3_CSV_KEY,
    codes_key=S3_CODES_KEY):

    try:
        codes_response = s3_client.get_object(
            Bucket=bucket_name, Key=codes_key)
        codes_str = codes_response['Body'].read().decode('utf-8')

        code_namespace = {}
        exec(codes_str, code_namespace)

        if "SUBURB_CODES_MAP" not in code_namespace:
            return json.dumps(
                {"error": "SUBURB_CODES_MAP not found in suburb_codes.py"}, indent=4)

        suburb_codes_map = code_namespace["SUBURB_CODES_MAP"]

    except Exception as e:
        return json.dumps(
            {"error": f"Failed to read/execute suburb_codes.py from S3: {e}"}, indent=4)

    name_to_code = {v.lower(): k for k, v in suburb_codes_map.items()}
    suburb_code = name_to_code.get(suburb_name.lower())

    if not suburb_code:
        return json.dumps(
            {"error": f"Suburb code not found for '{suburb_name}'."}, indent=4)

    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=csv_key)
        df = pd.read_csv(response['Body'])
    except Exception as e:
        return json.dumps(
            {"error": f"Failed to read CSV file from S3: {e}"}, indent=4)

    filtered_df = df[df["SAL_CODE_2021"] == "SAL" + suburb_code]
    if filtered_df.empty:
        return json.dumps(
            {"error": f"No data found for suburb code '{suburb_code}'."}, indent=4)

    row = filtered_df.iloc[0]
    total_population = int(row["P_Tot_Tot"]) if "P_Tot_Tot" in row else 0
    income_not_stated = int(row["P_PI_NS_Tot"]) if "P_PI_NS_Tot" in row else 0

    result = {
        "suburb": suburb_name,
        "suburb_code": "SAL" + suburb_code
    }

    weighted_total = 0

    for key, (col, midpoint) in INCOME_BRACKETS.items():
        count = int(row[col]) if col in row else 0
        result[f"{key} range"] = count
        weighted_total += count * midpoint

    result["Partial_income_not_stated"] = income_not_stated
    result["Total_population"] = total_population

    if total_population > 0:
        avg_income = round(weighted_total / total_population)
    else:
        avg_income = "Unavailable"

    result["average_income_range"] = avg_income

    return json.dumps(result, indent=4)

def lambda_handler(event, context):
    try:
        suburb_encoded = event["pathParameters"]["suburb"]
        suburb = urllib.parse.unquote(suburb_encoded)
        if not suburb:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                },
                "body": json.dumps({"error": "No suburb provided in event"})
            }

        response_json = get_income_data(suburb)
        response_obj = json.loads(response_json)

        if "error" in response_obj and "not found" in response_obj["error"].lower():
            return {
                "statusCode": 404,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                },
                "body": response_json
            }
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            },
            "body": response_json
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*"
            },
            "body": json.dumps({"error": f"Error processing the request: {str(e)}"})
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python income.py <suburb name>")
    else:
        test_suburb = sys.argv[1]
        result = get_income_data(test_suburb)
        print(result)