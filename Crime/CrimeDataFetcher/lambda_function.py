import json
import boto3
from util.config import config
from crime_fetcher import fetch

s3 = boto3.client("s3")
s3_bucket_name = config.get("S3_BUCKET_NAME")

sqs = boto3.client("sqs")
sqs_queue_url = config.get("SQS_QUEUE_URL")
batch_size = config.get("BATCH_SIZE")

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
        return {"statusCode" : 500, "body" : "Error fetching crime data"}
    
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
            batch_suburbs = suburbs[i : i + batch_size]
            message_body = json.dumps({"suburbs" : batch_suburbs.tolist()})

            sqs.send_message(QueueUrl=sqs_queue_url, MessageBody=message_body)
            print(f"Queued jobs for {batch_suburbs} to SQS")
            
        print("Data uploaded and queued successfully")
    except Exception as e:
        print(f"Error uploading data: {e}")
        return {"statusCode" : 500, "body" : "Error uploading data"}
    
    return {"statusCode" : 200, "body" : "Data fetched successfully"}
    