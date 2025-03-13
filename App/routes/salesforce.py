import json
from fastapi import APIRouter, HTTPException, Depends, Query
import openai
import pandas as pd
from database import get_salesforce_session, get_sf
from fastapi.responses import JSONResponse
from config import openai_client
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
from pydantic import BaseModel
router = APIRouter()

@router.get("/")
def root():
    return {"message": "Salesforce API is ready"}

def refresh_salesforce():
    """Rafraîchir la connexion Salesforce en cas d'erreur d'authentification."""
    global sf, access_token, instance_url
    access_token, instance_url = get_salesforce_session()
    sf = Salesforce(instance_url=instance_url, session_id=access_token)

def clean_soql_response(response):
    try:
        # Vérifier si response est une chaîne JSON ou déjà un objet Python
        if isinstance(response, str):
            data = json.loads(response)  # Convertir la chaîne JSON en dict
        elif isinstance(response, dict):
            data = response
        else:
            return {"error": "Format de réponse invalide"}

        records = data.get("soql_query", [])  # Récupérer les enregistrements

        if not isinstance(records, list):
            return {"error": "Données mal formatées"}

        # Nettoyer les enregistrements en supprimant "attributes"
        cleaned_data = [{k: v for k, v in record.items() if k != "attributes"} for record in records]
         
        return cleaned_data

    except json.JSONDecodeError:
        return {"error": "Réponse JSON invalide"}

# Exemple de test
response = { 
    "soql_query": [
        {"attributes": {"type": "Account"}, "Id": "001", "Name": "Company A"},
        {"attributes": {"type": "Account"}, "Id": "002", "Name": "Company B"}
    ]
}

cleaned_response = clean_soql_response(response)
print(cleaned_response)


# Définition du modèle de requête
class QueryModel(BaseModel):
    query: str



@router.post("/accounts/")
def get_accounts(query_data: QueryModel):
    sf = get_sf()  # Récupérer l'instance Salesforce
    try:
        query = query_data.query  # Récupérer la requête SQL envoyée en JSON
        result = sf.query(query)
        records = result.get("records", [])

        if not records:
            print("🔍 Aucune donnée trouvée dans Salesforce.")
            return JSONResponse(content={"message": "Aucune donnée trouvée"}, status_code=404)

        cleaned_records = [{k: v for k, v in record.items() if k != "attributes"} for record in records]
        
        df = pd.DataFrame(cleaned_records)

        if df.empty:
            print("🚨 DataFrame vide ! Aucune donnée récupérée.")
            return JSONResponse(content={"message": "Aucune donnée trouvée"}, status_code=404)

        print("\n🔹 Aperçu du DataFrame :\n", df.head())

        return JSONResponse(content=df.to_dict(orient="records"), status_code=200)
    
    except SalesforceAuthenticationFailed:
        print("🔑 Échec d'authentification Salesforce, tentative de reconnexion...")
        refresh_salesforce()
        try:
            result = sf.query(query)
            records = result.get("records", [])
            return [{k: v for k, v in record.items() if k != "attributes"} for record in records]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur après rafraîchissement : {str(e)}")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur SOQL : {str(e)}")

@router.get("/generate")
def generate_response(prompt: str):
   
   response = openai_client.invoke(prompt)
   return {"response": response.content}