"""
Veille hebdomadaire multi-fonds.

Lit les liens de la semaine, recupere les cours, fait resumer les articles
par Mistral, et regenere le site statique.

Usage :
    python build.py               -> traite la semaine en cours
    python build.py 2026-S34      -> traite une semaine precise
    python build.py --all         -> retraite toutes les semaines disponibles
"""

import csv
import json
import os
import re
import sys
import time
import datetime as dt
from pathlib import Path

# --------------------------------------------------------------------------
# Reglages
# --------------------------------------------------------------------------

RACINE = Path(__file__).parent
CONFIG = RACINE / "config" / "fonds.json"
DOSSIER_LIENS = RACINE / "liens"
DOSSIER_SITE = RACINE / "site"
CACHE = RACINE / ".cache"

MODELE = "mistral-large-latest"
PAUSE_ENTRE_APPELS = 3          # secondes, pour rester sous le rate limit gratuit
JOURS_DE_COURS = 5              # nombre de seances affichees

# La cle API est lue depuis la variable d'environnement MISTRAL_API_KEY.
# Voir README.md pour la mise en place.


# --------------------------------------------------------------------------
# Cours de bourse
# --------------------------------------------------------------------------

def charger_cours(ticker, fin):
    """Retourne les dernieres seances : date, cours de cloture, variation %."""
    if not ticker:
        return []

    import yfinance as yf

    debut = fin - dt.timedelta(days=JOURS_DE_COURS * 3)
    hist = yf.Ticker(ticker).history(
        start=debut.isoformat(),
        end=(fin + dt.timedelta(days=1)).isoformat(),
        auto_adjust=False,
    )
    if hist.empty:
        print(f"    ! aucun cours pour {ticker}")
        return []

    hist = hist.tail(JOURS_DE_COURS + 1)
    seances = []
    precedent = None
    for date, ligne in hist.iterrows():
        cloture = float(ligne["Close"])
        variation = None if precedent is None else (cloture / precedent - 1) * 100
        seances.append({
            "date": date.strftime("%Y-%m-%d"),
            "dernier": round(cloture, 2),
            "variation": None if variation is None else round(variation, 2),
        })
        precedent = cloture

    return seances[-JOURS_DE_COURS:]


def devise_du_ticker(ticker):
    if ticker.endswith(".KS"):
        return "KRW"
    if ticker.endswith(".TW"):
        return "TWD"
    if ticker.endswith(".PA") or ticker.endswith(".AS"):
        return "EUR"
    return "USD"


def perf_semaine(seances):
    """Performance du premier au dernier cours de la periode affichee."""
    if len(seances) < 2:
        return None
    return round((seances[-1]["dernier"] / seances[0]["dernier"] - 1) * 100, 2)


# --------------------------------------------------------------------------
# Extraction des articles
# --------------------------------------------------------------------------

def extraire_article(url):
    """Recupere le texte d'un article. Utilise un cache disque."""
    import trafilatura

    CACHE.mkdir(exist_ok=True)
    cle = re.sub(r"[^a-zA-Z0-9]", "_", url)[:120]
    fichier = CACHE / f"{cle}.json"

    if fichier.exists():
        return json.loads(fichier.read_text(encoding="utf-8"))

    telecharge = trafilatura.fetch_url(url)
    if telecharge is None:
        print(f"    ! page inaccessible : {url}")
        return None

    texte = trafilatura.extract(telecharge, include_comments=False, include_tables=False)
    if not texte:
        print(f"    ! aucun texte extrait : {url}")
        return None

    meta = trafilatura.extract_metadata(telecharge)
    resultat = {
        "url": url,
        "titre": (meta.title if meta and meta.title else url),
        "source": (meta.sitename if meta and meta.sitename else ""),
        "date": (meta.date if meta and meta.date else ""),
        "texte": texte[:12000],
    }
    fichier.write_text(json.dumps(resultat, ensure_ascii=False), encoding="utf-8")
    return resultat


