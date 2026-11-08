# Qorb Santé — Télé-expertise assistée par IA

Plateforme qui connecte les infirmiers des centres de santé ruraux aux médecins spécialistes.
L'IA structure le dossier, évalue l'urgence et priorise les cas. **Le médecin garde la décision finale.**

## Lancer le projet (VS Code)

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux : source venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

Le navigateur s'ouvre sur http://localhost:8501.

**Clé Gemini (optionnelle)** : copie `.env.example` en `.env` et mets ta clé.
Sans clé, l'app fonctionne en mode démo avec un triage par règles cliniques.

## Scénario de démo (5 minutes)

1. Menu gauche → **Charger des cas de démonstration**.
2. **Espace infirmier** → saisir un nouveau cas (ex : douleur thoracique, SpO2 92%) → voir l'analyse IA.
3. **Espace médecin** → les cas sont triés par urgence → « Générer un brouillon » → modifier → envoyer.
4. Retour **Espace infirmier → Suivi** : la réponse est arrivée.
5. **Impact & modèle économique** → simulateur de coûts évités.

## Architecture

| Fichier | Rôle |
|---|---|
| `app.py` | Interface Streamlit (3 espaces) |
| `ai.py` | Triage : LLM Gemini (texte + image) **+ garde-fou par règles** |
| `db.py` | Base SQLite (`qorb.db`) |

### Points à expliquer au jury
- **Garde-fou** : score final = max(score IA, score règles) → l'IA ne sous-évalue jamais un signe d'alarme.
- **Human-in-the-loop** : brouillon IA, validation du médecin obligatoire.
- **Données** : consentement obligatoire, référence patient (pas de nom), cible loi 09-08 / CNDP.
- **Limites actuelles (prototype)** : pas d'authentification, SQLite local, règles cliniques simplifiées
  non validées par un médecin → feuille de route : login par rôle, hébergement agréé, validation clinique.
