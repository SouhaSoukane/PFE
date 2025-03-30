import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from App.routes.salesforce import clean_soql_response, get_accounts
from App.config import openai_client, FILE_PATH

from fastapi.responses import JSONResponse



# Configuration de LangSmith
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_PROJECT"] = "pr-damp-childhood-24"
print("✅ LangSmith et OpenAI API sont configurés !")


app = FastAPI()

# Modèle pour la requête en langage naturel
class NaturalLanguageQuery(BaseModel):
    query: str

def load_yaml(file_path):
    """Charge le schéma Salesforce depuis un fichier YAML."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

# Fonction pour extraire les objets et champs pertinents
import re

def extract_relevant_objects(natural_language_query: str, schema: dict) -> dict:
    system_message = (
        "Tu es un expert en Salesforce et SOQL.\n"
        "Ton objectif est d'identifier **obligatoirement** au moins un objet et ses relations "
        "dans le schéma Salesforce fourni pour répondre à la question de l'utilisateur.\n\n"

        "📌 **Règles obligatoires** :\n"
        "- **Retourne UNIQUEMENT un JSON valide et strictement structuré, sans texte explicatif.**\n"
        "- **NE JAMAIS** inclure d'introduction, d'explication ou de conclusion.\n"
        "- **Ne mets JAMAIS de balises de code (` ```json ... ``` `).**\n"
        "- **Si aucun objet exact ne correspond, trouve un objet similaire et explique ton choix DANS LE JSON.**\n\n"

        "📌 **Format attendu (sans texte avant ou après)** :\n"
        "{\n"
        '  "objects": ["Object1__c", "Object2__c"],\n'
        '  "relations": [{"from": "Object1__c", "to": "Object2__c", "type": "Lookup", "field": "RelationField__c"}],\n'
        '  "fields": {"Object1__c": ["Field1__c", "Field2__c"], "Object2__c": ["FieldA__c"]}\n'
        "}\n\n"

        "📌 **Schéma Salesforce fourni** :\n"
        f"{json.dumps(schema, indent=2)}\n"
        " **Ne JAMAIS ajouter un champ absent du schéma**. Si un champ demandé est introuvable, retourne une erreur JSON dans la réponse."
"Ne jamais extraire un objet par défaut (Fallback_Object__c)."

"Si aucun objet valide n'est identifié, répondre explicitement que l'extraction a échoué au lieu d'ajouter un objet fictif."

"Toujours vérifier si l'objet extrait existe dans EntityDefinition."

"Si l'objet extrait n'existe pas, renvoyer une erreur d'extraction et demander une vérification du schéma."
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

    # 🔍 Debugging : Affichage brut de la réponse
    print("\n📥 Réponse brute de l'IA :", response_text)

    # 📌 Extraire uniquement la partie JSON si l’IA ajoute du texte explicatif
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group(0)

    # 🔥 Suppression des balises de code ```json ... ```
    response_text = response_text.strip("```json").strip("```").strip()

    try:
        extracted_data = json.loads(response_text)
    except json.JSONDecodeError:
        print("\n❌ Erreur : Impossible de parser la réponse JSON de l'IA. Tentative de correction...")

        # 🔄 Tentative de récupération d'un JSON valide en coupant les erreurs
        response_text = response_text.split("}\n")[0] + "}"  # Supprime les éventuelles coupures
        try:
            extracted_data = json.loads(response_text)
        except json.JSONDecodeError:
            print("\n❌ Échec de la correction, retour à une valeur par défaut.")
            return {"objects": [], "relations": [], "fields": {}}

    # ✅ Vérifier si des objets ont bien été trouvés
    if not extracted_data.get("objects"):
        print("\n❌ Aucune donnée extraite !")
        extracted_data = {"objects": ["Fallback_Object__c"], "relations": [], "fields": {"Fallback_Object__c": ["Id"]}}

    print("\n🔍 Objets et relations extraits :", extracted_data)

    return extracted_data

def correct_soql_relations(soql_query: str, extracted_data: dict) -> str:
    """
    Corrige dynamiquement les relations SOQL incorrectes en utilisant les objets et relations extraits.
    """
    relations = extracted_data.get("relations", [])
    
    for relation in relations:
        parent_obj = relation["from"]  # Ex: "TerritoryPromo__c"
        child_obj = relation["to"]  # Ex: "POS__c"
        relation_field = relation["field"]  # Ex: "Territory__c"

        # Construire la relation correcte
        incorrect_ref = f"{child_obj}__r"
        correct_ref = f"{parent_obj}__r.{child_obj}__r"

        # Remplacer dans la requête si nécessaire
        if incorrect_ref in soql_query:
            soql_query = soql_query.replace(incorrect_ref, correct_ref)

    return soql_query



# Fonction pour générer la requête SOQL
def generate_soql_query(natural_language_query: str) -> str:
    schema = load_yaml(FILE_PATH)

    # 🔍 Extraction des objets, relations et champs
    extracted_data = extract_relevant_objects(natural_language_query, schema)

    if not extracted_data["objects"]:
        print("\n❌ Aucun objet pertinent trouvé.")
        return "Erreur : Aucun objet pertinent trouvé."

    # 🔄 Construction du prompt pour la génération de SOQL
    system_message = (
    "Tu es un assistant expert en SOQL.\n"
    "Génère une requête SOQL **strictement valide** pour Salesforce en utilisant les objets et relations fournis.\n"
    "🚨 **Règles** :\n"
    "- Utilise UNIQUEMENT les objets et champs suivants :\n"
    f"{json.dumps(extracted_data['fields'], indent=2)}\n"
    "- Relations disponibles :\n"
    f"{json.dumps(extracted_data['relations'], indent=2)}\n"
    "- Ne crée pas de champs ou relations inexistants.\n"
    "Si un champ est de type DateTime, les valeurs doivent être au format YYYY-MM-DDTHH:MM:SSZ."

"Exemple :"

"❌ WHERE PaymentDate__c >= '2023-01-01'"

"✅ WHERE PaymentDate__c >= 2023-01-01T00:00:00Z"
    ### Exemple Lookup :
"SELECT Id, Name FROM Warehouse__c WHERE Account__c IN (SELECT Id FROM Account WHERE Name = 'Distributeur 1')"
    "- La requête doit être **directement exécutable** sur Salesforce.\n"
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
    soql_query = soql_query.strip("```sql").strip("```").strip()

    # 🚨 Correction automatique des relations mal formées
    soql_query = correct_soql_relations(soql_query, extracted_data)

    # Debugging: Affichage de la requête SOQL générée
    print("\n✅ Requête SOQL générée :")
    print(soql_query)

    return soql_query


def evaluate_and_fix_soql_query(soql_query: str) -> dict:
    """
    Évalue et corrige une requête SOQL.
    Retourne un dictionnaire avec l'analyse et une éventuelle correction.
    """
    yaml_content = load_yaml(FILE_PATH)

    # Vérifier que l'entrée est bien une chaîne
    if not isinstance(soql_query, str):
        soql_query = str(soql_query)

    system_message = (
        "Tu es un expert en SOQL (Salesforce Object Query Language). "
        "Analyse la requête SOQL fournie, détecte les erreurs et corrige-les si nécessaire.\n\n"
        "### Vérifications à effectuer :\n"
        "1. **Syntaxe** : La requête est-elle bien formée en SOQL ?\n"
        "2. **Objets et champs** : Tous les objets et champs existent-ils dans Salesforce ?\n"
        "3. **Relations** : Les jointures sont-elles correctes (Master-Detail, Lookup) ?\n"
        "4. **Optimisation** : La requête peut-elle être améliorée ?\n\n"
        "### Format de réponse attendu :\n"
        "{\n"
        '   "valid": true/false,  # Si la requête est valide\n'
        '   "errors": ["Description des erreurs détectées"],  # Liste des erreurs si présentes\n'
        '   "corrected_query": "Nouvelle requête SOQL corrigée"  # Requête corrigée si nécessaire\n'
        "}\n\n"
        "### Exemple :\n"
        "{\n"
        '   "valid": false,\n'
        '   "errors": ["Le champ CustomerType__c n\'existe pas dans Account"],\n'
        '   "corrected_query": "SELECT Id, Name FROM Account WHERE Type__c = \'Client\'"\n'
        "}\n\n"
        "### Schéma Salesforce :\n"
        f"{yaml_content}\n\n"
        "Retourne uniquement un JSON valide contenant le diagnostic et la correction si nécessaire."
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": soql_query}  # Vérification du type string
    ]

    # Appel API OpenAI pour évaluer et corriger la requête
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=500
    )

    return json.loads(response.choices[0].message.content.strip())  # Retourne un dict JSON



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

    # ✅ Si aucun résultat n'est trouvé
    if not results:
        return f"Désolé, je n'ai trouvé aucune information pour '{nl_query}'."

    # ✅ Reformulation dynamique sans supposer des clés spécifiques (ex: 'name', 'id')
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

