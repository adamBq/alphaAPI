import logging
import requests
from requests.exceptions import HTTPError
import json
import os
import boto3
import urllib.parse
from decimal import Decimal
from haversine import haversine, Unit

GOOGLE_API_KEY = "AIzaSyDcgohncbfmx_hw2MzwMTIe8jRqFRtgQ5c"
HEADERS = {
    "x-api-key": os.environ.get("AWS_API_KEY")
}
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST,GET"
}


logger = logging.getLogger()
logger.setLevel("INFO")

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('scores')

def family_score(suburb):
    response = table.get_item(
        Key={"suburb": suburb},
    )
    item = response.get("Item")

    if item and "familyScore" in item:
            score = float(item["familyScore"])
            logger.info(f"Found family score: {score}")
            return score
    
    url = 'https://m42dj4mgj8.execute-api.ap-southeast-2.amazonaws.com/prod/family/' + suburb

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info(f"Retrieved family statistics for {suburb}")
        data = response.json()

    family_with_child = data["coupleFamilyWithChildrenUnder15"] + \
        data["oneParentWithChildrenUnder15"]
    family_percent = family_with_child / data["totalFamilies"]

    score = 10 * family_percent / 0.5

    if not item:
        table.put_item(Item={
            "suburb": suburb,
            "familyScore": Decimal(str(score))
        })
    elif item.get("familyScore") is None:
        table.update_item(
            Key={"suburb": suburb},
            UpdateExpression='SET familyScore = :score',
            ExpressionAttributeValues={":score": Decimal(str(score))}
        )

    logger.info(f"Calculated family score: {score}")
    return score


def crime_score(suburb):
    response = table.get_item(
        Key={"suburb": suburb},
    )
    item = response.get("Item")

    if item and "crimeScore" in item:
            score = float(item["crimeScore"])
            logger.info(f"Found crime score: {score}")
            return score

    major_crimes = {
        "Homicide",
        "Assault",
        "Sexual offences",
        "Abduction and kidnapping",
        "Robbery",
        "Blackmail and extortion",
        "Coercive Control",
        "Intimidation, stalking and harassment",
        "Theft",
        "Other offences against the person",
        "Arson",
        "Malicious damage to property",
        "Drug offences",
        "Prohibited and regulated weapons offences",
        "Pornography offences"}
    minor_crimes = {
        "Disorderly conduct",
        "Betting and gaming offences",
        "Liquor offences",
        "Against justice procedures",
        "Other offences",
        "Transport regulatory offences"}

    major_crime_multiplier = 1
    minor_crime_multiplier = 0.5
    crime_count = 0

    url = "https://m42dj4mgj8.execute-api.ap-southeast-2.amazonaws.com/prod/crime/" + urllib.parse.quote(suburb)

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info(f"Retrieved crime statistics for {suburb}")
        data = response.json()

    for crime_category, crime_data in data["crimeSummary"].items():
        if crime_category in major_crimes:
            multiplier = major_crime_multiplier
        elif crime_category in minor_crimes:
            multiplier = minor_crime_multiplier

        crime_count += multiplier * crime_data["totalNum"]

    url = 'https://m42dj4mgj8.execute-api.ap-southeast-2.amazonaws.com/prod/family/population/' + urllib.parse.quote(suburb)

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info(f"Retrieved population statistics for {suburb}")
        data = response.json()

    population = data["totalPopulation"]
    crime_ratio = (crime_count) / population

    score = 10 * ((-crime_ratio / 12.5) + 1)

    if not item:
        table.put_item(Item={
            "suburb": suburb,
            "crimeScore": Decimal(str(score))
        })
    elif item.get("crimeScore") is None:
        table.update_item(
            Key={"suburb": suburb},
            UpdateExpression='SET crimeScore = :score',
            ExpressionAttributeValues={":score": Decimal(str(score))}
        )

    logger.info(f"Calculated crime score: {score}")
    return score


def weather_score(suburb):
    response = table.get_item(
        Key={"suburb": suburb},
    )
    item = response.get("Item")

    if item and "weatherScore" in item:
            score = float(item["weatherScore"])
            logger.info(f"Found weather score: {score}")
            return score

    url = 'https://m42dj4mgj8.execute-api.ap-southeast-2.amazonaws.com/prod/data/weather/suburb'

    body = {
        "suburb": suburb,
        "includeHighest": True
    }

    try:
        response = requests.post(url, json=body, headers=HEADERS)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info(f"Retrieved weather statistics for {suburb}")
        data = response.json()

    if data.get("requestedSuburbData", None) is None:
        score = 10.0
    else:
        weather_count = data["requestedSuburbData"]["occurrences"]
        weather_count_max = data["highestSuburbData"]["occurrences"]
        
        score = (10 / (weather_count_max**2)) * \
            (weather_count - weather_count_max)**2
    
    if not item:
        table.put_item(Item={
            "suburb": suburb,
            "weatherScore": Decimal(str(score))
        })
    elif not item.get("weatherScore", None):
        table.update_item(
            Key={"suburb": suburb},
            UpdateExpression='SET weatherScore = :score',
            ExpressionAttributeValues={":score": Decimal(str(score))}
        )

    logger.info(f"Calculated weather score: {score}")
    return score