# --------------------------------------------------------------------------
# Resume par le modele
#
# Toute la dependance a Mistral est isolee ici. Pour changer de fournisseur
# (Groq, Anthropic, Ollama...), seule cette fonction est a reecrire.
# --------------------------------------------------------------------------

SYSTEME = """Tu es analyste actions dans une societe de gestion francaise.
Tu rediges la note hebdomadaire de suivi d'un fonds thematique.

Regles de redaction :
- Francais, ton factuel et sobre, registre professionnel de gestion d'actifs.
- 4 a 6 phrases, en un seul paragraphe, sans titre ni puces.
- Commence par le fait marquant de la semaine, pas par une generalite.
- Cite les chiffres precis quand ils figurent dans les articles (resultats,
  guidance, montants, pourcentages).
- Relie explicitement l'information au mouvement du cours observe : si le titre
  a monte ou baisse, dis ce qui l'explique, et signale les cas ou le cours ne
  reagit pas comme l'actualite le laisserait attendre.
- Termine par une phrase sur ce que cela implique pour la position dans le fonds
  (risque, catalyseur a venir, point de vigilance).
- Ne parle jamais des articles eux-memes ("selon l'article", "la presse
  rapporte"). Restitue l'information directement.
- Si les articles ne permettent pas de conclure, dis-le simplement plutot que
  de combler avec des generalites."""


def verifier_installation():
    """Controle la cle avant de commencer le travail."""
    if not os.environ.get("MISTRAL_API_KEY"):
        raise SystemExit(
            "\nCle API absente.\n"
            "  1. Cree une cle sur console.mistral.ai\n"
            "  2. setx MISTRAL_API_KEY \"ta_cle\"\n"
            "  3. Ferme et rouvre Anaconda Prompt\n"
        )


