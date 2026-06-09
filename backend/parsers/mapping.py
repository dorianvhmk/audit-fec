"""
PCG account-prefix mapping for standard French plaquette line items.

Design notes
------------
* Keys are the canonical French labels exactly as they appear on a PCG-format
  bilan / compte de résultat.  The reconciler does a normalised fuzzy-match
  against these keys (see ``find_prefixes``).
* Values are lists of CompteNum *prefixes*.  For Bilan Actif items the contra-
  accounts (amortissements 28x, dépréciations 29x/39x) are included so that
  summing the FEC net soldes produces the NET balance-sheet value.
* ``SECTION`` maps every label to its balance-sheet section; used by the
  reconciler to apply the correct sign convention.
* The module exposes ``MAPPING`` as the primary import alias for the full dict.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Master mapping  (label → PCG prefixes)
# ---------------------------------------------------------------------------

PLAQUETTE_TO_PCG: dict[str, list[str]] = {

    # =========================================================================
    # BILAN ACTIF — immobilisé incorporel
    # =========================================================================

    "Frais d'établissement": ["201", "2801"],
    "Frais de développement": ["203", "2803"],

    # Short form used in simplified plaquettes
    "Concessions, brevets et droits similaires": ["205", "2805", "2905"],

    "Concessions, brevets, licences, marques, procédés, logiciels, droits et valeurs similaires": [
        "205", "206", "2805", "2806", "2905", "2906",
    ],
    "Fonds commercial": ["207", "2807", "2907"],
    "Autres immobilisations incorporelles": ["208", "2808", "2908"],

    "Immobilisations incorporelles nettes": [
        "201", "203", "205", "206", "207", "208",
        "2801", "2803", "2805", "2806", "2807", "2808",
        "2901", "2903", "2905", "2906", "2907", "2908",
    ],

    # =========================================================================
    # BILAN ACTIF — immobilisé corporel
    # =========================================================================

    "Terrains": ["211", "2811", "2911"],
    "Constructions": ["213", "2813", "2913"],

    # Exact label used in simplified plaquettes (short form)
    "Installations techniques, matériel, outillage": ["2154", "2815", "2915"],

    # Full PCG label
    "Installations techniques, matériel et outillage industriels": [
        "215", "2815", "2915",
    ],

    "Autres immobilisations corporelles": ["218", "2818", "2918"],
    "Immobilisations corporelles en cours": ["231", "232", "237", "238"],
    "Avances et acomptes sur immobilisations corporelles": ["237", "238"],

    "Immobilisations corporelles nettes": [
        "211", "212", "213", "214", "215", "218",
        "2811", "2812", "2813", "2814", "2815", "2818",
        "2911", "2912", "2913", "2914", "2915", "2918",
    ],

    # =========================================================================
    # BILAN ACTIF — immobilisé financier
    # =========================================================================

    # Short form used in simplified plaquettes
    "Participations": ["261", "266", "267", "2961", "2966", "2967"],

    "Créances rattachées à des participations": ["267", "2967"],
    "Autres titres immobilisés": ["271", "272", "273", "2971", "2972", "2973"],
    "Prêts": ["274", "2974"],

    # Short form
    "Autres immobilisations financières": [
        "274", "275", "276", "2974", "2975", "2976",
    ],

    "Immobilisations financières nettes": [
        "261", "262", "266", "267", "268",
        "271", "272", "273", "274", "275", "276",
        "2961", "2962", "2966", "2967", "2968",
        "2971", "2972", "2973", "2974", "2975", "2976",
    ],

    # =========================================================================
    # BILAN ACTIF — circulant / stocks
    # =========================================================================

    "Stocks et en-cours": [
        "31", "32", "33", "34", "35", "36", "37",
        "391", "392", "393", "394", "395", "396", "397",
    ],
    "Stocks de matières premières et autres approvisionnements": [
        "31", "32", "391", "392",
    ],
    "En-cours de production de biens": ["33", "393"],

    # Short form using account 335 (Travaux en cours / services en cours)
    "En-cours de production de services": ["335"],

    "Stocks de produits finis et intermédiaires": ["35", "36", "395", "396"],
    "Stocks de marchandises": ["37", "397"],

    # =========================================================================
    # BILAN ACTIF — circulant / créances
    # =========================================================================

    # Short form: only 4091 (acomptes fournisseurs vs acomptes clients)
    "Avances et acomptes versés sur commandes": ["4091"],

    "Créances clients": ["411", "413", "416", "491"],

    # Exact label as it appears on PCG plaquettes (without 418)
    "Créances clients et comptes rattachés": ["411", "413", "416", "491"],

    "Autres créances": [
        "409",
        "421", "425",
        "431", "437",
        "441", "444", "445", "446", "447", "448",
        "451", "455", "456", "458",
        "468", "486", "487",
    ],

    "Capital souscrit appelé non versé": ["109", "456"],

    # =========================================================================
    # BILAN ACTIF — trésorerie
    # =========================================================================

    "Valeurs mobilières de placement": ["50", "506", "590"],

    # Short form matching simplified plaquettes
    "Disponibilités": ["512", "514", "530", "531", "532", "533"],

    "Charges constatées d'avance": ["486"],
    "Écart de conversion actif": ["476"],

    # =========================================================================
    # BILAN PASSIF — capitaux propres
    # =========================================================================

    # Short form (accounts 101-103)
    "Capital social ou individuel": ["101", "102", "103"],

    "Primes liées au capital social": ["104"],
    "Réserve légale": ["1061"],

    # Some plaquettes label this entry with account 1063
    "Réserves statutaires ou contractuelles": ["1063"],

    "Réserves réglementées": ["1063", "1064"],
    "Autres réserves": ["1068"],
    "Réserves": ["106"],
    "Report à nouveau": ["110", "119"],

    # Short form (no parenthetical)
    "Résultat de l'exercice": ["120", "129"],

    # Full PCG label
    "Résultat de l'exercice (bénéfice ou perte)": ["120", "129"],

    "Subventions d'investissement": ["131", "138", "139"],
    "Provisions réglementées": ["14"],

    # =========================================================================
    # BILAN PASSIF — provisions
    # =========================================================================

    # Explicit sub-accounts (1511–1518)
    "Provisions pour risques": [
        "1511", "1512", "1513", "1514", "1515", "1516", "1518",
    ],

    # Explicit sub-accounts (1521–1528)
    "Provisions pour charges": [
        "1521", "1522", "1523", "1524", "1525", "1526", "1528",
    ],

    "Provisions pour risques et charges": ["15"],

    # =========================================================================
    # BILAN PASSIF — dettes financières
    # =========================================================================

    "Emprunts obligataires convertibles": ["163"],
    "Autres emprunts obligataires": ["163"],

    # Full sub-account list for établissements de crédit
    "Emprunts et dettes auprès des établissements de crédit": [
        "164", "1644", "1645", "1646", "1647", "1648",
    ],

    "Emprunts et dettes financières divers": ["165", "166", "167", "168"],
    "Avances et acomptes reçus sur commandes en cours": ["419"],

    # =========================================================================
    # BILAN PASSIF — dettes d'exploitation et diverses
    # =========================================================================

    "Dettes fournisseurs et comptes rattachés": ["401", "403", "404", "405", "408"],

    # Explicit sub-accounts (comptes 421–448)
    "Dettes fiscales et sociales": [
        "421", "422", "423", "424", "425", "426", "427", "428",
        "431", "432", "433", "437", "438",
        "441", "442", "443", "444", "445", "446", "447", "448",
    ],

    "Dettes sur immobilisations et comptes rattachés": ["404", "405"],

    "Autres dettes": [
        "451", "455", "456", "457", "458",
        "462", "464", "465", "467", "468",
    ],

    "Produits constatés d'avance": ["487"],
    "Écart de conversion passif": ["477"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — produits d'exploitation
    # =========================================================================

    "Chiffre d'affaires net": ["70"],
    "Ventes de marchandises": ["707"],

    # Explicit 4-digit sub-accounts
    "Production vendue de biens": ["7011", "7012", "7013"],

    # Explicit 4-digit sub-accounts
    "Production vendue de services": ["7041", "7042", "7043"],

    # Account 713 (Variation des en-cours de production)
    "Production stockée": ["713"],

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

    # Updated to include 6031/6032 variation de stocks
    "Achats de matières premières et autres approvisionnements": [
        "601", "602", "6031", "6032",
    ],

    "Variation de stocks de matières premières et approvisionnements": [
        "6031", "6032", "6033", "6034",
    ],

    "Achats consommés": ["60", "603"],

    # Added 607 and 609 to match simplified plaquette label
    "Autres achats et charges externes": [
        "604", "605", "606", "607", "608", "609", "61", "62",
    ],

    "Impôts, taxes et versements assimilés": ["63"],

    # Updated: 641, 644, 645, 646
    "Salaires et traitements": ["641", "644", "645", "646"],

    # Short form: account 645 only
    "Charges sociales": ["645"],

    # Dotations aux amortissements — short label used in simplified plaquettes
    "Sur immobilisations : dotations aux amortissements": ["6811", "6812"],

    # Full PCG label
    "Dotations aux amortissements et aux dépréciations sur immobilisations": [
        "6811", "6812",
    ],

    # Short label used in simplified plaquettes
    "Dotations aux provisions": ["6815", "6816"],

    "Dotations aux dépréciations des actifs circulants": ["6816", "6817"],
    "Dotations aux provisions pour risques et charges": ["6815"],

    # Short form
    "Autres charges": ["65"],

    "Autres charges de gestion courante": ["65"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — financier
    # =========================================================================

    # Updated: 761, 762, 763
    "Produits financiers de participations": ["761", "762", "763"],

    "Produits des autres valeurs mobilières": ["762", "764"],

    # New entry: 764–768
    "Autres intérêts et produits assimilés": ["764", "765", "766", "767", "768"],

    "Intérêts et produits assimilés": ["763", "768"],
    "Reprises sur dépréciations et provisions financières": ["786"],
    "Produits financiers": ["76", "786", "796"],

    # Updated: full range 661–668
    "Intérêts et charges assimilées": [
        "661", "662", "663", "664", "665", "666", "667", "668",
    ],

    "Dotations financières aux amortissements, dépréciations et provisions": ["686"],
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
    "Dotations exceptionnelles aux amortissements, dépréciations et provisions": ["687"],
    "Charges exceptionnelles": ["67", "687", "697"],

    # =========================================================================
    # COMPTE DE RÉSULTAT — résultat
    # =========================================================================

    "Participation des salariés aux résultats de l'entreprise": ["691"],

    # Updated: 695, 696, 698
    "Impôts sur les bénéfices": ["695", "696", "698"],
}


# ---------------------------------------------------------------------------
# Section metadata
# ---------------------------------------------------------------------------

SECTION: dict[str, str] = {
    # ── BILAN ACTIF ────────────────────────────────────────────────────────
    "Frais d'établissement":                                            "bilan_actif",
    "Frais de développement":                                           "bilan_actif",
    "Concessions, brevets et droits similaires":                        "bilan_actif",
    "Concessions, brevets, licences, marques, procédés, logiciels, droits et valeurs similaires": "bilan_actif",
    "Fonds commercial":                                                 "bilan_actif",
    "Autres immobilisations incorporelles":                             "bilan_actif",
    "Immobilisations incorporelles nettes":                             "bilan_actif",
    "Terrains":                                                         "bilan_actif",
    "Constructions":                                                    "bilan_actif",
    "Installations techniques, matériel, outillage":                    "bilan_actif",
    "Installations techniques, matériel et outillage industriels":      "bilan_actif",
    "Autres immobilisations corporelles":                               "bilan_actif",
    "Immobilisations corporelles en cours":                             "bilan_actif",
    "Avances et acomptes sur immobilisations corporelles":              "bilan_actif",
    "Immobilisations corporelles nettes":                               "bilan_actif",
    "Participations":                                                   "bilan_actif",
    "Créances rattachées à des participations":                         "bilan_actif",
    "Autres titres immobilisés":                                        "bilan_actif",
    "Prêts":                                                            "bilan_actif",
    "Autres immobilisations financières":                               "bilan_actif",
    "Immobilisations financières nettes":                               "bilan_actif",
    "Stocks et en-cours":                                               "bilan_actif",
    "Stocks de matières premières et autres approvisionnements":        "bilan_actif",
    "En-cours de production de biens":                                  "bilan_actif",
    "En-cours de production de services":                               "bilan_actif",
    "Stocks de produits finis et intermédiaires":                       "bilan_actif",
    "Stocks de marchandises":                                           "bilan_actif",
    "Avances et acomptes versés sur commandes":                         "bilan_actif",
    "Créances clients":                                                 "bilan_actif",
    "Créances clients et comptes rattachés":                            "bilan_actif",
    "Autres créances":                                                  "bilan_actif",
    "Capital souscrit appelé non versé":                                "bilan_actif",
    "Valeurs mobilières de placement":                                  "bilan_actif",
    "Disponibilités":                                                   "bilan_actif",
    "Charges constatées d'avance":                                      "bilan_actif",
    "Écart de conversion actif":                                        "bilan_actif",
    # ── BILAN PASSIF ───────────────────────────────────────────────────────
    "Capital social ou individuel":                                     "bilan_passif",
    "Primes liées au capital social":                                   "bilan_passif",
    "Réserve légale":                                                   "bilan_passif",
    "Réserves statutaires ou contractuelles":                           "bilan_passif",
    "Réserves réglementées":                                            "bilan_passif",
    "Autres réserves":                                                  "bilan_passif",
    "Réserves":                                                         "bilan_passif",
    "Report à nouveau":                                                 "bilan_passif",
    "Résultat de l'exercice":                                           "bilan_passif",
    "Résultat de l'exercice (bénéfice ou perte)":                      "bilan_passif",
    "Subventions d'investissement":                                     "bilan_passif",
    "Provisions réglementées":                                          "bilan_passif",
    "Provisions pour risques":                                          "bilan_passif",
    "Provisions pour charges":                                          "bilan_passif",
    "Provisions pour risques et charges":                               "bilan_passif",
    "Emprunts obligataires convertibles":                               "bilan_passif",
    "Autres emprunts obligataires":                                     "bilan_passif",
    "Emprunts et dettes auprès des établissements de crédit":           "bilan_passif",
    "Emprunts et dettes financières divers":                            "bilan_passif",
    "Avances et acomptes reçus sur commandes en cours":                 "bilan_passif",
    "Dettes fournisseurs et comptes rattachés":                         "bilan_passif",
    "Dettes fiscales et sociales":                                      "bilan_passif",
    "Dettes sur immobilisations et comptes rattachés":                  "bilan_passif",
    "Autres dettes":                                                    "bilan_passif",
    "Produits constatés d'avance":                                      "bilan_passif",
    "Écart de conversion passif":                                       "bilan_passif",
    # ── COMPTE DE RÉSULTAT ─────────────────────────────────────────────────
    "Chiffre d'affaires net":                                           "compte_de_resultat",
    "Ventes de marchandises":                                           "compte_de_resultat",
    "Production vendue de biens":                                       "compte_de_resultat",
    "Production vendue de services":                                    "compte_de_resultat",
    "Production stockée":                                               "compte_de_resultat",
    "Production immobilisée":                                           "compte_de_resultat",
    "Subventions d'exploitation":                                       "compte_de_resultat",
    "Reprises sur dépréciations, provisions et amortissements":         "compte_de_resultat",
    "Transferts de charges d'exploitation":                             "compte_de_resultat",
    "Autres produits de gestion courante":                              "compte_de_resultat",
    "Achats de marchandises":                                           "compte_de_resultat",
    "Variation de stocks de marchandises":                              "compte_de_resultat",
    "Achats de matières premières et autres approvisionnements":        "compte_de_resultat",
    "Variation de stocks de matières premières et approvisionnements":  "compte_de_resultat",
    "Achats consommés":                                                 "compte_de_resultat",
    "Autres achats et charges externes":                                "compte_de_resultat",
    "Impôts, taxes et versements assimilés":                            "compte_de_resultat",
    "Salaires et traitements":                                          "compte_de_resultat",
    "Charges sociales":                                                 "compte_de_resultat",
    "Sur immobilisations : dotations aux amortissements":               "compte_de_resultat",
    "Dotations aux amortissements et aux dépréciations sur immobilisations": "compte_de_resultat",
    "Dotations aux provisions":                                         "compte_de_resultat",
    "Dotations aux dépréciations des actifs circulants":                "compte_de_resultat",
    "Dotations aux provisions pour risques et charges":                 "compte_de_resultat",
    "Autres charges":                                                   "compte_de_resultat",
    "Autres charges de gestion courante":                               "compte_de_resultat",
    "Produits financiers de participations":                            "compte_de_resultat",
    "Produits des autres valeurs mobilières":                           "compte_de_resultat",
    "Autres intérêts et produits assimilés":                            "compte_de_resultat",
    "Intérêts et produits assimilés":                                   "compte_de_resultat",
    "Reprises sur dépréciations et provisions financières":             "compte_de_resultat",
    "Produits financiers":                                              "compte_de_resultat",
    "Intérêts et charges assimilées":                                   "compte_de_resultat",
    "Dotations financières aux amortissements, dépréciations et provisions": "compte_de_resultat",
    "Charges financières":                                              "compte_de_resultat",
    "Produits exceptionnels sur opérations de gestion":                 "compte_de_resultat",
    "Produits exceptionnels sur opérations en capital":                 "compte_de_resultat",
    "Reprises sur dépréciations et provisions exceptionnelles":         "compte_de_resultat",
    "Produits exceptionnels":                                           "compte_de_resultat",
    "Charges exceptionnelles sur opérations de gestion":               "compte_de_resultat",
    "Charges exceptionnelles sur opérations en capital":               "compte_de_resultat",
    "Dotations exceptionnelles aux amortissements, dépréciations et provisions": "compte_de_resultat",
    "Charges exceptionnelles":                                          "compte_de_resultat",
    "Participation des salariés aux résultats de l'entreprise":         "compte_de_resultat",
    "Impôts sur les bénéfices":                                         "compte_de_resultat",
}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """
    Normalise for fuzzy comparison: lower-case, strip accents, collapse spaces.

    Also normalises apostrophes and hyphens to spaces so that curly-quote
    variants extracted by pdfplumber compare equal to the canonical keys.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"['\-]", " ", ascii_only)
    return re.sub(r"\s+", " ", ascii_only).strip().lower()