def transport_score(data):
    
    house_location = data["results"][0]["geometry"]["location"]
    lat, lng = house_location["lat"], house_location["lng"]

    # get closest bus stop
    url = "https://places.googleapis.com/v1/places:searchNearby"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": 'places.location,places.displayName'
    }

    params = {
        "locationRestriction": {
            "circle": {
                "center": {

                    "latitude": lat,
                    "longitude": lng,
                },
                "radius": 1500.0
            }
        },
        "rankPreference": "DISTANCE",
        "includedTypes": ["bus_station", "bus_stop", "light_rail_station"]
    }

    try:
        response = requests.post(url, json=params, headers=headers)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info("Retrieved bus and lightrail data")
        data = response.json()

    if not data.get("places"):
        bus_score = 0
    else:
        bus_stop_location = data["places"][0]["location"]
        bus_stop_count = len(data["places"])

        distance = haversine(
            (lat,
             lng),
            (bus_stop_location["latitude"],
             bus_stop_location["longitude"]),
            unit=Unit.METERS)
        bus_score = 5 * ((1500 - distance) / 1500) * (bus_stop_count / 20)

    # get closest train station
    params = {
        "locationRestriction": {
            "circle": {
                "center": {

                    "latitude": lat,
                    "longitude": lng,
                },
                "radius": 10000.0
            }
        },
        "rankPreference": "DISTANCE",
        "includedTypes": ["subway_station", "train_station"]
    }

    try:
        response = requests.post(url, json=params, headers=headers)
        response.raise_for_status()
    except HTTPError as e:
        logger.exception(e)
        return None
    except Exception as e:
        logger.exception(e)
        return None
    else:
        logger.info("Retrieved train and metro data")
        data = response.json()

    if not data.get("places"):
        train_score = 0
    else:
        train_station_location = data["places"][0]["location"]
        train_station_count = min(len(data["places"]), 10)

        distance = haversine(
            (lat,
             lng),
            (train_station_location["latitude"],
             train_station_location["longitude"]),
            unit=Unit.METERS)
        train_score = 5 * ((10000 - distance) / 10000) * \
            (train_station_count / 10)

    logger.info(f"Calculated transport score: {train_score + bus_score}")
    return train_score + bus_score


def handler(event, context):
    body = json.loads(event.get('body', None))

    if not body:
        return json.dumps({
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": "No body"
        })

    address = body.get("address", None)
    if not address:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": "No address provided"
        }
    
    weights = body.get("weights", None)
    if not weights:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": "No weights provided"
        }

    total_weights = sum(weights.values())

    if total_weights != 1:
        weights = {
            key: value /
            total_weights for key,
            value in weights.items()}
        
    suburb_only = body.get("suburbOnly", False)

    if not suburb_only:
        url = "https://maps.googleapis.com/maps/api/geocode/json?address=" + \
            urllib.parse.quote(address) + "&key=" + GOOGLE_API_KEY

        try:
            logger.info(f"Fetching geocode for address: {address}")
            response = requests.get(url)
            response.raise_for_status()
        except HTTPError as e:
            logger.exception(e)
            return None
        except Exception as e:
            print(e)
            logger.exception(e)
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": f"Invalid address: {e}"
            }
        else:
            logger.info(f"Retrieved geocode for address: {address}")
            data = response.json()

        suburb = next((component["long_name"] for component in data["results"][
                    0]["address_components"] if "locality" in component["types"]), None)

        scores = {
            "family": family_score(suburb),
            "crime": crime_score(suburb),
            "weather": weather_score(suburb),
            "transport": transport_score(data),
        }
    
    else:
        suburb = address

        scores = {
            "family": family_score(suburb),
            "crime": crime_score(suburb),
            "weather": weather_score(suburb),
        }

    logger.info("Checking all scores are valid")
    for key, value in scores.items():
        if value is None:
            logger.error(f"Score for {key} is invalid")
            return {
                "statusCode": 500,
                "headers": CORS_HEADERS,
                "body": f"Unable to generate {key} score"
            }
    logger.info("All scores are valid")



    if not suburb_only:
        overall = {
                "overallScore": round(
                    weights.get(
                        "publicTransportation",
                        0) *
                    scores["transport"] +
                    weights.get(
                        "crime",
                        0) *
                    scores["crime"] +
                    weights.get(
                        "weather",
                        0) *
                    scores["weather"] +
                    weights.get(
                        "familyDemographics",
                        0) *
                    scores["family"],
                    2),
                "breakdown": {
                    "crimeScore": round(
                        scores["crime"],
                        2),
                    "transportScore": round(
                        scores["transport"],
                        2),
                    "weatherScore": round(
                        scores["weather"],
                        2),
                    "familyScore": round(
                        scores["family"],
                        2),
            }}
    else:
        overall = {
            "overallScore": round(
                weights.get(
                    "crime",
                    0) *
                scores["crime"] +
                weights.get(
                    "weather",
                    0) *
                scores["weather"] +
                weights.get(
                    "familyDemographics",
                    0) *
                scores["family"],
                2),
            "breakdown": {
                "crimeScore": round(
                    scores["crime"],
                    2),
                "weatherScore": round(
                    scores["weather"],
                    2),
                "familyScore": round(
                    scores["family"],
                    2),
        }}
    
    logger.info(overall)
    
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps(overall)
    }

event = {
    "body": json.dumps({
        "address": "Marsfield",
        "suburbOnly": True,
        "weights": {
            "crime": 1,
            "weather": 1,
            "familyDemographics": 1
        }
    })
}

print(handler(event, ''))