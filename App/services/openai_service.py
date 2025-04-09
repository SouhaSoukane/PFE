import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from App.routes.salesforce import clean_soql_response, get_accounts
from App.config import openai_client, FILE_PATH
from datetime import datetime
from fastapi.responses import JSONResponse
import re

from App.services.exemples import SOQL_EXAMPLES, detect_example_need

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


def get_current_datetime():
    now = datetime.now()
    return {"datetime": now}
# Fonction pour extraire les objets et champs pertinents

def extract_relevant_objects(natural_language_query: str, schema: dict) -> dict:
    """
    Étape 1 : Comprendre le besoin utilisateur
    Étape 2 : Identifier les objets Salesforce pertinents
    Étape 3 : Générer les relations + champs
    """
    # Étape 1 : Résumer l'intention de l'utilisateur
    step1_messages = [
        {"role": "system", "content": "Tu es un assistant Salesforce. Résume en une phrase claire ce que l'utilisateur cherche à faire, sans ajouter d'interprétation personnelle."},
        {"role": "user", "content": natural_language_query}
    ]
    step1_response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=step1_messages,
        temperature=0.2
    ).choices[0].message.content.strip()

    print("\n🔎 Étape 1 - Intention résumée :", step1_response)

    # Étape 2 : Identifier les objets à partir de l’intention + schéma
    step2_prompt = (
        "Tu es un expert en Salesforce et SOQL.\n"
        "À partir de l'intention suivante, identifie les objets pertinents du schéma.\n"
        "Ne retourne qu'un JSON strict comme décrit. Si aucun objet n'est valide, retourne une erreur explicite JSON.\n\n"
        f"📥 Intention : {step1_response}\n"
        f"📦 Schéma :\n{json.dumps(schema, indent=2)}\n\n"
        "📤 Format attendu :\n"
        "{\n"
        '  "objects": ["Object1__c", "Object2__c"],\n'
        '  "reasoning": "Explication du choix des objets (obligatoire)",\n'
        '  "errors": null\n'
        "}\n"
    )
    step2_messages = [
        {"role": "system", "content": step2_prompt}
    ]
    step2_response_text = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=step2_messages,
        temperature=0.2,
        max_tokens=500
    ).choices[0].message.content.strip()

    print("\n🧩 Étape 2 - Objets identifiés :", step2_response_text)

    try:
        step2_json = json.loads(re.search(r"\{.*\}", step2_response_text, re.DOTALL).group(0))
    except:
        print("❌ Erreur lors du parsing JSON.")
        return {"objects": [], "relations": [], "fields": {}}

    if not step2_json.get("objects"):
        print("❌ Aucun objet extrait.")
        return {"objects": [], "relations": [], "fields": {}}

    # Étape 3 : Générer les relations et champs à partir des objets extraits
    selected_objects = step2_json["objects"]
    step3_prompt = (
    "Tu es un expert Salesforce. À partir de l’intention utilisateur et des objets extraits du schéma, identifie uniquement les **champs et relations pertinents** pour répondre au besoin.\n"
    "⚠️ Tu dois te baser uniquement sur les champs et relations **existants dans le schéma**.\n"
    "❗️N’inclus que les éléments directement utiles pour répondre à l’intention, ne liste pas tout ce qui est disponible.\n\n"
    f"🎯 Intention : {step1_response}\n"
    f"📄 Objets : {selected_objects}\n"
    f"📦 Schéma :\n{json.dumps(schema, indent=2)}\n\n"
    "📤 Format attendu :\n"
    "{\n"
    '  "relations": [{"from": "Object1__c", "to": "Object2__c", "type": "Lookup", "field": "RelationField__c"}],\n'
    '  "fields": {\n'
    '    "Object1__c": ["Champ1__c", "Champ2__c"],\n'
    '    "Object2__c": ["ChampA__c"]\n'
    "  }\n"
    "}"
     )

    step3_response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": step3_prompt}],
        temperature=0.2,
        max_tokens=500
    ).choices[0].message.content.strip()

    print("\n🔗 Étape 3 - Relations et champs :", step3_response)

    try:
        step3_json = json.loads(re.search(r"\{.*\}", step3_response, re.DOTALL).group(0))
    except:
        print("❌ Parsing JSON échoué à l'étape 3.")
        return {"objects": selected_objects, "relations": [], "fields": {}}

    # Combiner résultats
    final_result = {
        "intention":step1_response,
        "objects": selected_objects,
        "relations": step3_json.get("relations", []),
        "fields": step3_json.get("fields", {})
    }

    return final_result

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

import re

def correct_datetime_format(soql_query: str, datetime_fields: list) -> str:
    # Regex pour matcher les dates au format YYYY-MM-DD (sans T00:00:00Z) uniquement
    pattern = r"\b({})\s*([<>=!]+)\s*'?(?!\d{{4}}-\d{{2}}-\d{{2}}T)(\d{{4}}-\d{{2}}-\d{{2}})'?".format("|".join(map(re.escape, datetime_fields)))
    
    def replacer(match):
        field, operator, date = match.groups()
        return f"{field} {operator} {date}T00:00:00Z"

    return re.sub(pattern, replacer, soql_query)


