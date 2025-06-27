import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
import openai
from App.routes.salesforce import QueryModel, clean_soql_response, get_accounts
from App.config import openai_client, FILE_PATH
from datetime import datetime
from fastapi.responses import JSONResponse
import re

from App.services.exemples import SOQL_EXAMPLES, detect_example_need



app = FastAPI()
datetime_fields = [
    "Loading__c.Date__c",
    "Reception__c.Date__c",
    "IssuedDate__c",
    "CreatedDate__c",
    "LastOrderDate__c",
    "PaymentDate__c",
    "ActualVisitDate__c",
    "PlannedVisitDate__c"
]




# Modèle pour la requête en langage naturel
class NaturalLanguageQuery(BaseModel):
    query: str

def load_yaml(file_path):
    """Charge le schéma Salesforce depuis un fichier YAML."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

schema = load_yaml(FILE_PATH)

def get_current_datetime():
    now = datetime.now()
    return {"datetime": now}
# Fonction pour extraire les objets et champs pertinents

 



def extract_relevant_objects(natural_language_query: str, schema: dict, step1_response:str) -> dict:

    # Étape 2 - Identification des objets
    step2_user_prompt = (
         "Tu es un expert en Salesforce et SOQL.\n"
        "À partir de l'intention suivante, identifie les objets pertinents du schéma.\n"
        "Ne retourne qu'un JSON strict comme décrit. Si aucun objet n'est valide, retourne une erreur explicite JSON.\n\n"
        f" Intention : {step1_response}\n"
        f" Schéma :\n{json.dumps(schema, indent=2)}\n\n"

        " Format attendu :\n"
        "{\n"
        '  "objects": ["Object1__c", "Object2__c"],\n'
        '  "reasoning": "Explication du choix des objets (obligatoire)",\n'
        '  "errors": null\n'
        "}\n"
    )

    step2_response_text = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=  [{"role": "user", "content": step2_user_prompt}],
        temperature=0.2,
        max_tokens=500
    ).choices[0].message.content.strip()

    print("\n Étape 2 - Objets identifiés :", step2_response_text)

    try:
        step2_json = json.loads(re.search(r"\{.*\}", step2_response_text, re.DOTALL).group(0))
    except:
        return {"objects": [], "relations": [], "fields": {}}

    if not step2_json.get("objects"):
        return {"objects": [], "relations": [], "fields": {}}

    selected_objects = step2_json["objects"]

    # Étape 3 - Relations et champs
    step3_user_prompt = (
       "Tu es un expert Salesforce. À partir de l’intention utilisateur et des objets extraits du schéma, identifie uniquement les **champs et relations pertinents** pour répondre au besoin.\n"
    "***retourne toujours l'id***"
    " Tu dois te baser uniquement sur les champs et relations **existants dans le schéma**.\n"
    "N’inclus que les éléments directement utiles pour répondre à l’intention, ne liste pas tout ce qui est disponible.\n\n"
    f" Intention : {step1_response}\n"
    f" Objets : {selected_objects}\n"
    f" Schéma :\n{json.dumps(schema, indent=2)}\n\n"
    " Format attendu :\n"
    "{\n"
    '  "relations": [{"from": "Object1__c", "to": "Object2__c", "type": "Lookup", "field": "RelationField__c"}],\n'
    '  "fields": {\n'
    '    "Object1__c": ["Champ1__c", "Champ2__c"],\n'
    '    "Object2__c": ["ChampA__c"]\n'
    "  }\n"
    )

    step3_response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages= [{"role": "user", "content": step3_user_prompt}],
        temperature=0.2,
        max_tokens=500
    ).choices[0].message.content.strip()

    print("\n Étape 3 - Relations et champs :", step3_response)

    try:
        step3_json = json.loads(re.search(r"\{.*\}", step3_response, re.DOTALL).group(0))
    except:
        return {"objects": selected_objects, "relations": [], "fields": {}}

    return {
        "intention": step1_response,
        "objects": selected_objects,
        "relations": step3_json.get("relations", []),
        "fields": step3_json.get("fields", {})
    }



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

def correct_datetime_format(soql_query: str, datetime_fields: list) -> str:
    """
    Corrige uniquement les comparaisons sur les champs de type DateTime dans une requête SOQL.
    Si la date est au format 'YYYY-MM-DD' sans T, elle sera convertie en 'YYYY-MM-DDT00:00:00Z'
    uniquement pour les champs spécifiés comme DateTime.
    """
    # On trie par longueur inversée pour éviter les collisions (ex: Date__c vs MyDate__c)
    datetime_fields = sorted(datetime_fields, key=len, reverse=True)

    # Construit une expression qui matche tous les champs DateTime
    pattern = r"\b({})\s*([<>=!]+)\s*'?(?!\d{{4}}-\d{{2}}-\d{{2}}T)(\d{{4}}-\d{{2}}-\d{{2}})'?".format("|".join(map(re.escape, datetime_fields)))

    def replacer(match):
        field, operator, date = match.groups()
        return f"{field} {operator} {date}T00:00:00Z"

    return re.sub(pattern, replacer, soql_query)

def generate_soql_query(extracted_data: dict) -> str:
    
    current_time = datetime.now()
    current_date_str = current_time.strftime("%Y-%m-%d")

    system_message = """
 Tu es un expert Salesforce spécialisé dans l'écriture de requêtes SOQL complexes, **exécutables** et **optimisées**.

 Objectif : Lit bien l'intention de l'utilisateur ****Ne rate rien*** afin de génèrer une requête SOQL qui réponds à cette intention **parfaitement valide**, **optimisée** et **strictement conforme** aux objets, relations et champs fournis .

 Contraintes INCONTOURNABLES :

