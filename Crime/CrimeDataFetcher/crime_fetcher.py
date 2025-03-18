import requests
import pandas as pd
import zipfile
import io
from util.config import config

CRIME_DATA_URL = config.get('CRIME_DATA_URL')

def fetch():
    """
    This method will download the crime data ZIP file, extract the CSV file
    and load it into a pandas DataFrame. 

    Returns:
        crime_data: The crime data in a pandas DataFrame
    """
    try:
        print("Downloading crime data...")
        
        response = requests.get(CRIME_DATA_URL)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zip_ref:
            csv_filename = zip_ref.namelist()[0]
            with zip_ref.open(csv_filename) as file:
                crime_data = pd.read_csv(file)

        print("Crime data downloaded successfully.")
        return crime_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching crime data: {e}")
        return None
    except zipfile.BadZipFile as e:
        print(f"Error extracting ZIP file: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None
