import json
import os
import boto3
import requests
from bs4 import BeautifulSoup
from collections import defaultdict

def lambda_handler(event, context):
    """
    Example container-based Lambda that:
      1) Reads historical JSON data from S3.
      2) Scrapes FY 2024-25 data from a website.
      3) Aggregates by suburb.
      4) Writes the aggregated output back to S3.

    Expects environment variables:
      - S3_BUCKET: Name of the S3 bucket
      - HISTORICAL_KEY: S3 key for the historical JSON
      - OUTPUT_KEY: S3 key for the output JSON
      - LIVE_URL: The URL to scrape for 2024-25 data
    """

    # ----------------------------------------
    # 1) Configuration & S3 download
    # ----------------------------------------
    s3 = boto3.client("s3")
    bucket_name = os.environ.get("S3_BUCKET")
    historical_key = os.environ.get("HISTORICAL_KEY", "fy18-19_to_fy23-24_nsw_disasters.json")
    output_key = os.environ.get("OUTPUT_KEY", "nsw_suburb_disaster_rankings.json")
    live_url = os.environ.get("LIVE_URL", "https://www.nsw.gov.au/emergency/recovery/natural-disaster-declarations/fy-2024-25")
    last_updated = "2025-02-25T12:00:00Z"  # Example fixed date, can be dynamic

    # Download historical data from S3
    try:
        response = s3.get_object(Bucket=bucket_name, Key=historical_key)
        historical_data = json.loads(response["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        print(f"⚠️ Historical file '{historical_key}' not found in bucket '{bucket_name}'. Using empty list.")
        historical_data = []
    except Exception as e:
        print(f"❌ Could not read historical data. Error: {e}")
        return {
            "statusCode": 500,
            "body": f"Error reading historical data from S3: {e}"
        }

    # ----------------------------------------
    # 2) Scrape the 2024-25 live data
    # ----------------------------------------
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(live_url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Could not scrape live URL. Error: {e}")
        return {
            "statusCode": 500,
            "body": f"Error scraping live URL: {e}"
        }

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    live_disaster_data = []

    if table:
        tbody = table.find("tbody")
        if tbody:
            rows = tbody.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 4:
                    agrn = cells[0].get_text(strip=True)
                    disaster_type = cells[1].get_text(strip=True)
                    disaster_name = cells[2].get_text(strip=True)
                    local_government_area = cells[3].get_text(strip=True)
                    live_disaster_data.append({
                        "AGRN": agrn,
                        "disasterType": disaster_type,
                        "disasterName": disaster_name,
                        "localGovernmentArea": local_government_area
                    })
    else:
        print("❌ No table found on the live data page.")
        # Continue but note we have no new data
    live_data = {
        "year": live_url.split("/")[-1],  # e.g. "fy-2024-25"
        "last_updated": last_updated,
        "disasters": live_disaster_data
    }

    # ----------------------------------------
    # 3) Combine with historical data
    # ----------------------------------------
    combined_data = historical_data + [live_data]

    # ----------------------------------------
    # 4) Aggregate by suburb
    # ----------------------------------------
    suburb_counts = defaultdict(int)
    suburb_disasters = defaultdict(set)

    for entry in combined_data:
        for disaster in entry.get("disasters", []):
            # localGovernmentArea might contain multiple lines
            suburbs = disaster.get("localGovernmentArea", "").split("\n")
            for suburb in suburbs:
                suburb = suburb.strip()
                if suburb:
                    suburb_counts[suburb] += 1
                    suburb_disasters[suburb].add(disaster.get("disasterName", ""))

    aggregated = []
    for suburb, count in suburb_counts.items():
        aggregated.append({
            "suburb": suburb,
            "occurrences": count,
            "disasterNames": list(suburb_disasters[suburb])
        })

    # Sort descending by occurrences
    aggregated.sort(key=lambda x: x["occurrences"], reverse=True)

    # ----------------------------------------
    # 5) Save aggregated data back to S3
    # ----------------------------------------
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=output_key,
            Body=json.dumps(aggregated, indent=4).encode("utf-8"),
            ContentType="application/json"
        )
        msg = f"✅ Aggregated data saved to s3://{bucket_name}/{output_key}"
        print(msg)
        return {
            "statusCode": 200,
            "body": msg
        }
    except Exception as e:
        print(f"❌ Error writing aggregated data to S3: {e}")
        return {
            "statusCode": 500,
            "body": f"Error writing to S3: {e}"
        }
    