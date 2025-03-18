import json
import os

CONFIG_FILE = "config/config.json"

def load_config():
    """
    Load the configuration from the config file

    Returns:
        config: The configuration
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    config_path = os.path.join(base_dir, CONFIG_FILE)

    try:
        with open(config_path, "r") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}
    
config = load_config()