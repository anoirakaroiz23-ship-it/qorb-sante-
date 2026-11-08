"""Moteur IA de Qorb Santé.

- Si GEMINI_API_KEY est défini  -> analyse par un LLM multimodal (texte + image).
- Sinon (ou si l'API échoue)    -> mode démo : triage par règles cliniques simples.

SÉCURITÉ : le score final = max(score LLM, score des règles). L'IA ne peut donc
jamais "sous-évaluer" un signe d'alarme détecté par les règles.
L'IA est une AIDE À LA DÉCISION, jamais un diagnostic.
"""
import base64
import json
import os

import requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DISCLAIMER = (
    "Aide à la décision générée par IA — ne remplace pas le jugement clinique. "
    "La décision finale appartient toujours au médecin."
)

LEVELS = [  # (score minimum, niveau, délai cible)
    (8, "Critique", "Immédiat : appeler le SAMU / évacuer"),
    (6, "Urgent", "Avis spécialiste < 1 heure"),
    (4, "Semi-urgent", "Avis spécialiste < 24 heures"),
    (1, "Non urgent", "Suivi local, avis différé"),
]

# Mots-clés d'alarme (français, darija translittérée, arabe) -> points
RED_FLAGS = {
    "douleur thoracique": 4, "douleur poitrine": 4, "dard sder": 4, "wja3 sder": 4, "ألم في الصدر": 4,
    "difficulté respiratoire": 4, "essoufflement": 3, "dyq nefs": 4, "ضيق التنفس": 4, "s3ib nefs": 4,
    "perte de connaissance": 5, "inconscient": 5, "syncope": 4, "ghma": 4, "إغماء": 4,
    "convulsion": 5, "crise convulsive": 5, "تشنج": 5,
    "hémorragie": 5, "hemorragie": 5, "saignement abondant": 5, "nzif": 4, "نزيف": 4,
    "paralysie": 5, "déficit": 3, "bouche déviée": 5, "troubles de la parole": 4, "شلل": 5,
    "enceinte": 2, "grossesse": 2, "hamel": 2, "حامل": 2,
    "fièvre": 1, "skhana": 1, "حمى": 1,
    "traumatisme": 2, "chute": 1, "fracture": 2, "brûlure": 2, "hrq": 2,
    "vomissements": 1, "diarrhée": 1, "déshydratation": 2,
    "confusion": 3, "désorienté": 3,
    "morsure": 2, "piqûre": 2, "intoxication": 4, "tentative de suicide": 5,
}


def _level_from_score(score):
    for minimum, name, delay in LEVELS:
        if score >= minimum:
            return name, delay
    return "Non urgent", LEVELS[-1][2]


def rule_based_triage(data):
    """Triage par règles : constantes + mots-clés + âge. Retourne le dict d'analyse."""
    score, flags = 1, []
    v = data.get("vitals", {})
    age = data.get("age") or 0

    def add(points, msg):
        nonlocal score
        score += points
        flags.append(msg)

    spo2 = v.get("spo2")
    if spo2 and spo2 < 90: add(5, f"SpO2 très basse ({spo2}%)")
    elif spo2 and spo2 < 94: add(2, f"SpO2 basse ({spo2}%)")

    pas = v.get("systolic")
    if pas and pas < 90: add(4, f"Hypotension (PAS {pas} mmHg)")
    elif pas and pas >= 180: add(3, f"Hypertension sévère (PAS {pas} mmHg)")

    fc = v.get("heart_rate")
    if fc and (fc > 130 or fc < 45): add(3, f"Fréquence cardiaque anormale ({fc}/min)")
    elif fc and fc > 110: add(1, f"Tachycardie ({fc}/min)")

    t = v.get("temperature")
    if t and t >= 40: add(3, f"Fièvre très élevée ({t}°C)")
    elif t and t >= 38.5: add(1, f"Fièvre ({t}°C)")
    elif t and t < 35: add(3, f"Hypothermie ({t}°C)")

    fr = v.get("resp_rate")
    if fr and fr > 30: add(3, f"Polypnée ({fr}/min)")

    gly = v.get("glycemia")
    if gly and gly < 0.5: add(4, f"Hypoglycémie sévère ({gly} g/L)")
    elif gly and gly > 3: add(3, f"Hyperglycémie sévère ({gly} g/L)")

    if age and (age < 2 or age >= 75):
        add(1, "Terrain à risque (âge extrême)")

    text = f"{data.get('complaint', '')} {data.get('history', '')}".lower()
    kw_points = 0
    for kw, pts in RED_FLAGS.items():
        if kw in text:
            kw_points = max(kw_points, pts) + (1 if kw_points else 0)
            if pts >= 3:
                flags.append(f"Signe d'alarme dans le récit : « {kw} »")
    score += kw_points

    score = max(1, min(10, score))
    level, delay = _level_from_score(score)

    questions = [
        "Depuis quand les symptômes ont-ils commencé, et comment ont-ils évolué ?",
        "Antécédents connus (diabète, HTA, cardiopathie, asthme, grossesse) ?",
        "Traitements en cours et allergies connues ?",
    ]
    if "thorac" in text or "poitrine" in text or "sder" in text:
        questions.append("La douleur irradie-t-elle (bras, mâchoire, dos) ? Un ECG est-il disponible ?")
    if "fi" in text and "vre" in text:
        questions.append("Raideur de nuque, éruption cutanée ou vomissements associés ?")

    return {
        "summary": (data.get("complaint") or "").strip()[:400],
        "score": score,
        "level": level,
        "delay": delay,
        "red_flags": flags or ["Aucun signe d'alarme majeur détecté par les règles"],
        "questions": questions,
        "suggested_exams": [],
        "orientation": "Évacuation / SAMU" if score >= 8 else (
            "Télé-expertise prioritaire" if score >= 6 else "Télé-expertise standard"),
        "engine": "règles (mode démo)",
        "disclaimer": DISCLAIMER,
    }


