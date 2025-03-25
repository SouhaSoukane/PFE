import json
import re
import os
import chardet
from fastapi import FastAPI
from pydantic import BaseModel
import openai
import yaml
from routes.salesforce import clean_soql_response, get_accounts
from config import openai_client, FILE_PATH, OBJECTS_RELATIONS_FILE_PATH
from fastapi.responses import JSONResponse

# Configuration de LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_PROJECT"] = "pr-damp-childhood-24"
print("✅ LangSmith et OpenAI API sont configurés !")

app = FastAPI()

class NaturalLanguageQuery(BaseModel):
    query: str


def load_yaml(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
            if not data:
                raise ValueError(f"Le fichier YAML {file_path} est vide ou mal formé.")
            return data
    except FileNotFoundError:
        print(f"❌ Erreur : Fichier introuvable -> {file_path}")
    except yaml.YAMLError as e:
        print(f"❌ Erreur de parsing YAML dans {file_path} : {e}")
    except Exception as e:
        print(f"❌ Erreur inattendue : {e}")
    return {}


# Fonction pour extraire les objets et champs pertinents
import re
def extract_relevant_objects(natural_language_query: str, schema: dict) -> dict:
    system_message = (
        "Tu es un expert en Salesforce et SOQL.\n"
        "Ton objectif est d'identifier **obligatoirement** au moins un objet en relation avec la requête utilisateur.\n\n"
        
        "📌 **Règles obligatoires** :\n"
        "- **Ne retourne que des objets EXISTANTS dans le schéma Salesforce fourni.**\n"
        "- **Si la requête concerne les produits, cherche en priorité les objets liés aux produits (ex: Product__c, ProductVariant__c).**\n"
        "- **Ne jamais extraire un objet par défaut (Fallback_Object__c).**\n"
        "- **Si aucun objet exact ne correspond, trouve un objet similaire et explique ton choix dans le JSON.**\n"
        "- **Si aucun objet valide n'existe, renvoie une erreur explicite au lieu d'un objet fictif.**\n"
        "- **Toujours vérifier si l'objet extrait existe dans EntityDefinition.**\n"
        "- **Si l'objet extrait n'existe pas, renvoyer une erreur d'extraction et demander une vérification du schéma.**\n"
        "- **Retourne UNIQUEMENT un JSON valide et strictement structuré, sans texte explicatif.**\n"
        "- **NE JAMAIS** inclure d'introduction, d'explication ou de conclusion.\n"
        "- **Ne mets JAMAIS de balises de code (` ```json ... ``` `).**\n\n"

        "📌 **Format attendu (sans texte avant ou après)** :\n"
        "{\n"
        '  "objects": ["Object1__c", "Object2__c"],\n'
        '  "relations": [{"from": "Object1__c", "to": "Object2__c", "type": "Lookup", "field": "RelationField__c"}]\n'
        "}\n\n"

        "📌 **Schéma Salesforce fourni** :\n"
        f"{json.dumps(schema, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": natural_language_query}
    ]

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=500
    )

    response_text = response.choices[0].message.content.strip()

    if not response_text:
        print("\n❌ Erreur : Réponse vide de l'IA.")
        return {"objects": [], "relations": []}

    # 🔍 Debugging : Affichage brut de la réponse
    print("\n📥 Réponse brute de l'IA :", response_text)

    # 📌 Extraction stricte du JSON
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group(0)

    try:
        extracted_data = json.loads(response_text)
    except json.JSONDecodeError:
        print("\n❌ Erreur : Impossible de parser la réponse JSON de l'IA.")
        return {"objects": [], "relations": []}

    # ✅ Vérification des objets extraits
    if not extracted_data.get("objects"):
        print("\n❌ Aucune donnée extraite !")
        return {"objects": [], "relations": []}

    print("\n🔍 Objets et relations extraits :", extracted_data)
    return extracted_data



def fetch_fields_for_objects(extracted_data: dict, full_schema: dict) -> dict:
    """
    Récupère les champs des objets extraits en se basant sur le schéma complet.
    """
    fields = {}

    print(f"\n🔍 Structure de full_schema : {type(full_schema)}")  # Vérification du type

    for obj in extracted_data["objects"]:
        # Vérifier que full_schema est bien un dictionnaire et contient l'objet
        if isinstance(full_schema, dict) and obj in full_schema:
            obj_data = full_schema[obj]
            
            if isinstance(obj_data, dict) and "fields" in obj_data:
                fields[obj] = list(obj_data["fields"].keys())
            else:
                print(f"\n⚠️ Problème avec l'objet {obj} : {obj_data} (type: {type(obj_data)})")
        else:
            print(f"\n❌ Objet non trouvé dans le schéma : {obj}")

    return fields

