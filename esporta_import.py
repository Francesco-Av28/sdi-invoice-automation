# Genera i file per l'acquisizione esterna del gestionale contabile
# (import da file di testo delimitato) e il report dei casi accantonati.
#
# Formato file di import: testo con delimitatore ';', righe T (testata) e
# D (dettaglio per aliquota). Il layout delle colonne e' documentato qui
# sotto e va rispecchiato UNA VOLTA nella "specifica di acquisizione"
# creata nel gestionale: da li' in poi l'import e' un click.
#
# Layout riga T (fatture passive e attive):
#   T;tipo_doc;data_documento;numero_documento;data_registrazione;causale;
#     piva_controparte;codice_fiscale;denominazione;totale_documento
# Layout riga D (una per aliquota/natura):
#   D;codice_iva;imponibile;imposta;gruppo;conto;sottoconto;descrizione_conto
#
# Date gg/mm/aaaa, importi con la virgola decimale (formato italiano).
import csv
import os
from datetime import datetime


def _data_it(iso):
    """2026-07-22 -> 22/07/2026 (se gia' italiana la lascia stare)."""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _imp(n):
    return f"{n:.2f}".replace(".", ",")


def _codice_iva(riga):
    """Codice IVA 'parlante' nel file: aliquota intera o natura (N1, N2.2...).
    L'associazione con i codici IVA del gestionale si fa una volta nel wizard."""
    if riga["natura"]:
        return riga["natura"]
    a = riga["aliquota"]
    return f"{a:g}"


# Causali che identificano una fattura passiva: la specifica di import
# (tipologia "Fatture passive") accetta solo queste; le altre vanno nel
# file ATTIVE (tipologia "Fatture attive", da parametrizzare a parte).
CAUSALI_PASSIVE = ("FATTURA ACQUISTI", "NOTA CREDITO FORNITORE", "SPLIT PAYMENT")


def scrivi_import(percorso, decisioni):
    """decisioni: lista di (fattura, esito) tutte con stato 'ok'.
    Scrive/azzera il file di import per una singola azienda."""
    oggi = datetime.now().strftime("%d/%m/%Y")
    with open(percorso, "w", encoding="cp1252", errors="replace", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        for fattura, esito in decisioni:
            contro = (fattura["cedente"]
                      if esito["causale"] in CAUSALI_PASSIVE
                      else fattura["cessionario"])
            w.writerow([
                "T", fattura["tipo_doc"], _data_it(fattura["data"]),
                fattura["numero"], oggi, esito["causale"],
                contro["piva"], contro["codfis"], contro["nome"],
                _imp(fattura["totale"]),
            ])
            for r in esito["righe_conto"]:
                w.writerow([
                    "D", _codice_iva(r), _imp(r["imponibile"]), _imp(r["imposta"]),
                    r["gruppo"], r["conto"], r["sottoconto"], r["origine"],
                ])
    return percorso


def scrivi_report(percorso, registrate, dubbi):
    """Report Excel: foglio Registrate + foglio Dubbi (da fare a mano).
    Formato italiano."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    grassetto = Font(bold=True)

    ws = wb.active
    ws.title = "Pronte per import"
    ws.append(["Azienda", "File XML", "Tipo", "Data", "Numero", "Fornitore-Cliente",
               "Totale", "Causale", "Conti (per aliquota)", "Origine decisione"])
    for c in ws[1]:
        c.font = grassetto
    for cliente, fattura, esito in registrate:
        contro = fattura["cedente"] if "ACQUIST" in esito["causale"] or "FORNITORE" in esito["causale"] else fattura["cessionario"]
        ws.append([
            cliente.nome, fattura["file"], fattura["tipo_doc"],
            _data_it(fattura["data"]), fattura["numero"], contro["nome"],
            fattura["totale"], esito["causale"],
            " | ".join(f"{r['aliquota']:g}%->{r['codice']}" for r in esito["righe_conto"]),
            " | ".join(r["origine"] or "" for r in esito["righe_conto"]),
        ])

    ws2 = wb.create_sheet("Dubbi - da fare a mano")
    ws2.append(["Azienda", "File XML", "Tipo", "Data", "Numero", "Fornitore-Cliente",
                "Totale", "Perche' accantonata"])
    for c in ws2[1]:
        c.font = grassetto
    for cliente, fattura, esito in dubbi:
        contro = fattura["cedente"]
        ws2.append([
            cliente.nome if cliente else "?", fattura["file"], fattura["tipo_doc"],
            _data_it(fattura["data"]), fattura["numero"], contro["nome"],
            fattura["totale"], "; ".join(esito["motivi"]),
        ])

    for foglio in (ws, ws2):
        for col in foglio.columns:
            larghezza = max(len(str(c.value or "")) for c in col)
            foglio.column_dimensions[col[0].column_letter].width = min(larghezza + 2, 60)
    wb.save(percorso)
    return percorso
