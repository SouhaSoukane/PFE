from fastapi import FastAPI, HTTPException, Depends
from App.routes import salesforce,chat
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
import requests
from App.config import USERNAME, PASSWORD, CONSUMER_KEY, CONSUMER_SECRET, TOKEN_URL
from fastapi.middleware.cors import CORSMiddleware

# Création de l'API FastAPI
app = FastAPI()
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(salesforce.router, prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://esi97-dev-ed.develop.lightning.force.com",  # ✅ ton org Salesforce
        "https://*.lightning.force.com"                      # ✅ optionnel pour couvrir d'autres orgs
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)