def generate_soql_query(natural_language_query: str) -> str:
    # Charger les schémas
    schema = load_yaml(FILE_PATH)
    schema_OBJECTS_RELATIONS = load_yaml(OBJECTS_RELATIONS_FILE_PATH)

    # Assurer que les fichiers YAML sont bien convertis en dictionnaires
    try:
        schema = json.loads(schema) if isinstance(schema, str) else schema
        schema_OBJECTS_RELATIONS = json.loads(schema_OBJECTS_RELATIONS) if isinstance(schema_OBJECTS_RELATIONS, str) else schema_OBJECTS_RELATIONS
    except json.JSONDecodeError as e:
        print(f"\n❌ Erreur lors du chargement des fichiers YAML : {e}")
        return "Erreur : Schéma invalide."

    # 🔍 Extraction des objets et relations
    extracted_data = extract_relevant_objects(natural_language_query, schema_OBJECTS_RELATIONS)

    if not extracted_data["objects"]:
        print("\n❌ Aucun objet pertinent trouvé.")
        return "Erreur : Aucun objet pertinent trouvé."

    # ✅ Récupérer les champs des objets extraits
    extracted_data["fields"] = fetch_fields_for_objects(extracted_data, schema)

    # 🔄 Construction du prompt pour la génération de SOQL
    system_message = (
    "Tu es un assistant expert en SOQL.\n"
    "Génère une requête SOQL **strictement valide** pour Salesforce en utilisant les objets et relations fournis.\n"
    "🚨 **Règles strictes** :\n"
    "- Utilise UNIQUEMENT les objets et champs suivants :\n"
    f"{json.dumps(extracted_data['fields'], indent=2)}\n"
    "- Relations disponibles :\n"
    f"{json.dumps(extracted_data['relations'], indent=2)}\n"
    "- Ne crée pas de champs ou relations inexistants.\n"
    "- Respecte les relations **parent-enfant** et **enfant-parent**.\n"
    "- Si un champ est de type DateTime, les valeurs doivent être au format YYYY-MM-DDTHH:MM:SSZ.\n"
    "\n"
    "🔍 **Vérifications AVANT de générer la requête** :\n"
    "1️⃣ **Vérifier que toutes les relations utilisées existent bien** (utiliser `DescribeSObject` si nécessaire).\n"
    "2️⃣ **Si une relation parent-enfant est utilisée, s'assurer que l'objet parent possède bien la relation inverse**.\n"
    "3️⃣ **Si une relation enfant-parent est utilisée, vérifier que le champ Lookup ou Master-Detail existe bien sur l’objet enfant**.\n"
    "\n"
    "✅ **Exemples de requêtes valides :**\n"
    "\n"
    "🔹 **Requête enfant → parent (Lookup ou Master-Detail) :**\n"
    "  - SELECT Id, Name, Account.Name FROM Contact WHERE Account.Industry = 'media'\n"
    "\n"
    "🔹 **Requête parent → enfant (Subquery sur relation parent) :**\n"
    "  - SELECT Name, (SELECT Email FROM Contacts) FROM Account\n"
    "\n"
    "🔹 **Requête avec condition WHERE sur une relation enfant :**\n"
    "  - SELECT Name, (SELECT Email FROM Contacts WHERE Languages__c = 'French') FROM Account WHERE Industry = 'Tech'\n"
    "\n"
    "🔹 **Requête enfant → parent avec objet personnalisé :**\n"
    "  - SELECT Id, SubmittedAmount__c, Agent__r.Name FROM AgentPayment__c WHERE Agent__r.Name LIKE 'A%'\n"
    "\n"
    "🔹 **Requête parent → enfant avec objet personnalisé :**\n"
    "  - SELECT Name, (SELECT Code__c FROM Category__r) FROM Product__c WHERE Name LIKE 'Laptop%'\n"
    "\n"
    "🔹 **Requête avec clé polymorphique :**\n"
    "  - SELECT Id, Who.Name FROM Task WHERE Who.Type IN ('Contact', 'Lead')\n"
    "\n"
    "🔹 **Requête TYPEOF pour gérer les relations polymorphiques :**\n"
    "  - SELECT TYPEOF What WHEN Account THEN Phone, NumberOfEmployees WHEN Opportunity THEN Amount, CloseDate ELSE Name, Email END FROM Event\n"
    "\n"
    "🔹 **Requête avec agrégation et relation :**\n"
    "  - SELECT Name, (SELECT CreatedBy.Name FROM Notes) FROM Account\n"
    "  - SELECT Amount, Id, Name, (SELECT Quantity, PricebookEntry.UnitPrice FROM OpportunityLineItems) FROM Opportunity\n"
    "\n"
    "🔹 **Requête avec relation indirecte (via un objet intermédiaire) :**\n"
    "  - SELECT Territory__r.Name, (SELECT PromotionalProgram__r.Name FROM Territory__r.TerritoryPromos__r) FROM POS__c\n"
    "    🔹 **⚠️ Vérification importante :** `TerritoryPromos__r` doit être une relation enfant de `Territory__c`. Utiliser `DescribeSObject` pour confirmer.\n"
    "\n"
    "🛑 **Si une relation demandée n’existe pas** :\n"
    "- **Ne pas générer la requête.**\n"
    "- Retourner un message d'erreur spécifique : `Erreur SOQL : La relation 'XYZ' n'existe pas sur l'objet 'ABC'. Utilisez DescribeSObject pour vérifier.`\n"
    "\n"
    "🚀 **Retour attendu** :\n"
    "- La requête SOQL **directement exécutable** sur Salesforce.\n"
    "- **Retourne uniquement la requête SOQL** (pas de texte explicatif).\n"
    )



    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": natural_language_query}
    ]

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=300
    )

    soql_query = response.choices[0].message.content.strip()

    # 🚨 Suppression des balises de code ```sql ... ```
    soql_query = soql_query.replace("```sql", "").replace("```", "").strip()

    print("\n✅ Requête SOQL générée :")
    print(soql_query)

    return soql_query


