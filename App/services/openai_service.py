from fastapi import FastAPI
from pydantic import BaseModel
import openai
from routes.salesforce import clean_soql_response, get_accounts
from config import openai_client, FILE_PATH

app = FastAPI()

# Configuration de l'API OpenAI

# Modèle pour la requête en langage naturel
class NaturalLanguageQuery(BaseModel):
    query: str

def load_yaml(file_path):
    """Charge le schéma Salesforce depuis un fichier YAML."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def generate_soql_query(natural_language_query: str) -> str:
    """
    Convertit une requête en langage naturel en une requête SOQL.
    """
    yaml_content = load_yaml(FILE_PATH)

    system_message = (
        "Tu es un assistant expert en SOQL (Salesforce Object Query Language). "
        "SOQL ne supporte pas les jointures SQL classiques (JOIN, INNER JOIN, etc.). "
        "Utilise uniquement les relations Master-Detail, Lookup et l'héritage des objets Salesforce pour construire tes requêtes.\n\n"

        "### Exigences :\n"
        "- Ne génère que des requêtes SOQL valides et optimisées.\n"
        "- Utilise uniquement les objets et champs présents dans le schéma fourni.\n"
        "- Si une relation Lookup est nécessaire, utilise une sous-requête (IN/SELECT).\n\n"
        "Tu dois générer des requêtes SOQL valides en fonction des questions en langage naturel. "
        "### Exemple Lookup :\n"
        "SELECT Id, Name FROM Warehouse__c WHERE Account__c IN (SELECT Id FROM Account WHERE Name = 'Distributeur 1')\n\n"
        "Voici le schéma Salesforce en YAML :\n"
        f"{yaml_content}\n\n"
        "Ne retourne que la requête SOQL et rien d'autre."
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": natural_language_query}
    ]

    # Appel correct à l'API OpenAI
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=200
    )

    return response.choices[0].message.content.strip()


def execute_soql_query(soql_query: str):
    """Exécute une requête SOQL et retourne les résultats."""
    return get_accounts(query=soql_query)

@app.post("/query")
async def process_natural_language_query(nl_query: NaturalLanguageQuery):
    """
    Prend une requête en langage naturel, génère une requête SOQL, puis retourne les résultats.
    """
    try:
        soql_query = generate_soql_query(nl_query.query)
        results = execute_soql_query(soql_query)
        return {"soql_query": soql_query, "results": results}
    except Exception as e:
        return {"error": str(e)}

