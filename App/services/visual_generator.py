import pandas as pd
import json
from App.config import openai_client  # à adapter selon ton projet

#  Analyse automatique pour aider le LLM
#  Analyse améliorée des métadonnées
def extract_visual_insights(df: pd.DataFrame, max_categories: int = 10) -> dict[str, any]:
    """Extract enhanced metadata about the DataFrame to guide visualization choices."""
    columns_meta = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            columns_meta[col] = "temporal"
        elif pd.api.types.is_numeric_dtype(df[col]):
            unique_vals = df[col].nunique()
            if unique_vals <= 10 and df[col].dtype in ['int64', 'int32']:
                columns_meta[col] = "ordinal"
            else:
                columns_meta[col] = "quantitative"
        else:
            unique_vals = df[col].nunique()
            columns_meta[col] = "nominal"

    quant_stats = {}
    for col in df.columns:
        if columns_meta.get(col) == "quantitative":
            quant_stats[col] = {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": float(df[col].mean())
            }

    summary = {
        "row_count": len(df),
        "column_types": columns_meta,
        "quantitative_stats": quant_stats,
        "distinct_values": {col: df[col].nunique() for col in df.columns},
        "temporal_columns": [col for col, typ in columns_meta.items() if typ == "temporal"],
        "categorical_columns": [col for col, typ in columns_meta.items() if typ == "nominal"],
        "quantitative_columns": [col for col, typ in columns_meta.items() if typ == "quantitative"],
        "sample_data": {col: df[col].dropna().iloc[:5].tolist() for col in df.columns},
        "sample_categories": {
            col: df[col].dropna().unique().tolist()[:max_categories]
            for col in df.columns if columns_meta.get(col) == "nominal"
        }
    }

    return summary


#  Génération du JSON Vega-Lite
import json

def generate_vegalite_spec(df_name: str, df: pd.DataFrame, user_query: str) -> dict:
    insights = extract_visual_insights(df)

    prompt = f"""
Tu es un expert en visualisation de données utilisant Vega-Lite v6.

Ta mission est de générer un objet JSON Vega-Lite **valide et minimal**, basé sur :
1. Les métadonnées du DataFrame "{df_name}".
2. La demande de l'utilisateur.

---

 Objectif :
- Produire un graphique clair, professionnel et lisible.
- Les axes doivent avoir des **titres explicites** (ex. : "Date", "Montant total des commandes").
- Tous les textes doivent être propres et sans jargon technique ("Sum of", "Average of"... interdits).


 **Contraintes obligatoires** :
- Ne retourne **que** un JSON **strictement valide** (aucun texte autour, aucun commentaire).
- Utilise `"data": {{"name": "source"}}` pour référencer les données.
- Choisis un **type de graphique pertinent** :
  - Si la requête contient les mots "évolution", "tendance", "courbe", ou "dans le temps", utilise `"mark": {{"type": "line", "point": true}}`.
  - Si elle contient "comparaison", "par catégorie", ou des noms de colonnes non temporelles, utilise `"bar"`.

---

 **Cas spécifiques liés au temps** :
- Si l'utilisateur mentionne "par semaine" ou "par mois" :
  - **Agrège les données** sur cette période avec `timeUnit` (ex. `"timeUnit": "yearweek"` ou `"yearmonth"`).
  - Affiche la **date de début de chaque période** sur l'axe X.
  - Affiche la **date de début de chaque période** sur l'axe X.
- L'axe X doit utiliser `"type": "temporal"` si c’est une date.

- L'axe Y doit utiliser une **somme ou moyenne** sur une colonne quantitative, selon le contexte.

---

 **Recommandations d'encodage** :
- L’axe X = champ temporel, avec `labelAngle: -45`, `format: "%Y-%m-%d"`.
- L’axe Y = champ quantitatif (`montant total des ventes` par exemple).
- Ajoute toujours un `tooltip` contenant la date et la valeur.

---

 **Méta-infos disponibles** :
{json.dumps(insights, indent=2)}

 **Demande utilisateur** :
"{user_query}"

Génère maintenant un objet JSON Vega-Lite v6 **valide et minimal**.
"""


    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content.strip()

    try:
        # Nettoyage au cas où du texte aurait été rajouté autour du JSON
        json_str = content[content.index("{"): content.rindex("}") + 1]
        return json.loads(json_str)
    except Exception as e:
        return {"error": f"Erreur de parsing : {e}", "raw": content}

#  Injection des données
def inject_values(spec: dict, df: pd.DataFrame) -> dict:
    df_copy = df.copy()
    for col in df_copy.select_dtypes(include=["datetime"]):
        df_copy[col] = df_copy[col].dt.strftime("%Y-%m-%d")
    spec["data"] = {"values": df_copy.to_dict(orient="records")}
    return spec

#  Correction du format de l’axe temporel
def improve_temporal_axis(spec: dict) -> dict:
    try:
        x_encoding = spec.get("encoding", {}).get("x", {})
        if x_encoding.get("type") == "temporal":
            x_encoding.setdefault("axis", {})
            x_encoding["axis"]["format"] = "%Y-%m-%d"
            x_encoding["axis"]["labelAngle"] = -45
    except Exception as e:
        print(" Erreur dans le formatage de l'axe X :", e)
    return spec

# #  Point d’entrée
# if __name__ == "__main__":
#     df_name = "large_sales_dataset"
#     df = pd.read_csv("C:/Users/Fatma/Downloads/multi_dimensional_sales_dataset.csv")

   
#     user_query = "Montre l’évolution des ventes totales par produit et par région, en séparant les résultats par canal de vente."

#     base_spec = generate_vegalite_spec(df_name, df, user_query)
#     print(" JSON généré par le LLM (avant injection des données) :\n")
#     print(json.dumps(base_spec, indent=2))

#     if "error" in base_spec:
#         print(" Erreur :", base_spec["error"])
#         print(" Réponse brute :", base_spec["raw"])
#     else:
#         full_spec = inject_values(base_spec, df)
#         full_spec = improve_temporal_axis(full_spec)

#         print(" Aperçu des données injectées :")
#         for i, row in enumerate(full_spec["data"]["values"][:5]):
#             print(f"{i+1}. {row}")

#         output_file = "vegalite_output.json"
#         with open(output_file, "w", encoding="utf-8") as f:
#             json.dump(full_spec, f, indent=2)

#         print(f"\n JSON Vega-Lite sauvegardé dans : {output_file}")
#         print(" Ouvre-le sur https://vega.github.io/editor/ pour visualiser le graphe.")