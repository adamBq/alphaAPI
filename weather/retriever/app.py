from fastapi import FastAPI, HTTPException
import boto3
import os
import json
import logging

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

app = FastAPI()

BUCKET_NAME = os.environ.get("S3_BUCKET", "my-default-bucket")
RANKINGS_KEY = "disaster_rankings.json"

s3_client = boto3.client("s3")

def load_s3_object(key):
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        logger.error(f"Error loading {key} from S3: {e}")
        return None

@app.get("/suburbs/{suburb_name}")
def get_suburb(suburb_name: str):
    """
    Returns details about the requested suburb, plus
    also returns the suburb with highest occurrences.
    If the requested suburb is not found, return that as null
    plus the highest-occurrence suburb.
    """
    data = load_s3_object(RANKINGS_KEY)
    if data is None:
        raise HTTPException(status_code=500, detail="Aggregated data not found.")

    if not data:
        # If there's no data at all in the file, just return an empty structure
        return {"message": "No data available."}

    # The highest-occurrence suburb (assuming data is sorted descending by occurrences).
    top_suburb = data[0] if len(data) > 0 else None

    # Find the requested suburb (case-insensitive).
    found_suburb = None
    for record in data:
        if record["suburb"].lower() == suburb_name.lower():
            found_suburb = record
            break

    if found_suburb is None:
        # Return shape { "MyBadSuburb": null, "suburb_with_highest_occurrences": {...} }
        return {
            suburb_name: None,
            "suburb_with_highest_occurrences": top_suburb
        }
    else:
        # Return shape with full info + top suburb
        return {
            "suburb": found_suburb["suburb"],
            "occurrences": found_suburb["occurrences"],
            "disasterNames": found_suburb["disasterNames"],
            "suburb_with_highest_occurrences": top_suburb
        }

# Optionally a root endpoint for health checks
@app.get("/")
def index():
    return {"message": "Retriever service is running"}


from mangum import Mangum

handler = Mangum(app)

def lambda_handler(event, context):
    return handler(event, context)

