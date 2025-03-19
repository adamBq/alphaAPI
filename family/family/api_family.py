import os
import json
import sys
import boto3
import pandas as pd
from io import StringIO

s3_client = boto3.client('s3')

S3_BUCKET_NAME = 'paige-3011'
S3_CSV_KEY = '2021Census_G29_NSW_SAL.csv'
S3_CODES_KEY = 'suburb_codes.py'

def get_family_data(suburb_name, bucket_name=S3_BUCKET_NAME, csv_key=S3_CSV_KEY, codes_key=S3_CODES_KEY):
  """
  1. Fetch suburb_codes.py from S3, exec it to load SUBURB_CODES_MAP.
  2. Fetch the Census CSV (G29) from S3.
  3. Filter the CSV by the suburb code and return the family data info as JSON.
  """

  try:
    codes_response = s3_client.get_object(Bucket=bucket_name, Key=codes_key)
    codes_str = codes_response['Body'].read().decode('utf-8')

    code_namespace = {}

    exec(codes_str, code_namespace)

    if "SUBURB_CODES_MAP" not in code_namespace:
      return json.dumps({"error": "SUBURB_CODES_MAP not found in suburb_codes.py"}, indent=4)

    suburb_codes_map = code_namespace["SUBURB_CODES_MAP"]

  except Exception as e:
    return json.dumps({"error": f"Failed to read/execute suburb_codes.py from S3: {e}"}, indent=4)

  name_to_code = {v.lower(): k for k, v in suburb_codes_map.items()}

  suburb_code = name_to_code.get(suburb_name.lower())
  if not suburb_code:
    return json.dumps({"error": f"Suburb code not found for '{suburb_name}'."}, indent=4)

  try:
    response = s3_client.get_object(Bucket=bucket_name, Key=csv_key)
    df = pd.read_csv(response['Body'])
  except Exception as e:
    return json.dumps({"error": f"Failed to read CSV file from S3: {e}"}, indent=4)

  filtered_df = df[df["SAL_CODE_2021"] == "SAL" + suburb_code]
  if filtered_df.empty:
    return json.dumps({"error": f"No data found for suburb code '{suburb_code}'."}, indent=4)

  def sum_columns(*cols):
    total = 0
    for col in cols:
      if col in filtered_df.columns:
        total += filtered_df[col].sum()
    return int(total)

  result = {
    "suburb": suburb_name,
    "totalFamilies": sum_columns("Total_F", "Total_P"),
    "coupleFamilyWithNoChildren": sum_columns("CF_no_children_F", "CF_no_children_P"),
    "coupleFamilyWithChildrenUnder15": sum_columns("CF_ChU15_a_Total_F", "CF_ChU15_a_Total_P"),
    "coupleFamilyWithChildrenOver15": sum_columns("CF_no_ChU15_a_Total_F", "CF_no_ChU15_a_Total_P"),
    "totalCoupleFamilies": sum_columns("CF_Total_F", "CF_Total_P"),
    "oneParentWithChildrenUnder15": sum_columns("OPF_ChU15_a_Total_F", "OPF_ChU15_a_Total_P"),
    "oneParentWithChildrenOver15": sum_columns("OPF_no_ChU15_a_Total_F", "OPF_no_ChU15_a_Total_P"),
    "totalOneParentFamilies": sum_columns("OPF_Total_F", "OPF_Total_P"),
    "otherFamily": sum_columns("Other_family_F", "Other_family_P")
  }

  return json.dumps(result, indent=4)

def lambda_handler(event, context):
  """
  AWS Lambda handler:
  1. Reads 'suburb' from the event's pathParameters (assuming API Gateway usage).
  2. Calls get_family_data to fetch data from S3 and filter.
  3. Returns an HTTP-style response.
  """

  suburb = event["pathParameters"]["suburb"]
  if not suburb:
    return {
      "statusCode": 400,
      "body": json.dumps({"error": "No suburb provided in event"})
    }

  response_json = get_family_data(suburb)
  return {
    "statusCode": 200,
    "body": response_json
  }

if __name__ == "__main__":
  if len(sys.argv) < 2:
    print("Usage: python api_family_data.py <suburb>")
  else:
    test_suburb = sys.argv[1]
    result = get_family_data(test_suburb)
    print(result)
