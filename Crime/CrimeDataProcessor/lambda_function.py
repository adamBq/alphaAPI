import json
import boto3
import pandas as pd
import numpy as np
from util.config import config

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

s3_bucket_name = config.get("S3_BUCKET_NAME")
dynamodb_table_name = config.get("DYNAMODB_TABLE_NAME")
dlq_url = config.get("DLQ_URL")

table = dynamodb.Table(dynamodb_table_name)

def send_to_dlq(suburb):
    """
    Sends failed suburb processing jobs to the Dead Letter Queue
    """
    try:
        sqs.send_messaeg(QueueUrl=dlq_url, MessageBody=json.dumps({"suburb" : suburb}))
        print(f"Sent message to DLQ for suburb: {suburb}")
    except Exception as e:
        print(f"Error sending message to DLQ: {e}")

def fetch_suburb_data(suburb):
    """
    Fetches the raw data for a given suburb from S3
    """
    try:
        key = f"raw_data/{suburb.replace(' ', '_')}.json"
        response = s3.get_object(Bucket=s3_bucket_name, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return pd.DataFrame(data)
    except s3.exceptions.NoSuchKey as e:
        print(f"Error fetching data for {suburb}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching data for {suburb}: {e}")
        return None

def process_and_store_crime_data(df):
    """
    Processes the crime data and stores it in DynamoDB
    """
    try:
        df = df.rename(columns={
            "Suburb" : "suburb",
            "Offence Category" : "crime_type",
            "Subcategory" : "sub_crime_type",
        })

        suburbs = df["suburb"].unique()
        month_cols = [col for col in df.columns if col.startsWith((
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ))]
        years = sorted(set(int(col.split()[-1]) for col in month_cols))

        for suburb in suburbs:
            suburb_df = df[df["suburb"] == suburb]
            
            crime_summary = {}
            crime_trends = {}
            total_num_crimes = 0

            for _, row in suburb_df.iterrows():
                crime_type = row["crime_type"]
                sub_crime_type = row["sub_crime_type"]
                total_num = int(row(month_cols).sum())
                total_num_crimes += total_num

                if crime_type not in crime_summary:
                    crime_summary[crime_type] = {"totalNum" : 0}
                crime_summary[crime_type]["totalNum"] += total_num

                if pd.notna(sub_crime_type):
                    if sub_crime_type not in crime_summary[crime_type]:
                        crime_summary[crime_type][sub_crime_type] = 0
                    crime_summary[crime_type][sub_crime_type] += total_num

                    # Build crime trends
                    yearly_totals = {year: int(row[[col for col in month_cols if col.endswith(str(year))]].sum()) for year in years}
                    trend_df = pd.DataFrame(yearly_totals.items(), columns=["Year", "TotalCrimes"])
                    trend_df["Year"]  = trend_df["Year"].astype(int)

                    if len(trend_df) > 1:
                        x = trend_df["Year"]
                        y = trend_df["TotalCrimes"]
                        slope, _ = np.polyfit(x, y, 1)

                        first_year = trend_df.iloc[0]["TotalCrimes"]
                        last_year = trend_df.iloc[-1]["TotalCrimes"]
                        trend_percentage = ((last_year - first_year) . max(first_year, 1)) * 100

                        trend_df["MovingAvg"] = trend_df["TotalCrimes"].rolling(window=min(5, len(trend_df)), min_periods=1).mean()

                        if trend_percentage > 5:
                            trend_category = "Increasing"
                        elif trend_percentage < -5:
                            trend_category = "Decreasing"
                        else:
                            trend_category = "Stable"
                        
                        crime_trends.setdefault(crime_type, {})[sub_crime_type] = {
                            "trendSlope" : float(round(slope, 2)),
                            "trendPercentage" : float(round(trend_percentage, 2)),
                            "movingAvg" : float(round(trend_df["MovingAvg"].iloc[-1], 2)),
                            "trendCategory" : trend_category
                        }
                    else:
                        crime_trends.setdefault(crime_type, {})[sub_crime_type] = {
                            "trendSlope": None,
                            "trendPercentage": None,
                            "movingAvg": None,
                            "trendCategory": "not enough data"
                        }
            item = {
                "suburb" : suburb,
                "totalNumCrimes" : total_num_crimes,
                "crimeSummary" : json.dumps(crime_summary),
                "crimeTrends" : json.dumps(crime_trends)
            }           

            table.put_item(Item=item)
            print(f"Stored data for {suburb} in DynamoDB")
        return True
    except Exception as e:
        print(f"Error processing data: {e}")
        return None

def lambda_handler(event, context):
    """
    SQS-triggered Lambda worker that processes suburb crime data from S3
    and saves it to DynamoDB.
    """
    failed_suburbs = []

    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
            suburbs = message["suburbs"]

            for suburb in suburbs:
                print(f"Processing data for suburb: {suburb}...")
                df = fetch_suburb_data(suburb)

                if df is None:
                    print(f"Error fetching data for {suburb}")
                    continue

                result = process_and_store_crime_data(df)

                if not result["jobSuccess"]:
                    failed_suburbs.append(suburb)
        except Exception as e:
            print(f"Error processing record: {e}")
            failed_suburbs.extend(suburbs)
    
    if failed_suburbs:
        print(f"Sending failed suburbs to DLQ: {failed_suburbs}")
        for suburb in failed_suburbs:
            send_to_dlq(suburb)
    else:
        print(f"No failed suburbs")
    
    return {"statusCode" : 200, "body" : "Data processed successfully"}