def _build_prompt(data):
    return f"""Tu es un assistant d'aide à la décision pour un infirmier d'un centre de santé rural au Maroc.
Tu NE POSES PAS de diagnostic définitif. Tu structures le dossier et évalues le niveau d'urgence.

DOSSIER:
- Âge: {data.get('age')} ans, Sexe: {data.get('sex')}
- Motif / récit (peut être en darija, français ou arabe): {data.get('complaint')}
- Antécédents / traitements: {data.get('history') or 'non précisé'}
- Constantes: {json.dumps(data.get('vitals', {}), ensure_ascii=False)}

Réponds UNIQUEMENT avec un JSON valide, en français, avec ces clés:
- "summary": résumé médical structuré et concis (3-5 phrases)
- "score": entier de 1 (non urgent) à 10 (critique)
- "red_flags": liste de signes d'alarme identifiés
- "questions": liste de 3 à 5 questions que l'infirmier doit poser/vérifier en priorité
- "suggested_exams": liste d'examens simples réalisables en centre rural
- "orientation": une de "Évacuation / SAMU", "Télé-expertise prioritaire", "Télé-expertise standard", "Suivi local"
"""


def llm_triage(data, api_key):
    parts = [{"text": _build_prompt(data)}]
    if data.get("image"):
        parts.append({"inline_data": {
            "mime_type": data.get("image_mime") or "image/jpeg",
            "data": base64.b64encode(data["image"]).decode(),
        }})
    r = requests.post(
        API_URL.format(model=MODEL),
        params={"key": api_key},
        json={
            "contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        },
        timeout=40,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    out = json.loads(text)
    out["score"] = max(1, min(10, int(out.get("score", 5))))
    out.setdefault("red_flags", [])
    out.setdefault("questions", [])
    out.setdefault("suggested_exams", [])
    out.setdefault("orientation", "Télé-expertise standard")
    return out


def analyze_case(data):
    """Point d'entrée : LLM si possible, règles toujours (garde-fou)."""
    rules = rule_based_triage(data)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return rules
    try:
        llm = llm_triage(data, api_key)
    except Exception as e:  # réseau, quota, JSON invalide...
        rules["engine"] = f"règles (LLM indisponible : {type(e).__name__})"
        return rules

    final_score = max(llm["score"], rules["score"])  # garde-fou de sécurité
    level, delay = _level_from_score(final_score)
    merged_flags = list(dict.fromkeys(llm["red_flags"] + [f for f in rules["red_flags"] if not f.startswith("Aucun")]))
    llm.update({
        "score": final_score, "level": level, "delay": delay,
        "red_flags": merged_flags or rules["red_flags"],
        "engine": f"{MODEL} + garde-fou règles",
        "disclaimer": DISCLAIMER,
    })
    return llm


def draft_reply(case, notes=""):
    """Brouillon de réponse du spécialiste (à relire et modifier par le médecin)."""
    a = case["analysis"]
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            prompt = (
                "Tu aides un médecin spécialiste à rédiger sa réponse de télé-expertise à un infirmier "
                "de centre rural. Rédige en français simple, clair, en puces: conduite à tenir, examens à "
                "faire, traitement à débuter si pertinent, critères d'évacuation, et quand recontacter. "
                "Ce n'est qu'un BROUILLON que le médecin validera.\n\n"
                f"Dossier: âge {case['age']}, sexe {case['sex']}, motif: {case['complaint']}, "
                f"constantes: {json.dumps(case['vitals'], ensure_ascii=False)}, "
                f"résumé IA: {a.get('summary')}, signes d'alarme: {a.get('red_flags')}.\n"
                f"Notes du médecin: {notes or 'aucune'}"
            )
            r = requests.post(
                API_URL.format(model=MODEL), params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.3}},
                timeout=40,
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass
    lines = [
        f"Cas {case['level']} (score {case['score']}/10) — {a.get('orientation', '')}",
        "",
        "Conduite à tenir proposée :",
        "- Surveiller les constantes toutes les 30 minutes et noter l'évolution.",
        "- Compléter l'examen clinique avec les questions listées dans le dossier.",
    ]
    if case["score"] >= 8:
        lines.append("- ÉVACUATION IMMÉDIATE : appeler le SAMU et préparer le transfert.")
    elif case["score"] >= 6:
        lines.append("- Prévoir un transfert si pas d'amélioration sous 1 heure.")
    lines += ["- Me recontacter avec les nouvelles constantes dans 2 heures.", "",
              "(Brouillon généré en mode démo — à adapter par le médecin.)"]
    return "\n".join(lines)
