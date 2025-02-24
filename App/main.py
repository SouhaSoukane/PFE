from fastapi import FastAPI, HTTPException, Depends
from routes import salesforce
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
import requests
from config import USERNAME, PASSWORD, CONSUMER_KEY, CONSUMER_SECRET, TOKEN_URL


# Création de l'API FastAPI
app = FastAPI()

app.include_router(salesforce.router, prefix="/api")
