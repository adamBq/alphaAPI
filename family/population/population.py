import os
import pandas as pd
import json
import sys
import boto3
from io import StringIO

s3_client = boto3.client('s3')

S3_BUCKET_NAME = 'paige-3011'
S3_CSV_KEY = '2021Census_G01_NSW_SAL.csv'
S3_CODES_KEY = 'suburb_codes.py'


def get_suburb_population(
        suburb_name,
        bucket_name=S3_BUCKET_NAME,
        csv_key=S3_CSV_KEY,
        codes_key=S3_CODES_KEY):
    """
    1. Fetch suburb_codes.py from S3, exec it to load SUBURB_CODES_MAP.
    2. Fetch the census CSV from S3.
    3. Filter the CSV by the suburb code and return the population info as JSON.
    """

    try:
        codes_response = s3_client.get_object(
            Bucket=bucket_name, Key=codes_key)
        codes_str = codes_response['Body'].read().decode('utf-8')

        code_namespace = {}
        exec(codes_str, code_namespace)

        if "SUBURB_CODES_MAP" not in code_namespace:
            return json.dumps(
                {"error": "No SUBURB_CODES_MAP found in suburb_codes.py"})

        suburb_codes_map = code_namespace["SUBURB_CODES_MAP"]

    except Exception as e:
        return json.dumps(
            {"error": f"Failed to read/execute suburb_codes.py from S3: {e}"})

    name_to_code = {v: k for k, v in suburb_codes_map.items()}

    suburb_code = name_to_code.get(suburb_name)
    if not suburb_code:
        return json.dumps(
            {"error": f"Suburb code not found for '{suburb_name}'."})

    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=csv_key)
        df = pd.read_csv(response['Body'])
    except Exception as e:
        return json.dumps({"error": f"Failed to read CSV file from S3: {e}"})

    filtered_df = df[df["SAL_CODE_2021"] == "SAL" + suburb_code]
    if filtered_df.empty:
        return json.dumps(
            {"error": f"No data found for suburb with code '{suburb_code}'."})

    tot_p_m = filtered_df["Tot_P_M"].sum()
    tot_p_f = filtered_df["Tot_P_F"].sum()

    result = {
        "suburb": suburb_name,
        "totalPopulation": int(tot_p_m + tot_p_f),
        "male": int(tot_p_m),
        "female": int(tot_p_f)
    }
    return json.dumps(result, indent=4)


def lambda_handler(event, context):
    print("Received event: ", json.dumps(event))
    try:
        suburb = event.get("pathParameters", {}).get("suburb")
        if not suburb:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No suburb provided in event"})
            }
        response_json = get_suburb_population(suburb)
        response_obj = json.loads(response_json)

        if "error" in response_obj and "not found" in response_obj["error"].lower(
        ):
            return {
                "statusCode": 404,
                "body": response_json
            }

        return {
            "statusCode": 200,
            "body": response_json
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"An error occurred: {str(e)}"})
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python population.py <suburb>")
    else:
        suburb = sys.argv[1]
        output = get_suburb_population(suburb)
        print(output)
