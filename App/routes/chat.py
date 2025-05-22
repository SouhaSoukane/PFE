from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from App.config import FILE_PATH
from App.services.Query_rewritting import query_rewriter, SessionHandler
from App.services.approche_decomposition import classify_query_complexity, decompose_complex_query_into_steps, execute_steps_sequentially
from App.services.openai_service import  load_yaml, refine_soql_query
from App.services.openai_service import extract_relevant_objects
from App.services.openai_service import evaluate_and_fix_soql_query

from App.services.openai_service import generate_natural_response
from App.routes.salesforce import QueryModel
from App.routes.salesforce import get_accounts
from App.services.openai_service import NaturalLanguageQuery
from App.services.openai_service import generate_soql_query

from fastapi.responses import JSONResponse

from App.services.visual_generator import generate_vegalite_spec, improve_temporal_axis, inject_values
router = APIRouter()

# Modèle pour valider les données envoyées dans le body
class SOQLRequest(BaseModel):
    natural_query: str

class QueryRequest(BaseModel):
    query: str

    
     
schema = load_yaml(FILE_PATH)
session = SessionHandler()
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
    query_rewritten = query_rewriter(nl_query.query, schema, session)
    extracted_data = extract_relevant_objects(nl_query.query, schema, query_rewritten)

    if not extracted_data["objects"]:
        print("\n❌ Aucun objet pertinent trouvé.")
        return {"error": "Aucun objet pertinent trouvé."}

    try:
        soql_query = generate_soql_query(extracted_data)
        query_model = QueryModel(query=soql_query)

        retry_count = 0
        while retry_count < 3:
            try:
                result_dict = get_accounts(query_model)  # ✅ récupère un dict avec "json" et "df"
                break
            except Exception as e:
                print(f"❌ Erreur d'exécution (tentative {retry_count + 1}) :", str(e))
                retry_count += 1

                corrected_soql = refine_soql_query(
                    extracted_data=extracted_data,
                    original_soql=query_model.query,
                    execution_error=str(e)
                )
                query_model = QueryModel(query=corrected_soql)
        else:
            return {"error": "Erreur après plusieurs tentatives d'exécution."}

        json_response = result_dict.get("json")
        df = result_dict.get("df")  # ✅ dataframe accessible ici si nécessaire

        if isinstance(json_response, JSONResponse):
            json_data = json.loads(json_response.body.decode())
            if isinstance(json_data, dict) and "message" in json_data:
                json_data = []
        else:
            json_data = json_response
        visuel = generate_vegalite_spec("data frame",df,query_rewritten)
        full_spec = inject_values(visuel, df)
        full_spec = improve_temporal_axis(full_spec)

        print("📊 Aperçu des données injectées :")
        for i, row in enumerate(full_spec["data"]["values"][:5]):
            print(f"{i+1}. {row}")

        output_file = "vegalite_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(full_spec, f, indent=2)

        print(f"\n✅ JSON Vega-Lite sauvegardé dans : {output_file}")
        print("💡 Ouvre-le sur https://vega.github.io/editor/ pour visualiser le graphe.")
        response = generate_natural_response(nl_query.query, json_data)
        session.append_assistant_response(response)
        print("🧠 Réponse ajoutée à la session :", session.get_history())

        return {
            "response": response,
            "soql_query": soql_query,
            "file":{output_file}
            # "dataframe": df.to_dict(orient="records") if df is not None else None  # optionnel
        }

    except Exception as e:
        return {"error": str(e)}


@router.post("/assistant")
async def assistant_api(nl_query: NaturalLanguageQuery):
    """
    Prend une requête en langage naturel, génère une requête SOQL, puis retourne les résultats.
    """
    
    response = generate_soql_query(nl_query.query)      
    return {"response": response}
    
    


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



class NaturalLanguageQuery(BaseModel):
    query: str

@router.post("/soql-from-nl")
def handle_complex_natural_language_query(nl_input: NaturalLanguageQuery):  # 👈 ici aussi
    nl_query = nl_input.query   # 👈 récupère le champ "query" proprement

    # Ensuite ton pipeline reste pareil :
    extracted_data = extract_relevant_objects(nl_query, schema,session)
    intention = extracted_data.get("intention", nl_query)
    complexity = classify_query_complexity(intention)

    if complexity == "simple":
        soql = generate_soql_query(extracted_data)
        query_model = QueryModel(query=soql)
        retry_count = 0
        while retry_count < 3:
            try:
                results = get_accounts(query_model)
                # retry_count= 3
                break  # ✅ Succès => on sort de la boucle
            except Exception as e:
                print(f"❌ Erreur d'exécution (tentative {retry_count + 1}) :", str(e))
                retry_count += 1

                corrected_soql = refine_soql_query(
                    extracted_data=extracted_data,
                    original_soql=query_model.query,
                    execution_error=str(e)
                )
                query_model = QueryModel(query=corrected_soql)
        else:
            # 🚨 Toutes les tentatives ont échoué
            return {"error": "Erreur après plusieurs tentatives d'exécution."}

        # ✅ Résultat valide
        if isinstance(results, JSONResponse):
            results = json.loads(results.body.decode())
            if isinstance(results, dict) and "message" in results:
                results = [] # ⚠️ tu dois avoir une fonction get_accounts qui exécute
        return generate_natural_response(nl_query, results)

    elif complexity == "complexe":
        
         steps = decompose_complex_query_into_steps(nl_query)
         results = execute_steps_sequentially(steps, schema)
         return {"steps": steps, "results": results}

    else:
        return "Je n'ai pas pu déterminer la complexité de la question."







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











@router.post("/rewrite")
def rewrite(natural_query:NaturalLanguageQuery):
    schema = load_yaml(FILE_PATH)
    

  
    try:
        reformulated = query_rewriter(natural_query.query, schema)
        return {"rewritten_query": reformulated}
    except Exception as e:
        return {"error": str(e)}, 500