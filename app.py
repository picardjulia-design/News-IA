"""
Veille hebdomadaire — interface.

Lancer avec :  streamlit run app.py
"""

import datetime as dt
import json
import os
from pathlib import Path

import streamlit as st

import build

RACINE = Path(__file__).parent
DOSSIER_DATA = RACINE / "data"
DOSSIER_LIENS = RACINE / "liens"
DOSSIER_DATA.mkdir(exist_ok=True)
DOSSIER_LIENS.mkdir(exist_ok=True)

st.set_page_config(page_title="Veille hebdomadaire", page_icon="//", layout="wide")

st.markdown("""
<style>
  .bandeau { background:#0E2745; color:#fff; padding:18px 26px; margin:-1rem -1rem 1.5rem;
             display:flex; align-items:center; gap:14px; }
  .bandeau b { font-size:20px; letter-spacing:.14em; }
  .bandeau span { font-size:12px; letter-spacing:.08em; text-transform:uppercase;
                  color:rgba(255,255,255,.72); border-left:1px solid rgba(255,255,255,.3);
                  padding-left:14px; }
  .hausse { color:#0F8B6C; font-weight:600; }
  .baisse { color:#C0392B; font-weight:600; }
</style>
<div class="bandeau"><b>CPR AM</b><span>Veille hebdomadaire</span></div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Etat
# --------------------------------------------------------------------------

def config():
    return json.loads(build.lire_texte(build.CONFIG))


def semaines_enregistrees():
    return sorted((p.stem for p in DOSSIER_DATA.glob("*.json")), reverse=True)


def charger(code):
    f = DOSSIER_DATA / f"{code}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def enregistrer(code, donnees):
    (DOSSIER_DATA / f"{code}.json").write_text(
        json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def exporter_site():
    """Regenere site/data.js a partir de toutes les semaines enregistrees."""
    tout = {c: charger(c) for c in semaines_enregistrees()}
    build.DOSSIER_SITE.mkdir(exist_ok=True)
    (build.DOSSIER_SITE / "data.js").write_text(
        "window.VEILLE = " + json.dumps(tout, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")
    return len(tout)


# --------------------------------------------------------------------------
# Barre laterale
# --------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Configuration")

    cle_env = os.environ.get("MISTRAL_API_KEY", "")
    if cle_env:
        st.success("Cle API detectee")
    else:
        cle = st.text_input("Cle API Mistral", type="password",
                            help="console.mistral.ai — non enregistree sur le disque")
        if cle:
            os.environ["MISTRAL_API_KEY"] = cle

    st.divider()

    aujourdhui = dt.date.today()
    annee, num, _ = aujourdhui.isocalendar()
    defaut = f"{annee}-S{num}"

    connues = semaines_enregistrees()
    choix = [defaut] + [c for c in connues if c != defaut]
    code = st.selectbox("Semaine", choix,
                        format_func=lambda c: f"{build.libelle_semaine(c)}  ({c})")

    cfg = config()
    id_fonds = st.selectbox("Fonds", list(cfg),
                            format_func=lambda k: cfg[k]["nom"])

    st.divider()
    if st.button("Exporter le site statique", use_container_width=True):
        n = exporter_site()
        st.success(f"{n} semaine(s) exportee(s) vers site/index.html")


fonds = cfg[id_fonds]
existant = charger(code)
onglet_saisie, onglet_resultats = st.tabs(["Saisie des liens", "Resultats"])


# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------

with onglet_saisie:
    st.caption(
        "Un lien par ligne, precede du ticker. Les colonnes supplementaires "
        "(titre de l'article, notes) sont ignorees, tu peux coller directement "
        "depuis Excel."
    )

    fichier_liens = DOSSIER_LIENS / f"{code}.csv"
    depart = build.lire_texte(fichier_liens) if fichier_liens.exists() else ""

    texte = st.text_area(
        "Liens de la semaine", value=depart, height=260,
        placeholder="NVDA;https://www.reuters.com/...\nAAPL;https://finance.yahoo.com/...",
        label_visibility="collapsed",
    )

    liens, ignorees = build.lire_liens_texte(texte) if texte.strip() else ({}, [])
    tickers_connus = {t["ticker"] for t in fonds["titres"] if t["ticker"]}
    inconnus = set(liens) - tickers_connus

    c1, c2, c3 = st.columns(3)
    c1.metric("Liens", sum(len(v) for v in liens.values()))
    c2.metric("Valeurs couvertes", f"{len(set(liens) & tickers_connus)} / {len(tickers_connus)}")
    c3.metric("Lignes ignorees", len(ignorees))

    if inconnus:
        st.warning("Tickers absents du fonds, ils seront ignores : "
                   + ", ".join(sorted(inconnus)))
    if ignorees:
        st.info("Lignes sans adresse https, ignorees : "
                + ", ".join(t for _, t in ignorees[:10]))

    a_traiter = st.multiselect(
        "Valeurs a traiter",
        [t["nom"] for t in fonds["titres"]],
        default=[t["nom"] for t in fonds["titres"] if t["ticker"] in liens],
    )

    lancer = st.button("Generer les resumes", type="primary",
                       disabled=not a_traiter, use_container_width=True)

    if lancer:
        if not os.environ.get("MISTRAL_API_KEY"):
            st.error("Renseigne ta cle API dans la barre laterale.")
            st.stop()

        fichier_liens.write_text(texte, encoding="utf-8")

        annee_c, num_c = int(code[:4]), int(code.split("S")[1])
        vendredi = dt.date.fromisocalendar(annee_c, num_c, 5)
        fin = min(vendredi, dt.date.today())

        anciennes = {}
        if existant and id_fonds in existant.get("fonds", {}):
            anciennes = {v["nom"]: v for v in existant["fonds"][id_fonds]["valeurs"]}

        valeurs, soucis = [], []
        barre = st.progress(0.0)
        journal = st.empty()

        for i, titre in enumerate(fonds["titres"]):
            nom, ticker = titre["nom"], titre["ticker"]

            if nom not in a_traiter:
                valeurs.append(anciennes.get(nom, {
                    "nom": nom, "ticker": ticker, "devise": build.devise_du_ticker(ticker),
                    "poids": titre["poids"], "cours": [], "perf": None,
                    "resume": "", "sources": [],
                }))
                barre.progress((i + 1) / len(fonds["titres"]))
                continue

            journal.caption(f"{nom} — cours")
            try:
                seances = build.charger_cours(ticker, fin) if ticker else []
            except Exception as e:
                seances = []
                soucis.append(f"{nom} : cours indisponibles ({e})")

            articles = []
            for url in liens.get(ticker, []):
                journal.caption(f"{nom} — lecture de l'article")
                try:
                    a = build.extraire_article(url)
                except Exception as e:
                    a = None
                    soucis.append(f"{nom} : {url[:50]} ({e})")
                if a:
                    articles.append(a)
                else:
                    soucis.append(f"{nom} : article illisible — {url[:60]}")

            resume = ""
            if articles:
                journal.caption(f"{nom} — redaction du resume")
                try:
                    resume = build.resumer(nom, fonds["nom"], titre["poids"],
                                           seances, articles)
                except Exception as e:
                    soucis.append(f"{nom} : echec du resume ({e})")

            valeurs.append({
                "nom": nom, "ticker": ticker, "devise": build.devise_du_ticker(ticker),
                "poids": titre["poids"], "cours": seances,
                "perf": build.perf_semaine(seances), "resume": resume,
                "sources": [{"url": a["url"], "titre": a["titre"], "source": a["source"]}
                            for a in articles],
            })
            barre.progress((i + 1) / len(fonds["titres"]))

        journal.empty()
        barre.empty()

        donnees = existant or {"semaine": code, "libelle": build.libelle_semaine(code),
                               "fonds": {}}
        donnees["genere_le"] = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
        donnees["fonds"][id_fonds] = {
            "nom": fonds["nom"], "description": fonds.get("description", ""),
            "valeurs": valeurs,
        }
        enregistrer(code, donnees)

        reussis = sum(1 for v in valeurs if v["resume"])
        st.success(f"{reussis} resume(s) generes. Va dans l'onglet Resultats.")
        if soucis:
            with st.expander(f"{len(soucis)} avertissement(s)"):
                for s in soucis:
                    st.caption(s)


# --------------------------------------------------------------------------
# Resultats
# --------------------------------------------------------------------------

with onglet_resultats:
    donnees = charger(code)
    if not donnees or id_fonds not in donnees.get("fonds", {}):
        st.info("Rien pour cette semaine. Genere les resumes dans l'onglet precedent.")
    else:
        valeurs = donnees["fonds"][id_fonds]["valeurs"]
        cotees = [v for v in valeurs if v.get("perf") is not None]
        poids_total = sum(v["poids"] for v in cotees)
        pondere = (sum(v["perf"] * v["poids"] for v in cotees) / poids_total
                   if poids_total else None)

        c1, c2, c3 = st.columns(3)
        c1.metric("Performance ponderee",
                  "–" if pondere is None else f"{pondere:+.2f} %")
        if cotees:
            meilleur = max(cotees, key=lambda v: v["perf"])
            pire = min(cotees, key=lambda v: v["perf"])
            c2.metric(meilleur["nom"], f"{meilleur['perf']:+.2f} %")
            c3.metric(pire["nom"], f"{pire['perf']:+.2f} %")
        st.caption(f"Genere le {donnees.get('genere_le', '')}")

        st.divider()
        modifie = False

        for v in valeurs:
            perf = v.get("perf")
            etiquette = f"{v['nom']}   ·   {v['poids']} %"
            if perf is not None:
                etiquette += f"   ·   {perf:+.2f} %"
            if not v.get("resume"):
                etiquette += "   ·   sans commentaire"

            with st.expander(etiquette, expanded=bool(v.get("resume"))):
                gauche, droite = st.columns([1, 3])

                with gauche:
                    if v.get("cours"):
                        st.dataframe(
                            [{"Date": c["date"][5:].replace("-", "/"),
                              "Cours": c["dernier"],
                              "Var.": "–" if c["variation"] is None
                                      else f"{c['variation']:+.2f} %"}
                             for c in v["cours"]],
                            hide_index=True, use_container_width=True)
                    else:
                        st.caption("Cours indisponibles.")

                with droite:
                    nouveau = st.text_area(
                        "Commentaire", value=v.get("resume", ""), height=190,
                        key=f"txt_{code}_{id_fonds}_{v['nom']}",
                        label_visibility="collapsed",
                        placeholder="Aucun commentaire. Tu peux en ecrire un ici.")
                    if nouveau != v.get("resume", ""):
                        v["resume"] = nouveau
                        modifie = True

                    for s in v.get("sources", []):
                        st.caption(f"[{s.get('source') or 'source'} — {s['titre'][:80]}]({s['url']})")

        if modifie:
            enregistrer(code, donnees)

        st.divider()
        st.download_button(
            "Telecharger la semaine (JSON)",
            json.dumps(donnees, ensure_ascii=False, indent=1),
            file_name=f"{code}.json", mime="application/json")
