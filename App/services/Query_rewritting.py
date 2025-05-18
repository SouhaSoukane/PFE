import json
from App.config import openai_client, FILE_PATH

nb_question = 0
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
class SessionHandler:
    def __init__(self):
        self.messages = []
        self.system_prompt_sent = False

    def reset(self):
        self.messages = []
        self.system_prompt_sent = False

    def initialize_if_needed(self, system_prompt):
     global nb_question
  
     MAX_TOKENS_CONTEXT = 6000
     if not self.messages:
        self.messages.append({"role": "system", "content": system_prompt})
     elif estimate_token_count(self.messages) > MAX_TOKENS_CONTEXT:
          print("⚠️ Contexte trop long, réinitialisation.")
          self.reset()
          self.messages.append({"role": "system", "content": system_prompt})

    def append_user_question(self, content: str):
        # Seules les vraies questions utilisateur vont dans l'historique
        self.messages.append({"role": "user", "content": content})
    def append_assistant_response(self, content: str):
     self.messages.append({"role": "assistant", "content": content})
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
    
    session.initialize_if_needed( "Tu es un expert du SFA Merx. À partir du schéma de base de données fourni, "
        "ta tâche est de reformuler la question de l'utilisateur en langage naturel, "
        "de manière claire, explicite et précise les informations qui peuvent interesser l'utilisateur, n'hesite pas à demander les noms des objets en question "
        "exemple: l'utilisateur demande: quel est le produit le plus cher"
        "réponse: donne moi le nom et le montant du produit qui a le prix le plus élevé"
        "Fais le mapping entre les mots-clés de la question et les objets/champs du schéma "
        "si cela est pertinent, sans les exposer directement comme du code ou de la structure. "
        "Le but est de générer une version compréhensible et non ambigüe de la question, "
        "qui pourra être traitée par un agent d'extraction ensuite.\n\n"
         "⚠️ Utilise un ton direct, sans formules de politesse ou de demande : reformule la question comme une instruction claire.\n\n"
        f"📦 Schéma :\n{json.dumps(schema, indent=2)}\n")
    session.append_user_question(natural_language_query)
    # global nb_question
    # nb_question += 1
    # print(nb_question ) 
    
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=session.get_history(),
        temperature=0.2,
        max_tokens=300
    )

    return response.choices[0].message.content.strip()