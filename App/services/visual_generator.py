import pandas as pd
import json
from App.config import openai_client  # à adapter selon ton projet

# 🔎 Analyse automatique pour aider le LLM
def extract_visual_insights(df: pd.DataFrame, max_categories=10) -> dict:
    columns_meta = {
        col: (
            "temporal" if pd.api.types.is_datetime64_any_dtype(df[col]) else
            "quantitative" if pd.api.types.is_numeric_dtype(df[col]) else
            "nominal"
        )
        for col in df.columns
    }

    summary = {
        "row_count": len(df),
        "column_types": columns_meta,
        "distinct_values": {col: df[col].nunique() for col in df.columns},
        "temporal_columns": [col for col, typ in columns_meta.items() if typ == "temporal"],
        "categorical_columns": [col for col, typ in columns_meta.items() if typ == "nominal"],
        "quantitative_columns": [col for col, typ in columns_meta.items() if typ == "quantitative"],
        "group_densities": {},
        "sample_categories": {}
    }

    for cat_col in summary["categorical_columns"]:
        summary["sample_categories"][cat_col] = df[cat_col].dropna().unique().tolist()[:max_categories]

    for cat_col in summary["categorical_columns"]:
        for time_col in summary["temporal_columns"]:
            group_counts = df.groupby(cat_col)[time_col].nunique()
            summary["group_densities"][f"{cat_col} / {time_col}"] = group_counts.to_dict()

    return summary

# 🧠 Génération du JSON Vega-Lite
def generate_vegalite_spec(df_name: str, df: pd.DataFrame, user_query: str) -> dict:
    insights = extract_visual_insights(df)

    prompt = f"""
Tu es un assistant expert en data visualisation.

Voici les métadonnées du DataFrame "{df_name}" :

Résumé :
{json.dumps(insights, indent=2)}

L'utilisateur a demandé : "{user_query}"

À partir de ces informations, génère un objet JSON conforme à Vega-Lite v6.
⚠️ N'inclus pas les données. Utilise `"data": {{"name": "source"}}`.
Retourne uniquement le JSON sans commentaire ni texte autour.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content.strip()

    try:
        json_str = content[content.index("{"): content.rindex("}")+1]
        return json.loads(json_str)
    except Exception as e:
        return {"error": f"Erreur de parsing : {e}", "raw": content}

# 🧩 Injection des données
def inject_values(spec: dict, df: pd.DataFrame) -> dict:
    df_copy = df.copy()
    for col in df_copy.select_dtypes(include=["datetime"]):
        df_copy[col] = df_copy[col].dt.strftime("%Y-%m-%d")
    spec["data"] = {"values": df_copy.to_dict(orient="records")}
    return spec

# ✅ Correction du format de l’axe temporel
def improve_temporal_axis(spec: dict) -> dict:
    try:
        x_encoding = spec.get("encoding", {}).get("x", {})
        if x_encoding.get("type") == "temporal":
            x_encoding.setdefault("axis", {})
            x_encoding["axis"]["format"] = "%Y-%m"
            x_encoding["axis"]["labelAngle"] = -45
    except Exception as e:
        print("⚠️ Erreur dans le formatage de l'axe X :", e)
    return spec

# # 🚀 Point d’entrée
# if __name__ == "__main__":
#     df_name = "large_sales_dataset"
#     df = pd.read_csv("C:/Users/Fatma/Downloads/multi_dimensional_sales_dataset.csv")

   
#     user_query = "Montre l’évolution des ventes totales par produit et par région, en séparant les résultats par canal de vente."

#     base_spec = generate_vegalite_spec(df_name, df, user_query)
#     print("🧠 JSON généré par le LLM (avant injection des données) :\n")
#     print(json.dumps(base_spec, indent=2))

#     if "error" in base_spec:
#         print("❌ Erreur :", base_spec["error"])
#         print("🔎 Réponse brute :", base_spec["raw"])
#     else:
#         full_spec = inject_values(base_spec, df)
#         full_spec = improve_temporal_axis(full_spec)

#         print("📊 Aperçu des données injectées :")
#         for i, row in enumerate(full_spec["data"]["values"][:5]):
#             print(f"{i+1}. {row}")

#         output_file = "vegalite_output.json"
#         with open(output_file, "w", encoding="utf-8") as f:
#             json.dump(full_spec, f, indent=2)

#         print(f"\n✅ JSON Vega-Lite sauvegardé dans : {output_file}")
#         print("💡 Ouvre-le sur https://vega.github.io/editor/ pour visualiser le graphe.")