def appeler_modele(systeme, prompt):
    """Appel HTTP direct a l'API Mistral.

    Volontairement sans SDK : urllib fait partie de la bibliotheque standard,
    ce qui supprime une dependance et les problemes d'installation qui vont
    avec. Pour changer de fournisseur, seule cette fonction est a reecrire.
    """
    import urllib.request
    import urllib.error

    corps = json.dumps({
        "model": MODELE,
        "messages": [
            {"role": "system", "content": systeme},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
    }).encode("utf-8")

    requete = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=corps,
        headers={
            "Authorization": "Bearer " + os.environ["MISTRAL_API_KEY"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(requete, timeout=120) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 401:
            raise RuntimeError("cle API refusee (401) — verifie MISTRAL_API_KEY")
        if e.code == 429:
            raise RuntimeError("limite de debit atteinte (429) — augmente "
                               "PAUSE_ENTRE_APPELS en haut du script")
        raise RuntimeError(f"erreur HTTP {e.code} : {detail}")

    return donnees["choices"][0]["message"]["content"].strip()


def resumer(nom_titre, nom_fonds, poids, seances, articles):
    """Prepare le prompt et retourne le resume en francais."""

    if seances:
        lignes = [
            f"  {s['date']} : {s['dernier']}"
            + (f" ({s['variation']:+.2f} %)" if s["variation"] is not None else "")
            for s in seances
        ]
        bloc_cours = "\n".join(lignes)
        perf = perf_semaine(seances)
        if perf is not None:
            bloc_cours += f"\n  Performance sur la periode : {perf:+.2f} %"
    else:
        bloc_cours = "  Cours non disponibles."

    bloc_articles = "\n\n".join(
        f"--- Article {i} ({a.get('source') or 'source non identifiee'}, "
        f"{a.get('date') or 'date inconnue'}) ---\n{a['titre']}\n\n{a['texte']}"
        for i, a in enumerate(articles, 1)
    )

    prompt = f"""Valeur : {nom_titre}
Fonds : {nom_fonds}
Poids dans le fonds : {poids} %

Cours de cloture de la semaine :
{bloc_cours}

Articles a synthetiser :
{bloc_articles}

Redige le paragraphe de suivi hebdomadaire pour cette valeur."""

    return appeler_modele(SYSTEME, prompt)


# --------------------------------------------------------------------------
# Lecture des liens
# --------------------------------------------------------------------------

# Codes place de marche (format MIC) vers suffixe Yahoo Finance.
# Permet de coller directement des tickers du type XNAS:AAPL ou XKRX:000660.
SUFFIXES = {
    "XNAS": "", "XNYS": "", "XASE": "", "ARCX": "", "BATS": "",
    "XKRX": ".KS", "XKOS": ".KQ",
    "XPAR": ".PA", "XAMS": ".AS", "XBRU": ".BR", "XLIS": ".LS",
    "XLON": ".L", "XETR": ".DE", "XSWX": ".SW",
    "XMIL": ".MI", "XMAD": ".MC", "XSTO": ".ST", "XCSE": ".CO",
    "XTAI": ".TW", "XTKS": ".T", "XHKG": ".HK", "XSES": ".SI",
    "XTSE": ".TO", "XASX": ".AX",
}


# Noms de places usuels acceptes en plus des codes MIC.
SUFFIXES.update({
    "NASDAQ": "", "NSDQ": "", "NYSE": "", "AMEX": "",
    "KRX": ".KS", "KOSPI": ".KS", "KOSDAQ": ".KQ",
    "EPA": ".PA", "LSE": ".L", "ETR": ".DE", "TPE": ".TW", "TSE": ".T",
})

MOTIF_URL = re.compile(r"https?://[^\s;\"'<>]+")


def normaliser_ticker(brut):
    """XNAS:AAPL -> AAPL, XKRX:000660 -> 000660.KS, NASDAQ: SPCX -> SPCX."""
    t = brut.strip().strip('"').upper()
    if ":" not in t:
        return t
    place, code = t.split(":", 1)
    place, code = place.strip(), code.strip()
    if place not in SUFFIXES:
        print(f"    ! place inconnue : {place} (ticker conserve tel quel)")
        return code
    return code + SUFFIXES[place]


def lire_texte(chemin):
    """Lit un fichier quel que soit son encodage.

    Excel enregistre les CSV en Windows-1252 par defaut, pas en UTF-8 :
    les tirets longs et apostrophes typographiques cassent une lecture
    UTF-8 stricte.
    """
    donnees = Path(chemin).read_bytes()
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return donnees.decode(encodage)
        except UnicodeDecodeError:
            continue
    return donnees.decode("utf-8", errors="replace")


def lire_liens_texte(texte):
    """Retourne {ticker: [url, ...]} depuis du texte brut.

    Le ticker est le premier champ de la ligne. L'adresse est cherchee
    n'importe ou sur la ligne : les colonnes intermediaires (titre de
    l'article, notes) sont donc sans effet.
    """
    liens = {}
    ignorees = []

    for numero, brut in enumerate(texte.splitlines(), 1):
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue

        premier = re.split(r"[;,\t]", ligne, maxsplit=1)[0]
        ticker = normaliser_ticker(premier)
        if ticker in ("TICKER", ""):
            continue

        trouvees = MOTIF_URL.findall(ligne)
        if not trouvees:
            ignorees.append((numero, ticker))
            continue

        for url in trouvees:
            liens.setdefault(ticker, []).append(url.rstrip(".,"))

    return liens, ignorees


def lire_liens(chemin):
    """Idem, depuis un fichier."""
    liens, ignorees = lire_liens_texte(lire_texte(chemin))

    if ignorees:
        print(f"\n  {len(ignorees)} ligne(s) sans adresse web, ignoree(s) : "
              + ", ".join(t for _, t in ignorees[:10]))
        print("  Verifie que la colonne des adresses contient bien des "
              "https://..., pas seulement les titres.\n")

    return liens


def libelle_semaine(code):
    """2026-S34 -> 'semaine du 17-08'."""
    m = re.match(r"(\d{4})-S(\d{1,2})$", code)
    if not m:
        return code
    annee, num = int(m.group(1)), int(m.group(2))
    lundi = dt.date.fromisocalendar(annee, num, 1)
    return f"semaine du {lundi.strftime('%d-%m')}"


def semaine_courante():
    a, s, _ = dt.date.today().isocalendar()
    return f"{a}-S{s}"


# --------------------------------------------------------------------------
# Traitement d'une semaine
# --------------------------------------------------------------------------

def traiter_semaine(code, config):
    fichier = DOSSIER_LIENS / f"{code}.csv"
    if not fichier.exists():
        raise SystemExit(
            f"Fichier introuvable : {fichier}\n"
            f"Cree-le et colle tes liens au format TICKER;URL."
        )

    print(f"\n=== {code} ({libelle_semaine(code)}) ===")
    liens = lire_liens(fichier)
    print(f"{sum(len(v) for v in liens.values())} lien(s) sur {len(liens)} valeur(s)")

    annee, num = int(code[:4]), int(code.split("S")[1])
    vendredi = dt.date.fromisocalendar(annee, num, 5)
    fin = min(vendredi, dt.date.today())

    echecs = []
    sortie = {
        "semaine": code,
        "libelle": libelle_semaine(code),
        "genere_le": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonds": {},
    }

    for id_fonds, fonds in config.items():
        valeurs = []
        for titre in fonds["titres"]:
            ticker = titre["ticker"]
            print(f"  {titre['nom']}")

            seances = charger_cours(ticker, fin) if ticker else []
            urls = liens.get(ticker.upper(), [])

            articles = []
            for url in urls:
                article = extraire_article(url)
                if article:
                    articles.append(article)

            if articles:
                try:
                    resume = resumer(titre["nom"], fonds["nom"], titre["poids"],
                                     seances, articles)
                    print(f"    resume genere ({len(articles)} article(s))")
                except Exception as e:
                    resume = ""
                    echecs.append(f"{titre['nom']} : {type(e).__name__} {e}")
                    print(f"    ! echec du resume : {e}")
                time.sleep(PAUSE_ENTRE_APPELS)
            else:
                resume = ""

            valeurs.append({
                "nom": titre["nom"],
                "ticker": ticker,
                "devise": devise_du_ticker(ticker),
                "poids": titre["poids"],
                "cours": seances,
                "perf": perf_semaine(seances),
                "resume": resume,
                "sources": [{"url": a["url"], "titre": a["titre"], "source": a["source"]}
                            for a in articles],
            })

        sortie["fonds"][id_fonds] = {
            "nom": fonds["nom"],
            "description": fonds.get("description", ""),
            "valeurs": valeurs,
        }

    if echecs:
        print(f"\n  {len(echecs)} resume(s) en echec :")
        for e in echecs:
            print(f"    {e}")

    return sortie


# --------------------------------------------------------------------------
# Generation du site
# --------------------------------------------------------------------------

def ecrire_site(semaines):
    """Ecrit site/data.js. Pas de fetch : le site s'ouvre en double-clic."""
    semaines = dict(sorted(semaines.items(), reverse=True))
    contenu = "window.VEILLE = " + json.dumps(semaines, ensure_ascii=False, indent=1) + ";\n"
    (DOSSIER_SITE / "data.js").write_text(contenu, encoding="utf-8")
    print(f"\nSite mis a jour : {DOSSIER_SITE / 'index.html'}")


def charger_existant():
    fichier = DOSSIER_SITE / "data.js"
    if not fichier.exists():
        return {}
    texte = fichier.read_text(encoding="utf-8")
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        return {}
    try:
        return json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError:
        return {}


# --------------------------------------------------------------------------

def main():
    verifier_installation()
    config = json.loads(lire_texte(CONFIG))
    args = sys.argv[1:]

    if args and args[0] == "--all":
        codes = sorted(p.stem for p in DOSSIER_LIENS.glob("*.csv"))
        if not codes:
            raise SystemExit("Aucun fichier de liens dans liens/.")
        semaines = {}
    else:
        codes = [args[0]] if args else [semaine_courante()]
        semaines = charger_existant()

    for code in codes:
        semaines[code] = traiter_semaine(code, config)

    ecrire_site(semaines)


if __name__ == "__main__":
    main()
