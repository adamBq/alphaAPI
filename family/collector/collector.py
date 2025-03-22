import os
import json
import requests
import boto3
from bs4 import BeautifulSoup

S3_BUCKET = os.environ.get("S3_BUCKET", "paige-3011")
S3_KEY = os.environ.get("S3_KEY", "abs_datapack_nsw.zip")

s3_client = boto3.client("s3")


def lambda_handler(event, context):
    """
    This Lambda function is triggered by an AWS EventBridge event.
    It downloads the most recent ABS DataPack for "general community profile" for
    suburb and localities (SAL) for NSW, then uploads the zip file to S3.
    """
    try:
        # retrieve the abs datapacks page
        datapacks_url = "https://www.abs.gov.au/census/find-census-data/datapacks"
        response = requests.get(datapacks_url)
        response.raise_for_status()

        # parse the html to find the datapack form
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form", id="datapackForm")
        if not form:
            raise Exception("Datapack form not found on the page.")

        # set up the form data
        form_data = {
            "census_year": "2021",
            "datapack_type": "general community profile",
            "geography": "SAL",
            "state": "NSW"
        }

        # get the form's action URL and build the full URL if necessary.
        form_action = form.get("action")
        if not form_action.startswith("http"):
            form_action = requests.compat.urljoin(datapacks_url, form_action)

        # submit the form via a post request
        download_page_response = requests.post(form_action, data=form_data)
        download_page_response.raise_for_status()

        # parse the response to find the download link for the zip file
        download_soup = BeautifulSoup(
            download_page_response.text, "html.parser")
        zip_link = download_soup.find(
            "a", href=lambda href: href and href.endswith(".zip"))
        if not zip_link:
            raise Exception("Zip file link not found.")
        zip_url = zip_link["href"]
        zip_url = requests.compat.urljoin(form_action, zip_url)

        # download the zip file
        zip_response = requests.get(zip_url)
        zip_response.raise_for_status()

        # upload the zip file to s3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=S3_KEY,
            Body=zip_response.content)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Successfully downloaded and uploaded the ABS datapack for NSW to S3 as {S3_KEY}"
            })
        }

    except Exception as e:
        print(f"Error processing the datapack: {e}")
        return {"statusCode": 500, "body": json.dumps(
            {"error": f"Error processing the datapack: {str(e)}"})}


if __name__ == "__main__":
    # local testing purposes
    result = lambda_handler({}, {})
    print(result)
