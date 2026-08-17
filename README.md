# Veille hebdomadaire — mode d'emploi

## Ce que fait le projet

Tu colles des liens d'articles dans un fichier. Le script récupère les cours,
lit les articles, les fait synthétiser par Mistral, et régénère le site.

```
veille/
├── config/fonds.json      ← tes fonds, tes valeurs, leurs poids
├── liens/2026-S34.csv     ← LES LIENS DE LA SEMAINE (c'est ici que tu écris)
├── build.py               ← le script à lancer
└── site/
    ├── index.html         ← le site (double-clic pour l'ouvrir)
    ├── style.css          ← les couleurs, tout en haut du fichier
    ├── app.js
    └── data.js            ← généré par build.py, ne pas éditer
```

---

## Installation (une seule fois)

**1. Les bibliothèques.** Ouvre Anaconda Prompt et lance :

```
pip install yfinance trafilatura mistralai
```

**2. La clé Mistral.** Crée un compte sur console.mistral.ai, génère une clé
API, puis déclare-la comme variable d'environnement.

Windows, dans Anaconda Prompt :
```
setx MISTRAL_API_KEY "ta_cle_ici"
```
Ferme et rouvre Anaconda Prompt pour que ce soit pris en compte.

macOS / Linux, dans le terminal :
```
echo 'export MISTRAL_API_KEY="ta_cle_ici"' >> ~/.zshrc
source ~/.zshrc
```

Ne mets jamais la clé directement dans le code : si tu publies le projet un
jour, elle partirait avec.

---

## La routine de chaque semaine

**1. Duplique le fichier de liens** et renomme-le avec la semaine ISO en cours.
Semaine du 24 août 2026 → `liens/2026-S35.csv`.

**2. Colle tes liens**, un par ligne, au format `TICKER;URL` :

```
NVDA;https://www.reuters.com/technology/nvidia-earnings-...
NVDA;https://www.lesechos.fr/finance-marches/...
AAPL;https://www.bloomberg.com/news/...
```

Il faut l'adresse complete de l'article, pas son titre. Le reflexe : ouvrir
l'article, cliquer dans la barre d'adresse du navigateur (`Ctrl+L`), copier.
Une ligne sans adresse valide est signalee au lancement et ignoree.

Les tickers acceptent aussi le format place de marche de ton terminal :
`XNAS:AAPL`, `XKRX:000660`, `XPAR:MC`, `NASDAQ: SPCX`. Ils sont convertis
automatiquement.

Tu peux garder des colonnes intermediaires (titre de l'article, notes) : seuls
le premier champ, lu comme ticker, et la premiere adresse `https://` de la
ligne sont utilises. Un export Excel a trois colonnes fonctionne tel quel.

Plusieurs liens pour la même valeur sont synthétisés ensemble en un seul
paragraphe. Une valeur sans lien apparaît quand même sur le site, avec ses
cours, simplement sans commentaire.

**3. Lance le script.** Dans Anaconda Prompt, place-toi dans le dossier puis :

```
cd chemin/vers/veille
python build.py
```

Le script traite la semaine en cours par défaut. Pour en refaire une autre :
`python build.py 2026-S34`. Pour tout régénérer : `python build.py --all`.

**4. Ouvre `site/index.html`** en double-cliquant dessus. Le sélecteur en haut
à droite permet de remonter l'historique des semaines.

---

## Ajouter un fonds

Édite `config/fonds.json` en dupliquant le bloc existant :

```json
{
  "ia":   { "nom": "Fonds IA",   "titres": [ ... ] },
  "sante":{ "nom": "Fonds Santé","titres": [ ... ] }
}
```

Les onglets en haut du site apparaissent automatiquement. Les tickers suivent
la convention Yahoo Finance : `AAPL`, `000660.KS` pour SK Hynix, `005930.KS`
pour Samsung, `MC.PA` pour LVMH.

---

## Points à connaître

**SpaceX** est dans la config avec un ticker vide : la valeur s'affiche et
accepte des résumés, mais sans cours. Renseigne le ticker dès que tu l'as.

**Devises.** Les valeurs coréennes cotent en wons, TSMC en dollars via son ADR.
La performance pondérée affichée en haut ne convertit pas les devises — elle
additionne des variations en pourcentage, ce qui reste juste tant que tu ne
regardes pas les montants. Si tu veux une contribution en euros, il faudra
brancher les taux de change.

**Cache.** Les articles téléchargés sont stockés dans `.cache/`. Relancer le
script ne les retélécharge pas. Supprime le dossier pour forcer.

**Coût.** Sur ton volume, tu restes très loin du plafond du tier gratuit
Mistral. Le script attend 3 secondes entre deux appels pour ne pas déclencher
de limite de débit — compte 1 à 2 minutes pour une semaine complète.

**Sites payants.** Les articles derrière un paywall ne seront pas extraits : le
script le signale et passe à la suite. Les Échos, le FT et le WSJ échouent
souvent. Reuters, CNBC, Yahoo Finance et Investing passent bien.

**Changer de modèle.** Toute la dépendance à Mistral tient dans la fonction
`resumer()` de `build.py`. Pour passer à Groq ou à un modèle local, seule
cette fonction est à réécrire.

---

## Mettre le site en ligne (plus tard)

Le site est purement statique : trois fichiers plus `data.js`. Un dépôt GitHub
avec Pages activé suffit à le publier gratuitement. À ce moment-là, on pourra
brancher une action qui régénère tout automatiquement dès que tu pousses un
nouveau fichier de liens.
