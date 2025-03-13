from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from routes.salesforce import QueryModel
from routes.salesforce import get_accounts
from services.openai_service import NaturalLanguageQuery
from services.openai_service import generate_soql_query

router = APIRouter()

# Modèle pour valider les données envoyées dans le body
class SOQLRequest(BaseModel):
    natural_query: str

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

@router.post("/query")
async def process_natural_language_query(nl_query: NaturalLanguageQuery):
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
  