1.  Tu ne peux utiliser **que les champs et relations fournis** dans les blocs ` Relations disponibles` et ` Champs disponibles`.  
    N’invente **jamais** un champ ou une relation (ex : `fullName` ou `PromotionalPrograms__r` si non listés).

2.  Si le champ ou la relation semble exister logiquement mais **n’est pas listé**, **ne l’utilise pas**. Tu dois alors reformuler la requête pour **rester strictement dans ce qui est autorisé**.

3.  Tu ne peux **jamais traverser plus d’un niveau de relation** par champ :
   - Interdiction : `Relation1__r.Relation2__r.Field` 
   - Autorisé : `Relation1__r.Field` 

4.  Si tu dois accéder à une relation enfant, utilise une **sous-requête** (`parent-to-child`) avec **le nom exact de la relation enfant** tel que fourni.
 Sous-requêtes (relations enfant) :

- Lorsque tu fais une sous-requête (parent-to-child), **utilise uniquement le nom exact** de la relation enfant fourni dans ` Relations disponibles`.
-  Si tu ne trouves pas de relation enfant correspondant à ce que demande l'utilisateur, **tu ne dois pas générer la requête**.
-  Exemple correct : `(SELECT Name FROM Contacts)` uniquement si `Contacts` est bien une relation enfant de l'objet de départ.
-  N'invente jamais de noms comme `PromotionalPrograms__r` si ce nom n’apparaît pas **exactement** dans la liste des relations enfant de l’objet courant (ex : `POS__c`).

5.  Si un champ personnalisé est utilisé, **il doit se terminer par `__c`**, et une relation personnalisée par `__r`. Ne fais jamais d’erreur de suffixe.
6. utilise le id dans la requete
7. Ne rate aucune information mentionné dans l'intention surtout les valeurs avec quoi tu vas filtré!
8.  Ne retourne **que** la requête SOQL **dans un bloc de code `soql`**, sans texte, explication ou caractère en plus.
9.  Quand une valeur de filtre est mentionnée (comme un nom, une date, une quantité), elle doit être utilisée dans un `WHERE` clair.
   - Ex : "associés à Numilog" implique un filtre sur `Account__r.Name LIKE '%Numilog%'`
---

 Exemple de sortie attendue :

Si la question contient un mot-clé ou un nom (comme "Numilog") et que l’objet principal possède une référence à Account (ex: Account__c), alors ajoute une clause WHERE qui filtre sur `Account__r.Name` avec un LIKE.

Par exemple : 
Pour "quels sont les entrepôts de Numilog ?", et si l’objet `Warehouse__c` a une relation avec `Account`, la requête SOQL doit inclure :
WHERE Account__r.Name LIKE '%Numilog%'

"""


    if "intention" in extracted_data:
     intention_summary = extracted_data["intention"]
    else:
    # Gérer le cas où l'intention est absente
     intention_summary = "Intention non définie"
    
    # Préparation des messages pour l'API
    messages = [
    {"role": "system", "content": system_message},
    {"role": "user", "content": f"""
   question:
    {  intention_summary}

      Objets identifiés :
    {json.dumps(extracted_data["objects"], indent=2)}

      Relations disponibles :
    {json.dumps(extracted_data["relations"], indent=2)}

     Champs disponibles :
    {json.dumps(extracted_data["fields"], indent=2)}
"""}
]

   

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=300
    )

    soql_query = response.choices[0].message.content.strip()
    soql_query = soql_query.strip("```soql").strip("```").strip()

    soql_query = correct_soql_relations(soql_query, extracted_data)
   
    soql_query = correct_datetime_format(soql_query, datetime_fields)
    # soql_query = correct_soql_query(soql_query, extracted_data)
    print("\n Requête SOQL générée :")
    print(soql_query)

    return soql_query

current_time = datetime.now()  
def correct_soql_query(soql_query: str, extracted_data: dict) -> str:
   
    current_date_str = current_time.strftime("%Y-%m-%d")

    system_message = f"""
