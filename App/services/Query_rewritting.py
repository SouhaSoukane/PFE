import json
from App.config import openai_client, FILE_PATH

nb_question = 0
def estimate_token_count(messages):
    """
    Estime approximativement le nombre de tokens utilisés dans une liste de messages.
    Basé sur une moyenne de 0.75 token par mot (valeur typique pour l'anglais/français).
    Gère les cas où le contenu n'est pas une chaîne de caractères (ex : DataFrame).
    """
    total_tokens = 0
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            # Convertit tout contenu non-textuel en texte exploitable
            if hasattr(content, "to_string"):
                content = content.to_string()
            else:
                content = str(content)
        word_count = len(content.split())
        total_tokens += int(word_count * 0.75) + 4  # +4 pour le rôle / structure
    return total_tokens

class SessionHandler:
    def __init__(self):
        self.messages = []
        self.system_prompt_sent = False
        self.history = []

    def reset(self):
        self.messages = []
        self.system_prompt_sent = False
        self.history = []

    def initialize_if_needed(self, system_prompt):
     global nb_question
  
     MAX_TOKENS_CONTEXT = 6000
     if not self.messages:
        self.messages.append({"role": "system", "content": system_prompt})
     elif estimate_token_count(self.messages) > MAX_TOKENS_CONTEXT:
          print("⚠️ Contexte trop long, réinitialisation.")
          self.reset()
          self.messages.append({"role": "system", "content": system_prompt})

    def append_user_question(self, content):
    # Convertit tout contenu non-textuel en chaîne avant d'ajouter
     if not isinstance(content, str):
        if hasattr(content, "to_string"):
            content = content.to_string()
        else:
            content = str(content)
     self.messages.append({"role": "user", "content": content})

    def append_assistant_response(self, content: str, data=None):
        # Ajouter la réponse de l'assistant à l'historique
        self.messages.append({"role": "assistant", "content": content})

        # Si un dataframe est fourni, l'ajouter sous forme de résumé lisible
        if data is not None:
            # Convertir un extrait du dataframe en JSON (par exemple, les 5 premières lignes)
            data_json = data.head(5).to_dict(orient="records")  # Limiter l'extrait à 5 lignes
            data_text = f"📊 Résumé des données : {json.dumps(data_json, indent=2, ensure_ascii=False)}"
            self.messages.append({"role": "assistant", "content": data_text})
    def get_history(self):
        return self.messages

# session = SessionHandler()

def estimate_token_count(messages):
    """
    Estime approximativement le nombre de tokens utilisés dans une liste de messages.
    Basé sur une moyenne de 0.75 token par mot (valeur typique pour l'anglais/français).
    """
    total_tokens = 0
    for msg in messages:
        content = msg.get("content", "")
        word_count = len(content.split())
        total_tokens += int(word_count * 0.75) + 4  # +4 pour le rôle / structure
    return total_tokens

def query_rewriter(natural_language_query: str, schema: dict, session:SessionHandler) -> str:
    session.initialize_if_needed(
        "Tu es un expert du SFA Merx. À partir du schéma de base de données fourni, "
        "ta tâche est de reformuler la question de l'utilisateur en langage naturel, "
        "de manière claire, explicite et précise, afin de guider un agent d'extraction de données. "
        "Tu dois toujours exploiter le contexte de la conversation pour comprendre à quoi fait référence l'utilisateur. "
        "Si l'utilisateur utilise un pronom ou une expression implicite comme : son, celle-ci, celui mentionné, etc., "
        "tu dois supposer qu’il fait référence à **la dernière entité principale mentionnée dans la conversation** "
        "(produit, catégorie, facture, commercial, etc.).\n"
        "À partir de ce moment, toutes les questions suivantes doivent être reformulées en se basant exclusivement sur l'**ID** "
        "de cette entité principale, même si la question porte sur d'autres champs ou attributs. "
        "Ne cherche jamais à interpréter sans contexte clair : si la référence est ambiguë, reformule la question pour qu'elle soit explicite. "
        "Ne redémarre jamais l’analyse depuis zéro. Ta priorité est la **continuité contextuelle** et la cohérence.\n\n"

        "Tu fais le mapping entre les mots-clés de la question et les objets/champs du schéma, "
        "mais sans exposer cela comme du code. Reformule uniquement la question de façon explicite, non ambigüe, et orientée résultat.\n\n"

        "⚠️ Utilise un ton direct, sans formules de politesse. Reformule chaque question comme une instruction claire.\n\n"

        "Voici un exemple de comportement attendu :\n"
        "- Q1 : Quel est le produit le moins cher ?\n"
        "- R1 : Donne-moi le nom, le montant et l'ID du produit qui a le prix le plus bas.\n"
        "- assistant : Le produit le moins cher est le Jus de Pomme Bio, ID 12345.\n"
        "- Q2 : Quelle est sa catégorie ?\n"
        "- R2 : Donne-moi le nom de la catégorie du produit avec l'ID 12345.\n\n"

        "Autre exemple :\n"
        "- Q1 : Quelle est la facture la plus élevée ?\n"
        "- R1 : Donne-moi le numéro, le montant, et l'ID de la facture ayant le montant TTC le plus élevé.\n"
        "- assistant : La facture la plus élevée est la facture INV-2024-098, ID abcdef.\n"
        "- Q2 : Quelle est sa date d’échéance ?\n"
        "- R2 : Donne-moi la date d’échéance de la facture avec l'ID abcdef.\n\n"

        f"📦 Schéma :\n{json.dumps(schema, indent=2)}\n"
        f"📥 Question : {natural_language_query}\n"
    )

    session.append_user_question(natural_language_query)

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=session.get_history(),
        temperature=0.2,
        max_tokens=300
    )

    return response.choices[0].message.content.strip()
