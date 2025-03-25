import os
from dotenv import load_dotenv

import openai

# Charger les variables d'environnement
load_dotenv()
openai_key = os.getenv("OPENAI_KEY")
openai_client = openai.OpenAI(api_key=openai_key)  
FILE_PATH = os.getenv("FILE_PATH")
OBJECTS_RELATIONS_FILE_PATH = os.getenv("OBJECTS_RELATIONS_FILE_PATH")
USERNAME = os.getenv("SALESFORCE_USERNAME")
PASSWORD = os.getenv("SALESFORCE_PASSWORD")
CONSUMER_KEY = os.getenv("SALESFORCE_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("SALESFORCE_CONSUMER_SECRET")
TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"