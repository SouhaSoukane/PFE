import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

USERNAME = os.getenv("SALESFORCE_USERNAME")
PASSWORD = os.getenv("SALESFORCE_PASSWORD")
CONSUMER_KEY = os.getenv("SALESFORCE_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("SALESFORCE_CONSUMER_SECRET")
TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"