# Pre-computed index for the default mapping
_NORM_INDEX: dict[str, str] = {_norm(k): k for k in PLAQUETTE_TO_PCG}

# Public alias
MAPPING: dict[str, list[str]] = PLAQUETTE_TO_PCG


def _build_norm_index(mapping: dict[str, list[str]]) -> dict[str, str]:
    return {_norm(k): k for k in mapping}


def find_prefixes(
    label: str,
    mapping: dict[str, list[str]] | None = None,
) -> list[str]:
    """
    Return the PCG prefix list for a plaquette label.

    Matching strategy (in priority order)
    --------------------------------------
    1. Exact match after normalisation.
    2. Canonical key is a substring of the label.
    3. Label is a substring of the canonical key.
    """
    m   = mapping if mapping is not None else PLAQUETTE_TO_PCG
    idx = _build_norm_index(m) if mapping is not None else _NORM_INDEX
    normed = _norm(label)

    if normed in idx:
        return m[idx[normed]]

    for canon_norm, canon_orig in idx.items():
        if canon_norm in normed:
            return m[canon_orig]

    for canon_norm, canon_orig in idx.items():
        if normed in canon_norm:
            return m[canon_orig]

    return []


def find_section(label: str) -> str | None:
    """Return the section for a label ('bilan_actif' | 'bilan_passif' | 'compte_de_resultat')."""
    normed = _norm(label)
    if normed in _NORM_INDEX:
        return SECTION.get(_NORM_INDEX[normed])
    for canon_norm, canon_orig in _NORM_INDEX.items():
        if canon_norm in normed or normed in canon_norm:
            return SECTION.get(canon_orig)
    return None