def generate_soql_query(natural_language_query: str) -> str:
    schema = load_yaml(FILE_PATH)
    current_time = datetime.now()
    current_year = current_time.year
    current_month = current_time.month
    current_day = current_time.day
    current_date_str = current_time.strftime("%Y-%m-%d")

    extracted_data = extract_relevant_objects(natural_language_query, schema)

    if not extracted_data["objects"]:
        print("\n❌ Aucun objet pertinent trouvé.")
        return "Erreur : Aucun objet pertinent trouvé."

    # # ➕ Détection dynamique des exemples
    # examples_needed = detect_example_need(natural_language_query,extracted_data)
    # # 🖨️ Affichage des exemples nécessaires dans la console
    # print("\n📌 Exemples détectés comme nécessaires :")
    # for key in examples_needed:
    #  print(f" - {key}")
    # example_snippets = ""
    # if examples_needed:
    #     example_snippets += "\n🧾 Exemples pertinents :\n"
    #     for key in examples_needed:
    #         for ex in SOQL_EXAMPLES.get(key, []):
    #             example_snippets += f"- {ex}\n"

    # 🧠 Construction du prompt
    system_message = f"""
⭐️ Tu es un expert Salesforce spécialisé dans l'écriture de requêtes SOQL complexes, **exécutables** et **optimisées**.

🎯 Objectif : Génère une requête SOQL **parfaitement valide**, **optimisée** et **strictement conforme** aux objets, relations et champs fournis ci-dessous.

🔐 Contraintes INCONTOURNABLES :

1. ⚠️ Tu ne peux utiliser **que les champs et relations fournis** dans les blocs `📐 Relations disponibles` et `🧾 Champs disponibles`.  
   ❌ N’invente **jamais** un champ ou une relation (ex : `fullName` ou `PromotionalPrograms__r` si non listés).

2. ✅ Si le champ ou la relation semble exister logiquement mais **n’est pas listé**, **ne l’utilise pas**. Tu dois alors reformuler la requête pour **rester strictement dans ce qui est autorisé**.

3. 🚫 Tu ne peux **jamais traverser plus d’un niveau de relation** par champ :
   - Interdiction : `Relation1__r.Relation2__r.Field` ❌
   - Autorisé : `Relation1__r.Field` ✅

4. ✅ Si tu dois accéder à une relation enfant, utilise une **sous-requête** (`parent-to-child`) avec **le nom exact de la relation enfant** tel que fourni.
🔁 Sous-requêtes (relations enfant) :

- Lorsque tu fais une sous-requête (parent-to-child), **utilise uniquement le nom exact** de la relation enfant fourni dans `📐 Relations disponibles`.
- ⚠️ Si tu ne trouves pas de relation enfant correspondant à ce que demande l'utilisateur, **tu ne dois pas générer la requête**.
- ✅ Exemple correct : `(SELECT Name FROM Contacts)` uniquement si `Contacts` est bien une relation enfant de l'objet de départ.
- ❌ N'invente jamais de noms comme `PromotionalPrograms__r` si ce nom n’apparaît pas **exactement** dans la liste des relations enfant de l’objet courant (ex : `POS__c`).

5. 🔍 Si un champ personnalisé est utilisé, **il doit se terminer par `__c`**, et une relation personnalisée par `__r`. Ne fais jamais d’erreur de suffixe.

6. 🧠 Règle d’or : Si l’utilisateur demande une info présente **directement sur un objet**, ne complexifie pas la requête inutilement.

7. 🎯 Ne retourne **que** la requête SOQL **dans un bloc de code `soql`**, sans texte, explication ou caractère en plus.

---

📅 Date actuelle : {current_date_str}

📐 Relations disponibles :
{json.dumps(extracted_data['relations'], indent=2)}

🧾 Champs disponibles :
{json.dumps(extracted_data['fields'], indent=2)}
"""

    if "intention" in extracted_data:
     intention_summary = extracted_data["intention"]
    else:
    # Gérer le cas où l'intention est absente
     intention_summary = "Intention non définie"
    user_message = f"{intention_summary}\n\n{natural_language_query}"

    # Préparation des messages pour l'API
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]
   

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2,
        max_tokens=300
    )

    soql_query = response.choices[0].message.content.strip()
    soql_query = soql_query.strip("```soql").strip("```").strip()

    soql_query = correct_soql_relations(soql_query, extracted_data)
    datetime_fields = ["IssuedDate__c", "CreatedDate__c", "LastOrderDate__c", "PaymentDate__c", "Date__c", "ActualVisitDate__c", "PlannedVisitDate__c"]
    soql_query = correct_datetime_format(soql_query, datetime_fields)
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
        "**Réponse brute :** Jean Dupont (ID: 1), Chiffre d'affaires : 500000DZD\n"
        "**Réponse reformulée :** Le commercial le plus performant est Jean Dupont, avec un chiffre d'affaires de 500 000 DZD.\n\n"
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

