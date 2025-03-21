import requests
import json
import urllib.parse
from haversine import haversine, Unit

API_KEY = "AIzaSyDcgohncbfmx_hw2MzwMTIe8jRqFRtgQ5c"

dynamodb = boto3.resource('dynamodb')


def family_score(suburb):

    url = 'https://tzeks84nk6.execute-api.ap-southeast-2.amazonaws.com/test/family/' + suburb

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

    family_with_child = data["coupleFamilyWithChildrenUnder15"] + \
        data["oneParentWithChildrenUnder15"]
    family_percent = family_with_child / data["totalFamilies"]

    score = 10 * family_percent / 0.5

    return score


def crime_score(suburb):
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

    url = "https://favnlumox2.execute-api.us-east-1.amazonaws.com/test?suburb=" + suburb

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

    for crime_category, crime_data in data["crimeSummary"].items():
        if crime_category in major_crimes:
            multiplier = major_crime_multiplier
        elif crime_category in minor_crimes:
            multiplier = minor_crime_multiplier

        crime_count += multiplier * crime_data["totalNum"]

    url = 'https://tzeks84nk6.execute-api.ap-southeast-2.amazonaws.com/test/family/population/' + suburb

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

    population = data["totalPopulation"]
    crime_ratio = (crime_count) / population

    return 10 * ((-crime_ratio / 12.5) + 1)


def weather_score(suburb):
    url = 'https://r69rgp99vg.execute-api.ap-southeast-2.amazonaws.com/dev/suburb'

    body = {
        "suburb": suburb,
        "includeHighest": True
    }

    response = requests.post(url, json=body)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

    body = json.loads(data["body"])

    if body.get("requestedSuburbData", None) is None:
        return 10

    weather_count = body["requestedSuburbData"]["occurrences"]
    weather_count_max = body["highestSuburbData"]["occurrences"]

    return (10 / (weather_count_max**2)) * \
        (weather_count - weather_count_max)**2


def transport_score(address):
    url = "https://maps.googleapis.com/maps/api/geocode/json?address=" + \
        urllib.parse.quote(address) + "&key=" + API_KEY

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

    if not data:
        return "Error: Invalid address or location not found"

    house_location = data["results"][0]["geometry"]["location"]
    lat, lng = house_location["lat"], house_location["lng"]

    # get closest bus stop
    url = "https://places.googleapis.com/v1/places:searchNearby"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
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

    response = requests.post(url, json=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

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

    response = requests.post(url, json=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
    else:
        return None

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

    return train_score + bus_score


def handler(event, context):
    address = event.get("address", None)
    weights = event.get("weights", None)

    if address is None or weights is None:
        return {
            "statusCode": 400,
            "body": "Invalid Address"
        }

    total_weights = sum(weights.values())

    if total_weights != 1:
        weights = {
            key: value /
            total_weights for key,
            value in weights.items()}

    url = "https://maps.googleapis.com/maps/api/geocode/json?address=" + \
        urllib.parse.quote(address) + "&key=" + API_KEY

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
    else:
        return {
            "statusCode": 400,
            "body": "Invalid address"
        }

    suburb = next((component["long_name"] for component in data["results"][
                  0]["address_components"] if "locality" in component["types"]), None)

    scores = {
        "transport": transport_score(address),
        "crime": crime_score(suburb),
        "weather": weather_score(suburb),
        "family": family_score(suburb),
    }

    for key, value in scores.items():
        if value is None:
            return {
                "statusCode": 500,
                "body": f"Unable to generate {key} score"
            }

    return {
        "statusCode": 200,
        "body": {
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
            }}}
