"""
PCG (Plan Comptable Général) account range mapping.

Maps plaquette line item labels to ranges of CompteNum prefixes,
allowing the reconciliation service to sum FEC balances for the
corresponding accounts and compare with the plaquette figure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PcgRange:
    label: str           # canonical label used in mapping
    prefixes: list[str]  # CompteNum prefixes to sum (e.g. ["211", "212"])
    section: str         # "actif" | "passif" | "resultat"


# ---------------------------------------------------------------------------
# Bilan Actif
# ---------------------------------------------------------------------------
BILAN_ACTIF: list[PcgRange] = [
    PcgRange("Immobilisations incorporelles", ["201", "203", "205", "206", "207", "208"], "actif"),
    PcgRange("Fonds commercial", ["207"], "actif"),
    PcgRange("Immobilisations corporelles", ["211", "212", "213", "214", "215", "218"], "actif"),
    PcgRange("Terrains", ["211"], "actif"),
    PcgRange("Constructions", ["213"], "actif"),
    PcgRange("Installations techniques, matériel et outillage", ["215"], "actif"),
    PcgRange("Autres immobilisations corporelles", ["218"], "actif"),
    PcgRange("Immobilisations en cours", ["231", "232", "237", "238"], "actif"),
    PcgRange("Immobilisations financières", ["261", "262", "266", "267", "268", "271", "272", "273", "274", "275", "276"], "actif"),
    PcgRange("Participations", ["261", "266"], "actif"),
    PcgRange("Créances rattachées à des participations", ["267"], "actif"),
    PcgRange("Autres titres immobilisés", ["271", "272", "273", "274"], "actif"),
    PcgRange("Prêts", ["274"], "actif"),
    PcgRange("Autres immobilisations financières", ["275", "276"], "actif"),
    PcgRange("Stocks et en-cours", ["31", "32", "33", "34", "35", "36", "37"], "actif"),
    PcgRange("Stocks de marchandises", ["37"], "actif"),
    PcgRange("Avances et acomptes versés sur commandes", ["409"], "actif"),
    PcgRange("Créances clients et comptes rattachés", ["411", "413", "416", "418"], "actif"),
    PcgRange("Autres créances", ["425", "431", "437", "444", "445", "446", "447", "448", "451", "455", "456", "458", "468", "486", "487"], "actif"),
    PcgRange("Capital souscrit appelé non versé", ["109", "456"], "actif"),
    PcgRange("Valeurs mobilières de placement", ["50", "506"], "actif"),
    PcgRange("Disponibilités", ["512", "514", "515", "516", "517", "518", "519", "53"], "actif"),
    PcgRange("Charges constatées d'avance", ["486"], "actif"),
]

# ---------------------------------------------------------------------------
# Bilan Passif
# ---------------------------------------------------------------------------
BILAN_PASSIF: list[PcgRange] = [
    PcgRange("Capital social", ["101"], "passif"),
    PcgRange("Primes d'émission, de fusion, d'apport", ["104"], "passif"),
    PcgRange("Réserve légale", ["1061"], "passif"),
    PcgRange("Réserves réglementées", ["1062", "1063", "1064"], "passif"),
    PcgRange("Autres réserves", ["106"], "passif"),
    PcgRange("Report à nouveau", ["110", "119"], "passif"),
    PcgRange("Résultat de l'exercice", ["120", "129"], "passif"),
    PcgRange("Subventions d'investissement", ["131", "138", "139"], "passif"),
    PcgRange("Provisions réglementées", ["14"], "passif"),
    PcgRange("Provisions pour risques", ["151"], "passif"),
    PcgRange("Provisions pour charges", ["152", "153", "154", "155", "156", "157", "158"], "passif"),
    PcgRange("Emprunts obligataires", ["163"], "passif"),
    PcgRange("Emprunts et dettes auprès des établissements de crédit", ["164"], "passif"),
    PcgRange("Emprunts et dettes financières divers", ["165", "166", "167", "168"], "passif"),
    PcgRange("Avances et acomptes reçus sur commandes en cours", ["419"], "passif"),
    PcgRange("Dettes fournisseurs et comptes rattachés", ["401", "403", "408"], "passif"),
    PcgRange("Dettes fiscales et sociales", ["42", "43", "44"], "passif"),
    PcgRange("Dettes sur immobilisations et comptes rattachés", ["404", "405"], "passif"),
    PcgRange("Autres dettes", ["455", "456", "457", "458", "468", "487"], "passif"),
    PcgRange("Produits constatés d'avance", ["487"], "passif"),
]

# ---------------------------------------------------------------------------
# Compte de résultat
# ---------------------------------------------------------------------------
COMPTE_RESULTAT: list[PcgRange] = [
    PcgRange("Ventes de marchandises", ["707"], "resultat"),
    PcgRange("Production vendue biens", ["701", "702", "703"], "resultat"),
    PcgRange("Production vendue services", ["704", "705", "706", "708"], "resultat"),
    PcgRange("Chiffre d'affaires net", ["70"], "resultat"),
    PcgRange("Production stockée", ["71"], "resultat"),
    PcgRange("Production immobilisée", ["72"], "resultat"),
    PcgRange("Subventions d'exploitation", ["74"], "resultat"),
    PcgRange("Reprises sur amortissements et provisions", ["781"], "resultat"),
    PcgRange("Transferts de charges d'exploitation", ["791"], "resultat"),
    PcgRange("Autres produits", ["75", "791"], "resultat"),
    PcgRange("Achats de marchandises", ["607"], "resultat"),
    PcgRange("Variation de stocks de marchandises", ["6037"], "resultat"),
    PcgRange("Achats de matières premières", ["601", "602"], "resultat"),
    PcgRange("Variation de stocks de matières", ["6031", "6032"], "resultat"),
    PcgRange("Autres achats et charges externes", ["604", "605", "606", "608", "61", "62"], "resultat"),
    PcgRange("Impôts, taxes et versements assimilés", ["63"], "resultat"),
    PcgRange("Salaires et traitements", ["641", "644"], "resultat"),
    PcgRange("Charges sociales", ["645", "646", "647", "648"], "resultat"),
    PcgRange("Dotations aux amortissements sur immobilisations", ["6811", "6812"], "resultat"),
    PcgRange("Dotations aux provisions", ["6815", "6816"], "resultat"),
    PcgRange("Autres charges", ["65"], "resultat"),
    PcgRange("Produits financiers", ["76", "786", "796"], "resultat"),
    PcgRange("Charges financières", ["66", "686", "696"], "resultat"),
    PcgRange("Produits exceptionnels", ["77", "787", "797"], "resultat"),
    PcgRange("Charges exceptionnelles", ["67", "687", "697"], "resultat"),
    PcgRange("Impôts sur les bénéfices", ["695", "699"], "resultat"),
]

ALL_RANGES: list[PcgRange] = BILAN_ACTIF + BILAN_PASSIF + COMPTE_RESULTAT

# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def find_ranges_for_label(label: str, section: str | None = None) -> list[PcgRange]:
    """
    Fuzzy-match a plaquette label against known PCG range labels.
    Returns all ranges whose canonical label is a substring of the
    plaquette label (case-insensitive), optionally filtered by section.
    """
    label_lower = label.lower()
    candidates = [r for r in ALL_RANGES if r.label.lower() in label_lower or label_lower in r.label.lower()]
    if section:
        candidates = [r for r in candidates if r.section == section]
    return candidates


def prefixes_for_label(label: str, section: str | None = None) -> list[str]:
    """Return deduplicated list of CompteNum prefixes for a given label."""
    seen: set[str] = set()
    result: list[str] = []
    for r in find_ranges_for_label(label, section):
        for p in r.prefixes:
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result
