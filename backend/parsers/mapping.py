"""
PCG account-prefix mapping for standard French plaquette line items.

Design notes
------------
* Keys are the canonical French labels exactly as they appear on a PCG-format
  bilan / compte de résultat.  The reconciler does a normalised fuzzy-match
  against these keys (see `find_prefixes`).
* Values are lists of CompteNum *prefixes* that contribute to the displayed
  figure.  Contra-accounts (amortissements 28x, dépréciations 29x/39x) are
  included so that summing the FEC net soldes produces the NET balance-sheet
  value directly.
* `SECTION` maps the same keys to their balance-sheet section, used by the
  reconciler to apply the correct sign convention when computing fec_amount.
"""

from __future__ import annotations

import unicodedata
import re

# ---------------------------------------------------------------------------
# Master mapping  (label → PCG prefixes)
# ---------------------------------------------------------------------------

PLAQUETTE_TO_PCG: dict[str, list[str]] = {

    # =========================================================================
    # BILAN ACTIF — immobilisé
    # =========================================================================

    # Incorporelles nettes = brut (20x) - amort (280x) - dépréc (290x)
    "Immobilisations incorporelles nettes": [
        "201", "203", "205", "206", "207", "208",
        "2801", "2803", "2805", "2806", "2807", "2808",
        "2901", "2903", "2905", "2906", "2907", "2908",
    ],

    # Fonds commercial net
    "Fonds commercial": ["207", "2807", "2907"],

    # Corporelles nettes = brut (21x, 22x) - amort (281x, 282x) - dépréc (291x, 292x)
    "Immobilisations corporelles nettes": [
        "211", "212", "213", "214", "215", "218",
        "2811", "2812", "2813", "2814", "2815", "2818",
        "2911", "2912", "2913", "2914", "2915", "2918",
    ],

    "Terrains": ["211", "2811", "2911"],
    "Constructions": ["213", "2813", "2913"],
    "Installations techniques, matériel et outillage industriels": [
        "215", "2815", "2915",
    ],
    "Autres immobilisations corporelles": ["218", "2818", "2918"],
    "Immobilisations corporelles en cours": ["231", "232", "237", "238"],

    # Financières nettes = brut (26x, 27x) - dépréc (296x, 297x)
    "Immobilisations financières nettes": [
        "261", "262", "266", "267", "268",
        "271", "272", "273", "274", "275", "276",
        "2961", "2962", "2966", "2967", "2968",
        "2971", "2972", "2973", "2974", "2975", "2976",
    ],

    "Participations": ["261", "262", "266", "2961", "2962", "2966"],
    "Créances rattachées à des participations": ["267", "2967"],
    "Autres titres immobilisés": ["271", "272", "273", "2971", "2972", "2973"],
    "Prêts": ["274", "2974"],
    "Autres immobilisations financières": ["275", "276", "2975", "2976"],

    # =========================================================================
    # BILAN ACTIF — circulant
    # =========================================================================

    # Stocks nets = brut (3x) - dépréc (39x)
    "Stocks et en-cours": [
        "31", "32", "33", "34", "35", "36", "37",
        "391", "392", "393", "394", "395", "396", "397",
    ],
    "Stocks de matières premières et autres approvisionnements": [
        "31", "32", "391", "392",
    ],
    "En-cours de production de biens": ["33", "393"],
    "En-cours de production de services": ["34", "394"],
    "Stocks de produits finis et intermédiaires": ["35", "36", "395", "396"],
    "Stocks de marchandises": ["37", "397"],

    "Avances et acomptes versés sur commandes": ["409"],

    # Créances clients nettes = brut (41x) - dépréc (491x)
    "Créances clients": ["411", "413", "416", "491"],
    "Créances clients et comptes rattachés": ["411", "413", "416", "418", "491"],

    "Autres créances": [
        "425", "431", "437",
        "444", "445", "446", "447", "448",
        "451", "455", "456", "458",
        "468", "486", "487", "496",
    ],
    "Capital souscrit appelé non versé": ["109", "456"],

    # VMP nettes = brut (50x) - dépréc (590x)
    "Valeurs mobilières de placement": ["50", "506", "590"],
    "Disponibilités": ["512", "514", "515", "516", "517", "531", "532", "533"],
    "Charges constatées d'avance": ["486"],
    "Écart de conversion actif": ["476"],

    # =========================================================================
    # BILAN PASSIF — capitaux propres
    # =========================================================================

    "Capital social ou individuel": ["101", "1011", "1012"],
    "Primes liées au capital social": ["104"],
    "Réserve légale": ["1061"],
    "Réserves statutaires ou contractuelles": ["1062"],
    "Réserves réglementées": ["1063", "1064"],
    "Autres réserves": ["1068"],
    "Réserves": ["106"],
    "Report à nouveau": ["110", "119"],
    "Résultat de l'exercice (bénéfice ou perte)": ["120", "129"],
    "Subventions d'investissement": ["131", "138", "139"],
    "Provisions réglementées": ["14"],

    # =========================================================================
    # BILAN PASSIF — provisions
    # =========================================================================

    "Provisions pour risques": ["151"],
    "Provisions pour charges": ["152", "153", "154", "155", "156", "157", "158"],
    "Provisions pour risques et charges": ["15"],

    # =========================================================================
    # BILAN PASSIF — dettes
    # =========================================================================

    "Emprunts obligataires convertibles": ["163"],
    "Autres emprunts obligataires": ["163"],
    "Emprunts et dettes auprès des établissements de crédit": ["164"],
    "Emprunts et dettes financières divers": ["165", "166", "167", "168"],
    "Avances et acomptes reçus sur commandes en cours": ["419"],
    "Dettes fournisseurs et comptes rattachés": ["401", "403", "404", "405", "408"],
    "Dettes fiscales et sociales": ["42", "43", "44"],
    "Dettes sur immobilisations et comptes rattachés": ["404", "405"],
    "Autres dettes": ["455", "457", "458", "468", "487"],
    "Produits constatés d'avance": ["487"],
    "Écart de conversion passif": ["477"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — produits d'exploitation
    # =========================================================================

    "Chiffre d'affaires net": ["70"],
    "Ventes de marchandises": ["707"],
    "Production vendue de biens": ["701", "702", "703"],
    "Production vendue de services": ["704", "705", "706", "708"],
    "Production stockée": ["71"],
    "Production immobilisée": ["72"],
    "Subventions d'exploitation": ["74"],
    "Reprises sur dépréciations, provisions et amortissements": ["781"],
    "Transferts de charges d'exploitation": ["791"],
    "Autres produits de gestion courante": ["75"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — charges d'exploitation
    # =========================================================================

    "Achats de marchandises": ["607"],
    "Variation de stocks de marchandises": ["6037"],
    "Achats de matières premières et autres approvisionnements": ["601", "602"],
    "Variation de stocks de matières premières et approvisionnements": [
        "6031", "6032", "6033", "6034",
    ],
    "Achats consommés": ["60", "603"],
    "Autres achats et charges externes": ["604", "605", "606", "608", "61", "62"],
    "Impôts, taxes et versements assimilés": ["63"],
    "Salaires et traitements": ["641", "644"],
    "Charges sociales": ["645", "646", "647", "648"],
    "Dotations aux amortissements et aux dépréciations sur immobilisations": [
        "6811", "6812",
    ],
    "Dotations aux dépréciations des actifs circulants": ["6816", "6817"],
    "Dotations aux provisions pour risques et charges": ["6815"],
    "Autres charges de gestion courante": ["65"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — financier
    # =========================================================================

    "Produits financiers de participations": ["761"],
    "Produits des autres valeurs mobilières": ["762", "764"],
    "Intérêts et produits assimilés": ["763", "768"],
    "Reprises sur dépréciations et provisions financières": ["786"],
    "Produits financiers": ["76", "786", "796"],
    "Intérêts et charges assimilées": ["661", "668"],
    "Dotations financières aux amortissements, dépréciations et provisions": [
        "686",
    ],
    "Charges financières": ["66", "686", "696"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — exceptionnel
    # =========================================================================

    "Produits exceptionnels sur opérations de gestion": ["771"],
    "Produits exceptionnels sur opérations en capital": ["775", "777"],
    "Reprises sur dépréciations et provisions exceptionnelles": ["787"],
    "Produits exceptionnels": ["77", "787", "797"],
    "Charges exceptionnelles sur opérations de gestion": ["671"],
    "Charges exceptionnelles sur opérations en capital": ["675"],
    "Dotations exceptionnelles aux amortissements, dépréciations et provisions": [
        "687",
    ],
    "Charges exceptionnelles": ["67", "687", "697"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — résultat
    # =========================================================================

    "Participation des salariés aux résultats de l'entreprise": ["691"],
    "Impôts sur les bénéfices": ["695", "699"],
}


# ---------------------------------------------------------------------------
# Section metadata (used by reconciler for sign convention)
# ---------------------------------------------------------------------------

SECTION: dict[str, str] = {
    # bilan_actif items
    "Immobilisations incorporelles nettes": "bilan_actif",
    "Fonds commercial": "bilan_actif",
    "Immobilisations corporelles nettes": "bilan_actif",
    "Terrains": "bilan_actif",
    "Constructions": "bilan_actif",
    "Installations techniques, matériel et outillage industriels": "bilan_actif",
    "Autres immobilisations corporelles": "bilan_actif",
    "Immobilisations corporelles en cours": "bilan_actif",
    "Immobilisations financières nettes": "bilan_actif",
    "Participations": "bilan_actif",
    "Créances rattachées à des participations": "bilan_actif",
    "Autres titres immobilisés": "bilan_actif",
    "Prêts": "bilan_actif",
    "Autres immobilisations financières": "bilan_actif",
    "Stocks et en-cours": "bilan_actif",
    "Stocks de matières premières et autres approvisionnements": "bilan_actif",
    "En-cours de production de biens": "bilan_actif",
    "En-cours de production de services": "bilan_actif",
    "Stocks de produits finis et intermédiaires": "bilan_actif",
    "Stocks de marchandises": "bilan_actif",
    "Avances et acomptes versés sur commandes": "bilan_actif",
    "Créances clients": "bilan_actif",
    "Créances clients et comptes rattachés": "bilan_actif",
    "Autres créances": "bilan_actif",
    "Capital souscrit appelé non versé": "bilan_actif",
    "Valeurs mobilières de placement": "bilan_actif",
    "Disponibilités": "bilan_actif",
    "Charges constatées d'avance": "bilan_actif",
    "Écart de conversion actif": "bilan_actif",
    # bilan_passif items
    "Capital social ou individuel": "bilan_passif",
    "Primes liées au capital social": "bilan_passif",
    "Réserve légale": "bilan_passif",
    "Réserves statutaires ou contractuelles": "bilan_passif",
    "Réserves réglementées": "bilan_passif",
    "Autres réserves": "bilan_passif",
    "Réserves": "bilan_passif",
    "Report à nouveau": "bilan_passif",
    "Résultat de l'exercice (bénéfice ou perte)": "bilan_passif",
    "Subventions d'investissement": "bilan_passif",
    "Provisions réglementées": "bilan_passif",
    "Provisions pour risques": "bilan_passif",
    "Provisions pour charges": "bilan_passif",
    "Provisions pour risques et charges": "bilan_passif",
    "Emprunts obligataires convertibles": "bilan_passif",
    "Autres emprunts obligataires": "bilan_passif",
    "Emprunts et dettes auprès des établissements de crédit": "bilan_passif",
    "Emprunts et dettes financières divers": "bilan_passif",
    "Avances et acomptes reçus sur commandes en cours": "bilan_passif",
    "Dettes fournisseurs et comptes rattachés": "bilan_passif",
    "Dettes fiscales et sociales": "bilan_passif",
    "Dettes sur immobilisations et comptes rattachés": "bilan_passif",
    "Autres dettes": "bilan_passif",
    "Produits constatés d'avance": "bilan_passif",
    "Écart de conversion passif": "bilan_passif",
    # compte_de_resultat items
    "Chiffre d'affaires net": "compte_de_resultat",
    "Ventes de marchandises": "compte_de_resultat",
    "Production vendue de biens": "compte_de_resultat",
    "Production vendue de services": "compte_de_resultat",
    "Production stockée": "compte_de_resultat",
    "Production immobilisée": "compte_de_resultat",
    "Subventions d'exploitation": "compte_de_resultat",
    "Reprises sur dépréciations, provisions et amortissements": "compte_de_resultat",
    "Transferts de charges d'exploitation": "compte_de_resultat",
    "Autres produits de gestion courante": "compte_de_resultat",
    "Achats de marchandises": "compte_de_resultat",
    "Variation de stocks de marchandises": "compte_de_resultat",
    "Achats de matières premières et autres approvisionnements": "compte_de_resultat",
    "Variation de stocks de matières premières et approvisionnements": "compte_de_resultat",
    "Achats consommés": "compte_de_resultat",
    "Autres achats et charges externes": "compte_de_resultat",
    "Impôts, taxes et versements assimilés": "compte_de_resultat",
    "Salaires et traitements": "compte_de_resultat",
    "Charges sociales": "compte_de_resultat",
    "Dotations aux amortissements et aux dépréciations sur immobilisations": "compte_de_resultat",
    "Dotations aux dépréciations des actifs circulants": "compte_de_resultat",
    "Dotations aux provisions pour risques et charges": "compte_de_resultat",
    "Autres charges de gestion courante": "compte_de_resultat",
    "Produits financiers de participations": "compte_de_resultat",
    "Produits des autres valeurs mobilières": "compte_de_resultat",
    "Intérêts et produits assimilés": "compte_de_resultat",
    "Reprises sur dépréciations et provisions financières": "compte_de_resultat",
    "Produits financiers": "compte_de_resultat",
    "Intérêts et charges assimilées": "compte_de_resultat",
    "Dotations financières aux amortissements, dépréciations et provisions": "compte_de_resultat",
    "Charges financières": "compte_de_resultat",
    "Produits exceptionnels sur opérations de gestion": "compte_de_resultat",
    "Produits exceptionnels sur opérations en capital": "compte_de_resultat",
    "Reprises sur dépréciations et provisions exceptionnelles": "compte_de_resultat",
    "Produits exceptionnels": "compte_de_resultat",
    "Charges exceptionnelles sur opérations de gestion": "compte_de_resultat",
    "Charges exceptionnelles sur opérations en capital": "compte_de_resultat",
    "Dotations exceptionnelles aux amortissements, dépréciations et provisions": "compte_de_resultat",
    "Charges exceptionnelles": "compte_de_resultat",
    "Participation des salariés aux résultats de l'entreprise": "compte_de_resultat",
    "Impôts sur les bénéfices": "compte_de_resultat",
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """
    Normalise for fuzzy comparison: lower-case, strip accents, collapse spaces.

    Also normalises apostrophes and hyphens to spaces so that:
      "Chiffre d'affaires" == "Chiffre d’affaires" == "Chiffre d affaires"
    This handles curly-quote variants that pdfplumber may extract.
    """
    # Normalise Unicode (decompose accents, normalise curly quotes → ASCII)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    # Treat apostrophes and hyphens as word separators
    ascii_only = re.sub(r"['\-]", " ", ascii_only)
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


# Pre-compute normalised key → original key for the default mapping
_NORM_INDEX: dict[str, str] = {_norm(k): k for k in PLAQUETTE_TO_PCG}

# Public alias — this is the symbol imported in the user-facing snippet:
#   from parsers.mapping import MAPPING
MAPPING: dict[str, list[str]] = PLAQUETTE_TO_PCG


def _build_norm_index(mapping: dict[str, list[str]]) -> dict[str, str]:
    """Build a normalised-key → original-key index for any mapping dict."""
    return {_norm(k): k for k in mapping}


def find_prefixes(
    label: str,
    mapping: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Return the list of PCG prefixes for a plaquette label.

    Parameters
    ----------
    label : str
        The label as extracted from the plaquette.
    mapping : dict, optional
        Custom ``{label: [prefix, ...]}`` mapping.  Defaults to
        ``PLAQUETTE_TO_PCG`` (the module-level canonical mapping).

    Matching strategy (in order)
    ----------------------------
    1. Exact match after normalisation.
    2. Canonical key is a substring of the label.
    3. Label is a substring of the canonical key.

    Returns [] if nothing matches.
    """
    m = mapping if mapping is not None else PLAQUETTE_TO_PCG
    idx = _build_norm_index(m) if mapping is not None else _NORM_INDEX
    normed = _norm(label)

    # 1. Exact
    if normed in idx:
        return m[idx[normed]]

    # 2. Canonical key contained in label
    for canon_norm, canon_orig in idx.items():
        if canon_norm in normed:
            return m[canon_orig]

    # 3. Label contained in canonical key
    for canon_norm, canon_orig in idx.items():
        if normed in canon_norm:
            return m[canon_orig]

    return []


def find_section(label: str) -> str | None:
    """Return the section string ('bilan_actif' | 'bilan_passif' | 'compte_de_resultat') for a label."""
    normed = _norm(label)
    if normed in _NORM_INDEX:
        return SECTION.get(_NORM_INDEX[normed])
    for canon_norm, canon_orig in _NORM_INDEX.items():
        if canon_norm in normed or normed in canon_norm:
            return SECTION.get(canon_orig)
    return None
