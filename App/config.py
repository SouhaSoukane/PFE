import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
# Charger les variables d'environnement
load_dotenv()
openai_key = os.getenv("OPENAI_KEY")
openai_client = ChatOpenAI(openai_api_key=openai_key)
USERNAME = os.getenv("SALESFORCE_USERNAME")
PASSWORD = os.getenv("SALESFORCE_PASSWORD")
CONSUMER_KEY = os.getenv("SALESFORCE_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("SALESFORCE_CONSUMER_SECRET")
TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"