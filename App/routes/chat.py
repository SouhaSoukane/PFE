from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import FILE_PATH
from services.openai_service import load_yaml
from services.openai_service import extract_relevant_objects
from services.openai_service import evaluate_and_fix_soql_query

from services.openai_service import generate_natural_response
from routes.salesforce import QueryModel
from routes.salesforce import get_accounts
from services.openai_service import NaturalLanguageQuery
from services.openai_service import generate_soql_query

from fastapi.responses import JSONResponse
router = APIRouter()

# Modèle pour valider les données envoyées dans le body
class SOQLRequest(BaseModel):
    natural_query: str

class QueryRequest(BaseModel):
    query: str



@router.post("/generate_soql")
def generate_soql(request: SOQLRequest):
    """Endpoint pour générer une requête SOQL depuis du texte en langage naturel."""
    if not request.natural_query:
        raise HTTPException(status_code=400, detail="Le champ 'natural_query' est requis.")
    
    soql_query = generate_soql_query(request.natural_query)
    return {"soql_query": soql_query}

@router.post("/data")
def generate_soql(request: SOQLRequest):
    """Endpoint pour générer une requête SOQL depuis du texte en langage naturel."""
    if not request.natural_query:
        raise HTTPException(status_code=400, detail="Le champ 'natural_query' est requis.")
    
    soql_query = generate_soql_query(request.natural_query)
    return {"soql_query": soql_query}
import json

@router.post("/query")
async def process_natural_language_query(nl_query: NaturalLanguageQuery):
    """
    Prend une requête en langage naturel, génère une requête SOQL, puis retourne les résultats.
    """
    try:
        soql_query = generate_soql_query(nl_query.query)
        query_model = QueryModel(query=soql_query)  
        results = get_accounts(query_model)  # Retourne un JSONResponse

        # ✅ Vérifier si `results` est un JSONResponse et extraire son contenu
        if isinstance(results, JSONResponse):
            results = json.loads(results.body.decode())  # Décoder correctement

            # Si le JSON contient une clé "message" (ex: "Aucune donnée trouvée"), retourner une liste vide
            if isinstance(results, dict) and "message" in results:
                results = []

        response = generate_natural_response(nl_query.query, results)
        return {"response": response}
    
    except Exception as e:
        return {"error": str(e)}


  


@router.post("/query/evaluate")
async def process_natural_language_query(nl_query: NaturalLanguageQuery):
    """
    Prend une requête en langage naturel, génère une requête SOQL, puis retourne les résultats.
    """
    try:
        soql_query = generate_soql_query(nl_query.query)
        query_model = QueryModel(query=soql_query)  
        evaluation_result=evaluate_and_fix_soql_query(query_model)
        # results = get_accounts(query_model)
        if evaluation_result["valid"]:
         final_query = soql_query  # Utilise la requête originale si elle est valide
        else:
         final_query = evaluation_result["corrected_query"]  # Utilise la requête corrigée

        # Exécuter la requête avec QueryModel
        query_model = QueryModel(query=final_query)
        results = get_accounts(query_model)  # Retourne un JSONResponse

        
        return {"response": results}
    
    except Exception as e:
        return {"error": str(e)}



@router.post("/donne")
async def data_retrieve(nl_query: NaturalLanguageQuery):
    """
    Prend une requête en langage naturel, génère une requête SOQL, puis retourne les résultats.
    """
    try:
        soql_query = generate_soql_query(nl_query.query)
        query_model = QueryModel(query=soql_query)  
        results = get_accounts(query_model)
        return {"soql_query": soql_query, "results": results}
    except Exception as e:
        return {"error": str(e)}
          


@router.post("/extract_relevant")
def extract_objects_endpoint(request: QueryRequest):
    schema = load_yaml(FILE_PATH)
    result = extract_relevant_objects(request.query, schema)
    return result          