def evaluate_and_fix_soql_query(soql_query: str) -> dict:
    """Évalue et corrige une requête SOQL."""
    yaml_content = load_yaml(FILE_PATH)
    
    system_message = (
        "Tu es un expert en SOQL (Salesforce Object Query Language). "
        "Analyse la requête SOQL fournie, détecte les erreurs et corrige-les.\n\n"
        "### Format de réponse attendu :\n"
        "{\n"
        '   "valid": true/false,\n'
        '   "errors": ["Description des erreurs détectées"],\n'
        '   "corrected_query": "Nouvelle requête SOQL corrigée"\n'
        "}\n\n"
        "### Schéma Salesforce :\n"
        f"{yaml_content}\n\n"
        "Retourne uniquement un JSON valide contenant le diagnostic et la correction."
    )
    
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": soql_query}
    ]
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=500
    )
    
    return json.loads(response.choices[0].message.content.strip())


def generate_natural_response(nl_query: str, results: list) -> str:
    system_message = (
        "Tu es un assistant expert en reformulation de réponses à partir de données, en langage naturel. "
        "Ton objectif est de transformer les résultats bruts en une réponse claire, naturelle et fluide pour l'utilisateur.\n\n"
        "### Exigences :\n"
        "- Reformule de manière naturelle sans termes techniques.\n"
        "- Utilise un ton simple et professionnel.\n"
        "- Si aucun résultat n'est trouvé, informe l'utilisateur avec une phrase polie.\n\n"
        "Voici un exemple :\n"
        "**Question :** Qui est le commercial le plus performant ?\n"
        "**Réponse brute :** Jean Dupont (ID: 1), Chiffre d'affaires : 500K€\n"
        "**Réponse reformulée :** Le commercial le plus performant est Jean Dupont, avec un chiffre d'affaires de 500 000 euros.\n\n"
        "Ne retourne que la réponse reformulée et rien d'autre."
    )

    # Si aucun résultat n'est trouvé
    if not results:
        return f"Désolé, je n'ai trouvé aucune information pour '{nl_query}'."

    # Reformulation dynamique sans supposer des clés spécifiques (ex: 'name', 'id')
    formatted_results = []
    for item in results:
        # Générer une phrase descriptive avec tous les attributs de l'objet
        description = ", ".join(f"{key}: {value}" for key, value in item.items())
        formatted_results.append(f"- {description}")

    data_summary = "\n".join(formatted_results)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"Question : {nl_query}\nRéponse brute :\n{data_summary}\nRéponse reformulée :"}
    ]

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

# @app.post("/query")
# async def process_natural_language_query(nl_query: NaturalLanguageQuery):
#     """
#     Prend une requête en langage naturel, génère une requête SOQL, exécute la requête,
#     puis retourne les résultats en langage naturel.
#     """
#     try:
#         soql_query = generate_soql_query(nl_query.query)
#         results = execute_soql_query(soql_query)
#         natural_response = generate_natural_response(nl_query.query, results)
        
#         return JSONResponse(content={"response": results})
    
#     except Exception as e:
#         return {"error": str(e)}

