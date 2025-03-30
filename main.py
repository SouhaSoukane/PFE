from fastapi import FastAPI, HTTPException, Depends
from routes import salesforce
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
import requests
from config import USERNAME, PASSWORD, CONSUMER_KEY, CONSUMER_SECRET, TOKEN_URL
from routes import chat

# Création de l'API FastAPI
app = FastAPI()
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(salesforce.router, prefix="/api")
