import json
import re
from App.config import openai_client
from typing import List, Dict
from fastapi.responses import JSONResponse
from App.routes.salesforce import QueryModel, get_accounts
from App.services.Query_rewritting import SessionHandler
from App.services.openai_service import  extract_relevant_objects, generate_soql_query, refine_soql_query

def classify_query_complexity(intention: str) -> str:
    prompt = f"""
Tu es un expert Salesforce. La question suivante est-elle simple ou complexe à traduire en requête SOQL ?
Réponds uniquement par "simple" ou "complexe".

Question : {intention}
"""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10
    ).choices[0].message.content.strip().lower()
    return response


def decompose_complex_query_into_steps(nl_query: str) -> List[str]:
    """
    Décompose une requête complexe en sous-questions PERTINENTES et DÉPENDANTES.
    Chaque sous-question doit faire progresser intelligemment vers la réponse finale.
    """
    system_prompt = """
Tu es un expert Salesforce et analyste de besoins métier.
Ta mission est de DÉCOMPOSER INTELLIGEMMENT une question complexe en plusieurs étapes CLAIRES et UTILES, seulement si nécessaire.

🎯 Objectif :
- Chaque sous-question doit faire avancer LOGIQUEMENT vers la réponse finale.
- Ne découpe PAS mécaniquement. Si une question simple suffit, ne la divise pas.
- Limite le nombre de sous-questions au strict nécessaire.
- Les étapes doivent être naturelles, éviter toute redondance ou absurdité.
- Chaque sous-question doit pouvoir être résolue seule par une requête SOQL simple.

📋 Format de réponse STRICT :
{
  "steps": [
    "Sous-question 1",
    "Sous-question 2",
    "Sous-question 3"
  ]
}

⚠️ Attention :
- Pas d'explications.
- Pas d'introduction ni de justification.
- Juste un JSON correct avec les questions découpées PERTINENTES.
"""

    user_prompt = f"""
Décompose intelligemment cette question en étapes :

"{nl_query}"
"""

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,  # 📉 pour avoir des réponses plus sérieuses, moins inventives
        max_tokens=600
    )

    content = response.choices[0].message.content.strip()

    try:
        steps_json = json.loads(content)
        return steps_json.get("steps", [])
    except json.JSONDecodeError:
        return []

session = SessionHandler()

def execute_steps_sequentially(steps: List[str], schema: dict) -> List[Dict]:
    """
    Exécute séquentiellement chaque étape décomposée.
    Chaque résultat est stocké et peut être exploité dans la génération suivante.
    """
    results_memory = []  # Pour stocker les résultats après chaque requête
    previous_result = None  # Pour passer au contexte suivant

    for index, step in enumerate(steps):
        print(f"\n🚀 Traitement de l'étape {index + 1} : {step}")

        # Ajouter au prompt le résultat précédent si ce n'est pas la première étape
        if previous_result:
            context_info = f"\nRésultat précédent disponible :\n{json.dumps(previous_result, indent=2)}\n\n"
        else:
            context_info = ""

        # 👇 Générer la requête en enrichissant l'intention avec le contexte du résultat précédent
        extracted_data = extract_relevant_objects(
            step + context_info,
            schema, session
        )
        
        soql_query = generate_soql_query(extracted_data)

        # 👇 Exécuter la requête
        query_model = QueryModel(query=soql_query)
        retry_count = 0

        while retry_count < 3:
            try:
                result = get_accounts(query_model)
                break
            except Exception as e:
                print(f"❌ Erreur d'exécution (étape {index + 1}) : {str(e)}")
                corrected_soql = refine_soql_query(
                    extracted_data=extracted_data,
                    original_soql=query_model.query,
                    execution_error=str(e)
                )
                query_model = QueryModel(query=corrected_soql)
                retry_count += 1
        else:
            result = {"error": f"Erreur à l'étape {index + 1}"}

        # ✅ Stocker le résultat
        if isinstance(result, JSONResponse):
            result = json.loads(result.body.decode())
        
        results_memory.append(result)

        # ✅ Préparer pour l'étape suivante
        previous_result = result

    return results_memory        