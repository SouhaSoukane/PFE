import requests
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
from config import USERNAME, PASSWORD, CONSUMER_KEY, CONSUMER_SECRET, TOKEN_URL

def get_salesforce_session():
    """Obtenir un token d'accès OAuth2 et l'instance URL de Salesforce."""
    data = {
        "grant_type": "password",
        "client_id": CONSUMER_KEY,
        "client_secret": CONSUMER_SECRET,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        auth_data = response.json()
        return auth_data["access_token"], auth_data["instance_url"]
    else:
        raise Exception(f"Authentication failed: {response.text}")

# Initialisation de la connexion Salesforce
access_token, instance_url = get_salesforce_session()
sf = Salesforce(instance_url=instance_url, session_id=access_token)

def get_sf():
    """Retourne l'instance Salesforce pour l'utiliser dans les routes."""
    return sf