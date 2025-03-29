import json
import boto3
import requests
import zipfile
import io
import pandas as pd

s3 = boto3.client("s3")
s3_bucket_name = "crime-data-bucket-raw-data"

sqs = boto3.client("sqs")
sqs_queue_url = "https://sqs.ap-southeast-2.amazonaws.com/522814692697/crime-data-processing-queue"
batch_size = 10

CRIME_DATA_URL = "https://bocsarblob.blob.core.windows.net/bocsar-open-data/SuburbData.zip"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def fetch():
    """
    This method will download the crime data ZIP file, extract the CSV file
    and load it into a pandas DataFrame.

    Returns:
        crime_data: The crime data in a pandas DataFrame
    """
    try:
        print("Downloading crime data...")

        response = requests.get(CRIME_DATA_URL)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zip_ref:
            csv_filename = zip_ref.namelist()[0]
            with zip_ref.open(csv_filename) as file:
                crime_data = pd.read_csv(file)

        print("Crime data downloaded successfully.")
        return crime_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching crime data: {e}")
        return None
    except zipfile.BadZipFile as e:
        print(f"Error extracting ZIP file: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def lambda_handler(event, context):
    """
    This lambda will be called through an AWS EventBridge which will be invoked
    once a year. The lambda will fetch the data from the source, add it in S3
    and then queue jobs to an SQS for worker lambdas to process.
    """
    # ====================
    # Fetch data from source
    # ====================
    crime_data = fetch()
    if crime_data is None:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": "Error fetching crime data"}

    # ====================
    # Upload and Queue Data
    # ====================
    try:
        suburbs = crime_data["Suburb"].unique()

        # Upload raw data to S3
        for suburb in suburbs:
            suburb_df = crime_data[crime_data["Suburb"] == suburb]
            file_key = f"raw_data/{suburb.replace(' ', '_')}.json"
            json_data = suburb_df.to_json(orient="records")

            s3.put_object(Bucket=s3_bucket_name, Key=file_key, Body=json_data)
            print(f"Uploaded raw data for {suburb} to S3")

        # Queue jobs to SQS
        for i in range(0, len(suburbs), batch_size):
            batch_suburbs = suburbs[i: i + batch_size]
            message_body = json.dumps({"suburbs": batch_suburbs.tolist()})

            sqs.send_message(QueueUrl=sqs_queue_url, MessageBody=message_body)
            print(f"Queued jobs for {batch_suburbs} to SQS")

        print("Data uploaded and queued successfully")
    except Exception as e:
        print(f"Error uploading data: {e}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": "Error uploading data"}

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": "Data fetched successfully"}
