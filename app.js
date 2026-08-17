(function () {
  "use strict";

  var donnees = window.VEILLE || {};
  var codes = Object.keys(donnees).sort().reverse();

  var elSemaines = document.getElementById("semaines");
  var elOnglets = document.getElementById("onglets");
  var elValeurs = document.getElementById("valeurs");
  var elTitre = document.getElementById("titre-fonds");
  var elDesc = document.getElementById("desc-fonds");
  var elSynthese = document.getElementById("synthese");
  var elGenere = document.getElementById("genere");

  if (codes.length === 0) {
    elValeurs.innerHTML =
      '<div class="valeur"><div class="bloc-texte"><p class="vide">' +
      "Aucune donnee. Lance <code>python build.py</code> apres avoir rempli " +
      "un fichier dans <code>liens/</code>.</p></div></div>";
    return;
  }

  var semaineActive = codes[0];
  var fondsActif = null;

  function classePerf(v) {
    if (v === null || v === undefined) return "neutre";
    return v > 0 ? "hausse" : v < 0 ? "baisse" : "neutre";
  }

  function signe(v, decimales) {
    if (v === null || v === undefined) return "–";
    return (v > 0 ? "+" : "") + v.toFixed(decimales === undefined ? 2 : decimales) + " %";
  }

  function jourMois(iso) {
    var p = iso.split("-");
    return p[2] + "/" + p[1];
  }

  function echapper(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* Courbe des cloures de la semaine, tracee en SVG. */
  function courbe(cours) {
    if (!cours || cours.length < 2) return "";
    var prix = cours.map(function (c) { return c.dernier; });
    var min = Math.min.apply(null, prix);
    var max = Math.max.apply(null, prix);
    var etendue = max - min || 1;
    var L = 260, H = 54, marge = 5;

    var points = prix.map(function (p, i) {
      var x = (i / (prix.length - 1)) * (L - marge * 2) + marge;
      var y = H - marge - ((p - min) / etendue) * (H - marge * 2);
      return x.toFixed(1) + "," + y.toFixed(1);
    });

    var monte = prix[prix.length - 1] >= prix[0];
    var couleur = monte ? "var(--hausse)" : "var(--baisse)";
    var aire = "M" + points[0] + " L" + points.join(" L") +
               " L" + (L - marge) + "," + H + " L" + marge + "," + H + " Z";

    return (
      '<svg class="courbe" viewBox="0 0 ' + L + " " + H + '" preserveAspectRatio="none" ' +
      'role="img" aria-label="Evolution du cours sur la semaine">' +
      '<path d="' + aire + '" fill="' + couleur + '" opacity="0.09"/>' +
      '<polyline points="' + points.join(" ") + '" fill="none" stroke="' + couleur +
      '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + points[points.length - 1].split(",")[0] + '" cy="' +
      points[points.length - 1].split(",")[1] + '" r="2.8" fill="' + couleur + '"/>' +
      "</svg>"
    );
  }

  function tableauCours(v) {
    if (!v.cours || v.cours.length === 0) {
      return '<p class="vide">Cours indisponibles pour cette valeur.</p>';
    }
    var lignes = v.cours.map(function (c) {
      return (
        "<tr><td class=\"date\">" + jourMois(c.date) + "</td>" +
        '<td class="prix">' + c.dernier.toLocaleString("fr-FR") + "</td>" +
        '<td class="var ' + classePerf(c.variation) + '">' + signe(c.variation) + "</td></tr>"
      );
    });
    return courbe(v.cours) + '<table class="cours">' + lignes.join("") + "</table>";
  }

  function fiche(v) {
    var sources = v.sources && v.sources.length
      ? '<div class="sources"><div class="sources-titre">Sources</div>' +
        v.sources.map(function (s) {
          var libelle = s.source ? s.source + " — " + s.titre : s.titre;
          return '<a href="' + echapper(s.url) + '" target="_blank" rel="noopener">' +
                 echapper(libelle) + "</a>";
        }).join("") + "</div>"
      : "";

    var texte = v.resume
      ? "<p>" + echapper(v.resume).replace(/\n+/g, "</p><p>") + "</p>"
      : '<p class="vide">Aucun lien fourni cette semaine pour cette valeur.</p>';

    return (
      '<article class="valeur">' +
      '<div class="valeur-tete">' +
      '<span class="valeur-nom">' + echapper(v.nom) + "</span>" +
      (v.ticker ? '<span class="valeur-ticker">' + echapper(v.ticker) + "</span>" : "") +
      '<span class="valeur-perf ' + classePerf(v.perf) + '">' + signe(v.perf) + "</span>" +
      '<span class="valeur-poids">' + v.poids + " % du fonds</span>" +
      "</div>" +
      '<div class="valeur-corps">' +
      '<div class="bloc-cours">' + tableauCours(v) + "</div>" +
      '<div class="bloc-texte">' + texte + sources + "</div>" +
      "</div></article>"
    );
  }

  function synthese(valeurs) {
    var cotees = valeurs.filter(function (v) { return v.perf !== null && v.perf !== undefined; });
    var poidsTotal = cotees.reduce(function (s, v) { return s + v.poids; }, 0);
    var pondere = poidsTotal
      ? cotees.reduce(function (s, v) { return s + v.perf * v.poids; }, 0) / poidsTotal
      : null;

    var couverts = valeurs.filter(function (v) { return v.resume; }).length;

    var meilleur = null, pire = null;
    cotees.forEach(function (v) {
      if (!meilleur || v.perf > meilleur.perf) meilleur = v;
      if (!pire || v.perf < pire.perf) pire = v;
    });

    function bloc(label, valeur, classe) {
      return '<div><div class="stat-valeur ' + (classe || "") + '">' + valeur +
             '</div><div class="stat-label">' + label + "</div></div>";
    }

    var html = bloc("Performance ponderee",
                    pondere === null ? "–" : signe(pondere),
                    classePerf(pondere));
    if (meilleur) {
      html += bloc("Plus forte hausse",
                   meilleur.nom + " " + signe(meilleur.perf), classePerf(meilleur.perf));
    }
    if (pire && pire !== meilleur) {
      html += bloc("Plus forte baisse",
                   pire.nom + " " + signe(pire.perf), classePerf(pire.perf));
    }
    html += bloc("Valeurs commentees", couverts + " / " + valeurs.length);
    return html;
  }

  function rendre() {
    var semaine = donnees[semaineActive];
    var idsFonds = Object.keys(semaine.fonds);
    if (!fondsActif || idsFonds.indexOf(fondsActif) === -1) fondsActif = idsFonds[0];

    elGenere.textContent = "Genere le " + semaine.genere_le;

    elOnglets.innerHTML = idsFonds.map(function (id) {
      return '<button class="onglet" data-fonds="' + id + '" aria-current="' +
             (id === fondsActif) + '">' + echapper(semaine.fonds[id].nom) + "</button>";
    }).join("");

    var fonds = semaine.fonds[fondsActif];
    elTitre.textContent = fonds.nom;
    elDesc.textContent = fonds.description || "";
    elSynthese.innerHTML = synthese(fonds.valeurs);
    elValeurs.innerHTML = fonds.valeurs.map(fiche).join("");

    document.title = fonds.nom + " — " + semaine.libelle;
  }

  elSemaines.innerHTML = codes.map(function (c) {
    return '<option value="' + c + '">' + echapper(donnees[c].libelle) + "</option>";
  }).join("");

  elSemaines.addEventListener("change", function () {
    semaineActive = this.value;
    rendre();
  });

  elOnglets.addEventListener("click", function (e) {
    var bouton = e.target.closest(".onglet");
    if (!bouton) return;
    fondsActif = bouton.dataset.fonds;
    rendre();
  });

  rendre();
})();