Tu es un consultant expert en requêtes SOQL.
Ta mission est de corriger la requête si elle est incorrecte.
Sinon, tu la retournes telle quelle.
Fait attention si elle est correcte n'y touche à rien


 Ne retourne **que** la requête SOQL **dans un bloc de code `soql`**, sans explication ou texte autour.

 Date actuelle : {current_date_str}

 Relations disponibles :
{json.dumps(extracted_data['relations'], indent=2)}

 Champs disponibles :
{json.dumps(extracted_data['fields'], indent=2)}
"""



    response = openai_client.chat.completions.create(
    model="gpt-4o",  # ou "gpt-4o-mini" selon ton plan
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": soql_query}
            ],
            temperature=0.2,
            max_tokens=150
        )

        # Extraire juste le texte entre les balises `soql`
    result = response.choices[0].message.content.strip()
    if result.startswith("```soql"):
            return result.replace("```soql", "").replace("```", "").strip()
    else:
            return result.strip()

def refine_soql_query( extracted_data: dict, original_soql: str, execution_error: str) -> str:
    """
    Utilise un LLM pour corriger une requête SOQL basée sur une erreur d'exécution.
    """

    system_message = """
     Tu es un expert Salesforce spécialisé dans la correction de requêtes SOQL.

     Objectif : Corriger la requête SOQL fournie en tenant compte de :
- l’intention exprimée par l'utilisateur
- la structure de la requête actuelle
- et surtout, le message d’erreur renvoyé lors de son exécution.

 Contraintes :
1. Tu dois absolument respecter les règles SOQL (pas de champs/relations inventés).
2. Tu peux reformuler la requête si nécessaire, mais elle doit rester fidèle à l’intention initiale.
3. Ne retourne que la requête SOQL dans un bloc `soql`. Aucune explication ou commentaire.
4. Si le message d'erreur indique qu’un champ ou une relation est invalide, corrige cela uniquement avec les champs connus (fournis dans les objets Salesforce).
5. Ne traverse pas plus d’un niveau de relation (ex: `A__r.B__r.C` est interdit).
"""
    if "intention" in extracted_data:
     intention_summary = extracted_data["intention"]
    else:
    # Gérer le cas où l'intention est absente
     intention_summary = "Intention non définie"
    
    user_message = f"""
 question:
    {  intention_summary}

 Requête SOQL initiale :  
```soql
{original_soql}
 Message d’erreur d'exécution :

 Relations disponibles :
{json.dumps(extracted_data['relations'], indent=2)}

 Champs disponibles :
{json.dumps(extracted_data['fields'], indent=2)}
{execution_error}

 Corrige la requête SOQL pour qu’elle respecte les contraintes et fonctionne correctement. """
    response = openai_client.chat.completions.create(
     model="gpt-4o",
     messages=[
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
     ],
     temperature=0.2,
     max_tokens=300
    )

    corrected_soql = response.choices[0].message.content.strip()
    corrected_soql = corrected_soql.strip("```soql").strip("```").strip()

# Tu peux ici aussi appliquer tes fonctions de correction
    # corrected_soql = correct_soql_relations(corrected_soql, extract_relevant_objects(original_nl_query, schema))
    corrected_soql = correct_datetime_format(corrected_soql, datetime_fields)
    # corrected_soql = correct_soql_query(corrected_soql, extract_relevant_objects(original_nl_query, schema))

    print("\n🔁 Requête SOQL corrigée après exécution échouée :")
    print(corrected_soql)

    return corrected_soql


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
        "N'utilise pas l'id sauf si l'utilisateur le demande"
        "Ne retourne que la réponse reformulée et rien d'autre."
       "  Date actuelle : {current_date_str}"
    )

    #  Cas vide ou non exploitable
    if not results or all(not any(v for v in item.values()) for item in results):
        return f"Désolé, je n'ai trouvé aucune information pour '{nl_query}'."

    #  Reformulation avec les 5 premiers résultats
    formatted_results = []
    for item in results[:5]:
        description = ", ".join(f"{key}: {value}" for key, value in item.items())
        formatted_results.append(f"- {description}")

    data_summary = "\n".join(formatted_results)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"Question : {nl_query}\nRéponse brute :\n{data_summary}\nRéponse reformulée :"}
    ]

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
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



def needs_visual_output(intention: str) -> bool:
    prompt = f"""
Tu es un assistant Salesforce. Analyse la question suivante et dis si l'utilisateur attend un visuel comme un graphique, un tableau, ou un diagramme.
Réponds uniquement par "oui" ou "non".

Question : {intention}
"""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10
    ).choices[0].message.content.strip().lower()
    return response == "oui"


