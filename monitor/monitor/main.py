import boto3
import os
import requests
from requests.exceptions import HTTPError

API_ENDPOINT = 'https://m42dj4mgj8.execute-api.ap-southeast-2.amazonaws.com/prod/'
SNS_ARN = 'arn:aws:sns:ap-southeast-2:522814692697:alphaAPI_Topic'
HEADERS = {
        "Content-Type": "application/json",
        "x-api-key": os.environ(["AWS_API_KEY"])
    }
sns = boto3.client('sns')

def send_notification(subject, message):
    sns.publish(
        TopicArn=SNS_ARN,
        Message=message,
        Subject=subject
    )

def check_api(api, body=None, headers=None):
    url = API_ENDPOINT + api

    try:
        if not body:
            response = requests.get(url, headers=HEADERS)
        else:
            response = requests.post(url, json=body, headers=headers)
        response.raise_for_status()

    except (Exception, HTTPError) as e:
        message=f"{str(e)}"
        send_notification('Alpha API Health Check Failed', message)
        return False
    else:
        return True

def handler(event, context):
    success = True

    
    if not check_api('family/North%20Ryde', headers=HEADERS):
        success = False

    if not check_api('crime/North%20Ryde', headers=HEADERS):
        success = False

    weather_body = {
        "suburb": "Strathfield",
        "includeHighest": False
    }
    if not check_api('data/weather/suburb', weather_body, HEADERS):
        success = False

    score_body = {
        "address": "13 Valewood Crescent, Marsfield",
        "weights": {
            "crime": 0.2,
            "weather": 0.1,
            "publicTransportation": 0.3,
            "familyDemographics": 0.3
        }
    }
    if not check_api('livability_score', score_body, HEADERS):
        success = False

    if success:
        send_notification("Alpha API Health Check Passed", "All Alpha API endpoints were healthy")