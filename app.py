"""Qorb Santé — télé-expertise assistée par IA pour les zones rurales.

Lancer :  streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import ai
import db

st.set_page_config(page_title="Qorb Santé", page_icon="🩺", layout="wide")
db.init_db()

ICONS = {"Critique": "🔴", "Urgent": "🟠", "Semi-urgent": "🟡", "Non urgent": "🟢"}


# ---------- Barre latérale ----------
st.sidebar.title("🩺 Qorb Santé")
st.sidebar.caption("Rapprocher le spécialiste du patient")
page = st.sidebar.radio(
    "Espace",
    ["👩‍⚕️ Infirmier (centre rural)", "🧑‍⚕️ Médecin spécialiste", "📊 Impact & modèle économique"],
)
st.sidebar.divider()
engine = "Gemini" if os.getenv("GEMINI_API_KEY") else "Mode démo (règles)"
st.sidebar.write(f"**Moteur IA :** {engine}")
st.sidebar.info(ai.DISCLAIMER)

if st.sidebar.button("Charger des cas de démonstration"):
    demos = [
        dict(center="Centre de santé Ain Beni Mathar", patient_ref="P-001", age=62, sex="Homme",
             complaint="Douleur thoracique depuis 2 heures avec sueurs, irradiation bras gauche",
             history="Diabète, hypertension",
             vitals=dict(temperature=36.8, heart_rate=112, spo2=93, systolic=165, resp_rate=22, glycemia=1.9)),
        dict(center="Dispensaire Tafoughalt", patient_ref="P-002", age=4, sex="Femme",
             complaint="Fièvre depuis 3 jours, vomissements, refuse de boire",
             history="Aucun",
             vitals=dict(temperature=39.6, heart_rate=140, spo2=96, systolic=95, resp_rate=34, glycemia=0.9)),
        dict(center="Centre de santé Figuig", patient_ref="P-003", age=35, sex="Femme",
             complaint="Plaie du pied infectée depuis une semaine, pas de fièvre",
             history="Aucun", vitals=dict(temperature=37.2, heart_rate=84, spo2=98, systolic=120)),
    ]
    for d in demos:
        d.update(image=None, image_mime=None)
        analysis = ai.rule_based_triage(d)
        db.add_case(d["center"], d["patient_ref"], d["age"], d["sex"], d["complaint"],
                    d["history"], d["vitals"], None, None, analysis, True)
    st.sidebar.success("3 cas de démo ajoutés.")


def show_analysis(a):
    icon = ICONS.get(a["level"], "⚪")
    st.markdown(f"### {icon} Niveau : **{a['level']}** — score {a['score']}/10")
    st.progress(a["score"] / 10)
    st.write(f"**Délai cible :** {a.get('delay', '')}  |  **Orientation :** {a.get('orientation', '')}")
    if a.get("summary"):
        st.write("**Résumé structuré :**")
        st.write(a["summary"])
    c1, c2 = st.columns(2)
    with c1:
        st.write("**⚠️ Signes d'alarme**")
        for f in a.get("red_flags", []):
            st.write(f"- {f}")
    with c2:
        st.write("**❓ Questions à poser en priorité**")
        for q in a.get("questions", []):
            st.write(f"- {q}")
    if a.get("suggested_exams"):
        st.write("**🔬 Examens suggérés :** " + ", ".join(a["suggested_exams"]))
    st.caption(f"Moteur : {a.get('engine', '?')} — {ai.DISCLAIMER}")


# ---------- Page infirmier ----------
if page.startswith("👩"):
    st.title("Espace infirmier")
    st.write("Saisissez le dossier du patient. L'IA le structure, évalue l'urgence et l'envoie au spécialiste.")

    tab_new, tab_follow = st.tabs(["Nouveau cas", "Suivi de mes cas"])

    with tab_new:
        with st.form("new_case"):
            c1, c2, c3 = st.columns(3)
            center = c1.text_input("Centre de santé", "Centre de santé rural")
            patient_ref = c2.text_input("Référence patient (pas de nom)", placeholder="P-004")
            age = c3.number_input("Âge", 0, 120, 30)
            sex = st.selectbox("Sexe", ["Femme", "Homme"])
            complaint = st.text_area(
                "Motif / description des symptômes (darija, français ou arabe)",
                placeholder="Ex: l'3yan 3ndo wja3 f sder men sa3tin...")
            history = st.text_area("Antécédents, traitements, allergies")
            st.write("**Constantes** (laisser à 0 si non mesuré)")
            v1, v2, v3, v4, v5, v6 = st.columns(6)
            temp = v1.number_input("Temp °C", 0.0, 45.0, 0.0, 0.1)
            hr = v2.number_input("FC /min", 0, 250, 0)
            spo2 = v3.number_input("SpO2 %", 0, 100, 0)
            sys_ = v4.number_input("PAS mmHg", 0, 300, 0)
            rr = v5.number_input("FR /min", 0, 80, 0)
            gly = v6.number_input("Glycémie g/L", 0.0, 8.0, 0.0, 0.1)
            img = st.file_uploader("Photo (plaie, radio, ECG...)", type=["jpg", "jpeg", "png"])
            consent = st.checkbox("Le patient a donné son consentement à la transmission de ses données de santé.")
            submitted = st.form_submit_button("Analyser et envoyer au spécialiste", type="primary")

        if submitted:
            if not consent:
                st.error("Le consentement du patient est obligatoire (loi 09-08).")
            elif not complaint.strip():
                st.error("Décrivez les symptômes.")
            else:
                vitals = {k: v for k, v in dict(temperature=temp, heart_rate=hr, spo2=spo2,
                                                systolic=sys_, resp_rate=rr, glycemia=gly).items() if v}
                data = dict(age=age, sex=sex, complaint=complaint, history=history, vitals=vitals,
                            image=img.getvalue() if img else None,
                            image_mime=img.type if img else None)
                with st.spinner("Analyse en cours..."):
                    analysis = ai.analyze_case(data)
                cid = db.add_case(center, patient_ref or "N/A", age, sex, complaint, history, vitals,
                                  data["image"], data["image_mime"], analysis, consent)
                st.success(f"Cas n°{cid} envoyé au spécialiste.")
                show_analysis(analysis)
                if analysis["score"] >= 8:
                    st.error("🚨 CAS CRITIQUE : appelez immédiatement le SAMU en parallèle.")

    with tab_follow:
        cases = db.list_cases()
        if not cases:
            st.info("Aucun cas pour le moment.")
        for c in cases:
            with st.expander(f"{ICONS.get(c['level'], '')} Cas #{c['id']} — {c['patient_ref']} — {c['status']}"):
                st.write(c["complaint"])
                if c["reply"]:
                    st.success("**Réponse du spécialiste :**\n\n" + c["reply"])
                else:
                    st.warning("En attente de réponse du spécialiste.")

# ---------- Page spécialiste ----------
elif page.startswith("🧑"):
    st.title("Espace médecin spécialiste")
    st.write("Les cas sont triés **du plus urgent au moins urgent**.")
    pending = db.list_cases(status="En attente")
    if not pending:
        st.info("Aucun cas en attente. Utilisez « Charger des cas de démonstration » dans le menu.")

    def make_draft(case_id):
        case = db.get_case(case_id)
        st.session_state[f"reply_{case_id}"] = ai.draft_reply(case, st.session_state.get(f"notes_{case_id}", ""))

    for c in pending:
        with st.expander(f"{ICONS.get(c['level'], '')} #{c['id']} — {c['level']} ({c['score']}/10) — "
                         f"{c['age']} ans, {c['sex']} — {c['center']}", expanded=c["score"] >= 8):
            left, right = st.columns([3, 2])
            with left:
                show_analysis(c["analysis"])
                st.write("**Récit de l'infirmier :**", c["complaint"])
                if c["history"]:
                    st.write("**Antécédents :**", c["history"])
                if c["vitals"]:
                    st.write("**Constantes :**", c["vitals"])
            with right:
                if c["image"]:
                    st.image(c["image"], caption="Image jointe", use_container_width=True)
                st.text_input("Notes pour l'IA (facultatif)", key=f"notes_{c['id']}")
                st.button("✨ Générer un brouillon de réponse", key=f"draft_{c['id']}",
                          on_click=make_draft, args=(c["id"],))
                reply = st.text_area("Votre réponse (vous validez et modifiez)", key=f"reply_{c['id']}", height=200)
                if st.button("✅ Envoyer la réponse", key=f"send_{c['id']}", type="primary"):
                    if reply.strip():
                        db.answer_case(c["id"], reply.strip())
                        st.rerun()
                    else:
                        st.error("Rédigez une réponse avant d'envoyer.")

# ---------- Page impact ----------
else:
    st.title("Impact & modèle économique")
    s = db.stats()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cas reçus", s["total"])
    m2.metric("En attente", s["pending"])
    m3.metric("Répondus", s["answered"])
    m4.metric("Délai moyen de réponse", f"{s['avg_delay_min']:.1f} min" if s["avg_delay_min"] is not None else "—")
    if s["by_level"]:
        st.bar_chart(pd.Series(s["by_level"], name="Cas par niveau d'urgence"))

    st.subheader("Simulateur de coûts évités")
    st.caption("⚠️ Hypothèses modifiables : à remplacer par des données officielles (Ministère de la Santé, "
               "études locales) avant la présentation.")
    a, b = st.columns(2)
    with a:
        referrals = st.slider("Patients adressés au spécialiste / mois / centre", 10, 500, 100)
        centers = st.slider("Nombre de centres équipés", 1, 100, 10)
        avoidable = st.slider("% de déplacements évitables grâce à la télé-expertise", 10, 80, 40)
    with b:
        trip_cost = st.number_input("Coût moyen d'un déplacement (MAD : transport + perte de revenu)", 50, 2000, 300)
        tele_cost = st.number_input("Coût d'une télé-expertise (MAD)", 5, 500, 50)
        subscription = st.number_input("Abonnement mensuel / centre (MAD)", 0, 20000, 1500)
    avoided = referrals * centers * avoidable / 100
    saving = avoided * (trip_cost - tele_cost) * 12
    revenue = subscription * centers * 12
    r1, r2, r3 = st.columns(3)
    r1.metric("Déplacements évités / an", f"{avoided * 12:,.0f}")
    r2.metric("Économie annuelle pour les familles", f"{saving:,.0f} MAD")
    r3.metric("Revenu annuel de la plateforme", f"{revenue:,.0f} MAD")

    st.subheader("Cadre légal & éthique")
    st.markdown(
        "- **Consentement** explicite du patient avant toute transmission.\n"
        "- **Minimisation** : référence patient, pas de nom ni de CIN.\n"
        "- **Loi 09-08 / CNDP** : déclaration du traitement, hébergement sécurisé des données de santé.\n"
        "- **Human-in-the-loop** : l'IA oriente, le médecin décide.\n"
        "- **Garde-fou** : le score final ne peut jamais être inférieur à celui des règles cliniques."
    )
