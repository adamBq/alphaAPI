import json
import boto3
import pandas as pd
import numpy as np

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

s3_bucket_name = "crime-data-bucket-raw-data"
dynamodb_table_name = "crime-data"
dlq_url = "https://sqs.ap-southeast-2.amazonaws.com/522814692697/crime-data-processing-dlq"
dlq_arn = "arn:aws:sqs:ap-southeast-2:522814692697:crime-data-processing-dlq"

table = dynamodb.Table(dynamodb_table_name)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def send_to_dlq(suburb):
    """
    Sends failed suburb processing jobs to the Dead Letter Queue
    """
    try:
        sqs.send_message(QueueUrl=dlq_url, MessageBody=json.dumps({"suburb" : suburb}))
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
            "Offence category" : "crime_type",
            "Subcategory" : "sub_crime_type",
        })

        suburbs = df["suburb"].unique()
        month_cols = [col for col in df.columns if col.startswith((
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
                total_num = int(row[month_cols].sum())
                total_num_crimes += total_num

                if crime_type not in crime_summary:
                    crime_summary[crime_type] = {"totalNum": 0}
                crime_summary[crime_type]["totalNum"] += total_num

                if pd.notna(sub_crime_type):
                    if sub_crime_type not in crime_summary[crime_type]:
                        crime_summary[crime_type][sub_crime_type] = {"totalNum" : 0}
                    crime_summary[crime_type][sub_crime_type]["totalNum"] += total_num

                    # Add per-year & per-month data
                    for year in years:
                        year_cols = [col for col in month_cols if col.endswith(str(year))]
                        per_year_total = int(row[year_cols].sum())

                        if year not in crime_summary[crime_type][sub_crime_type]:
                            crime_summary[crime_type][sub_crime_type][year] = {"totalNum": 0}

                        crime_summary[crime_type][sub_crime_type][year]["totalNum"] += per_year_total

                        # Add per-month data
                        for month_col in year_cols:
                            month = month_col.split()[0]  # Extract month name
                            per_month_count = int(row[month_col])

                            if month not in crime_summary[crime_type][sub_crime_type][year]:
                                crime_summary[crime_type][sub_crime_type][year][month] = 0

                            crime_summary[crime_type][sub_crime_type][year][month] += per_month_count

                    # Build crime trends
                    yearly_totals = {year: int(row[[col for col in month_cols if col.endswith(str(year))]].sum()) for year in years}
                    trend_df = pd.DataFrame(list(yearly_totals.items()), columns=["Year", "TotalCrimes"])
                    trend_df["Year"]  = trend_df["Year"].astype(int)

                    if len(trend_df) > 1:
                        x = trend_df["Year"]
                        y = trend_df["TotalCrimes"]
                        slope, _ = np.polyfit(x, y, 1)

                        first_year = trend_df.iloc[0]["TotalCrimes"]
                        last_year = trend_df.iloc[-1]["TotalCrimes"]
                        trend_percentage = ((last_year - first_year) / max(first_year, 1)) * 100

                        trend_df["MovingAvg"] = trend_df["TotalCrimes"].rolling(
                            window=min(5, len(trend_df)), min_periods=1).mean()

                        if trend_percentage > 5:
                            trend_category = "Increasing"
                        elif trend_percentage < -5:
                            trend_category = "Decreasing"
                        else:
                            trend_category = "Stable"

                        crime_trends.setdefault(crime_type, {})[sub_crime_type] = {
                            "trendSlope": float(round(slope, 2)),
                            "trendPercentage": float(round(trend_percentage, 2)),
                            "movingAvg": float(round(trend_df["MovingAvg"].iloc[-1], 2)),
                            "trendCategory": trend_category
                        }
                    else:
                        crime_trends.setdefault(
                            crime_type,
                            {})[sub_crime_type] = {
                            "trendSlope": None,
                            "trendPercentage": None,
                            "movingAvg": None,
                            "trendCategory": "not enough data"}
            item = {
                "suburb": suburb,
                "totalNumCrimes": total_num_crimes,
                "crimeSummary": json.dumps(crime_summary),
                "crimeTrends": json.dumps(crime_trends)
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
    print(f"event: {event}")
    # Detect if triggered by DLQ
    use_dlq = True  
    for record in event["Records"]:
        if record.get("eventSourceARN") == dlq_arn:
            use_dlq = False
            break
    
    suburbs = []
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

                if not result:
                    failed_suburbs.append(suburb)
        except Exception as e:
            print(f"Error processing record: {e}")
            failed_suburbs.extend(suburbs)
    
    if failed_suburbs and use_dlq:
        print(f"Sending failed suburbs to DLQ: {failed_suburbs}")
        for suburb in failed_suburbs:
            send_to_dlq(suburb)
    else:
        print(f"No failed suburbs")

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": "Data processed successfully"}
