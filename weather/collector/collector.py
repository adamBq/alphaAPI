import asyncio
import json
import hashlib
import os
from collections import defaultdict
from playwright.async_api import async_playwright
import boto3

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
BUCKET_NAME = os.environ.get('S3_BUCKET', 'my-default-bucket')

# S3 object keys
HISTORICAL_KEY = "fy18-19_to_fy23-24_nsw_disasters.json"
CACHE_KEY = "nsw_disasters_cache.json"  # Just if you want to keep a separate cache
RANKINGS_KEY = "disaster_rankings.json"

# S3 client
s3_client = boto3.client("s3")

# URL to scrape
LIVE_URL = "https://www.nsw.gov.au/emergency/recovery/natural-disaster-declarations/fy-2024-25"

# ------------------------------------------
# Scrape live data
# ------------------------------------------
async def scrape_live_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 ..."
        })
        await page.goto(url, wait_until="networkidle")
        # Extract table data
        disaster_data = await page.evaluate("""
            () => {
                const data = [];
                document.querySelectorAll("tbody tr").forEach(row => {
                    const cells = row.querySelectorAll("td, th");
                    if (cells.length >= 5) {
                        data.push({
                            "AGRN": cells[0].innerText.trim(),
                            "disasterType": cells[1].innerText.trim(),
                            "disasterName": cells[2].innerText.trim(),
                            "localGovernmentArea": cells[3].innerText.trim(),
                            "assistanceAvailable": cells[4].innerText.trim()
                        });
                    }
                });
                return data;
            }
        """)
        await browser.close()
        return {
            "year": url.split("/")[-1],
            "last_updated": "2025-02-26T12:00:00Z",
            "disasters": disaster_data
        }

# ------------------------------------------
# Utility: load/save from S3
# ------------------------------------------
def load_s3_object(key):
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Could not load {key} from S3: {e}")
        return None

def save_s3_object(data, key):
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(data, indent=4)
        )
        logger.info(f"Saved {key} to bucket {BUCKET_NAME}.")
    except Exception as e:
        logger.error(f"Error saving {key} to S3: {e}")

# ------------------------------------------
# Aggregate
# ------------------------------------------
def aggregate_by_suburb(data_entries):
    from collections import defaultdict
    suburb_counts = defaultdict(int)
    suburb_disasters = defaultdict(set)

    for entry in data_entries:
        disasters = entry.get("disasters", [])
        for disaster in disasters:
            suburbs = disaster.get("localGovernmentArea", "").split("\n")
            for suburb in suburbs:
                suburb = suburb.strip()
                if suburb:
                    suburb_counts[suburb] += 1
                    suburb_disasters[suburb].add(disaster.get("disasterName", ""))

    aggregated = []
    for suburb in suburb_counts:
        aggregated.append({
            "suburb": suburb,
            "occurrences": suburb_counts[suburb],
            "disasterNames": list(suburb_disasters[suburb])
        })
    # sort descending
    aggregated.sort(key=lambda x: x["occurrences"], reverse=True)
    return aggregated

# ------------------------------------------
# Main script logic
# ------------------------------------------
def main():
    # 1) Scrape new data
    live_data = asyncio.run(scrape_live_data(LIVE_URL))
    if not live_data:
        logger.error("No live data scraped; exiting.")
        return

    # 2) Load historical data
    historical_data = load_s3_object(HISTORICAL_KEY) or []
    # historical_data is presumably a list. If your historical JSON structure
    # is different, adapt as needed.

    # 3) Combine them
    combined_data = historical_data + [live_data]

    # 4) Aggregate
    aggregated = aggregate_by_suburb(combined_data)

    # 5) Save to S3 with final name
    save_s3_object(aggregated, RANKINGS_KEY)
    logger.info("Aggregation complete.")

if __name__ == "__main__":
    main()


def lambda_handler(event, context):
    # For AWS Lambda usage: each invocation runs once
    return main()
