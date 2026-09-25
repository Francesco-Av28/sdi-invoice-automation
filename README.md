# SDI Invoice Automation — rule-based booking of Italian e-invoices

A Python engine that reads Italian electronic invoices (FatturaPA XML from the SdI exchange system, including signed `.p7m` files), decides **company, direction, counterparty and ledger accounts** on its own, and writes a ready-to-import file for the accounting software plus an Excel report. Anything uncertain is **never booked**: it is set aside with the reason, for a human to review.

Built and used in production at an Italian tax & payroll advisory firm.

**First live batch (July 2026): 1,985 invoices across 29 companies → 1,508 booked automatically (76%), 477 set aside for review.** About 1,200 invoices per hour, 72% less booking time than manual entry.

## How it decides

```
XML / .p7m  ──►  lettore_xml.py   parse SdI layout, unwrap PKCS#7, unzip nested archives
                       │
                       ▼
               decisore.py        1. company + direction from VAT number (buyer = purchase, seller = sale)
                                  2. account per VAT line, by priority:
                                     keyword rule ► supplier VAT rule ► supplier name rule ► goods category
                                  3. category code resolved on THAT company's chart of accounts
                                  4. safety checks → "doubt" instead of a guess
                       │
                       ▼
               esporta_import.py  import file (header T + VAT-line D rows) + Excel report
```

Always set aside (by design): reverse-charge self-invoices (TD16–TD23), invoices with withholding tax, vehicle purchases (fixed assets), foreign currency, unknown suppliers with no hints, multi-rate invoices decided only by category, invoices whose VAT number does not match the folder they were filed in.

## Try it (synthetic data)

```
pip install -r requirements.txt
python genera_esempi.py     # writes 10 synthetic invoices to esempi/
python test_esempi.py       # 10/10 expected outcomes
python fatture_auto.py      # full run: files in USCITE/
```

Everything in `config/`, `regole/` and `esempi/` is **fictitious** (companies, VAT numbers, suppliers, chart of accounts). No client data is included.

## Configuration

| File | Content |
|---|---|
| `config/clienti.csv` | managed companies: name, VAT, code in the accounting software, rules folder, revenue account |
| `regole/<company>/codici_passive.csv` | learned rules: `parola` (keyword), `fornitore` (supplier VAT), `fornitore_nome` |
| `regole/<company>/piano_conti_costi.csv` | the company's chart of expense accounts |
| `regole/regole_comuni.csv` | rules shared by all companies |

## Stack

Python · `xml.etree` · `asn1crypto` (PKCS#7) · `openpyxl`. Packaged for colleagues as a single `.exe` with PyInstaller.

---

## In italiano

Motore Python che legge le fatture elettroniche XML dello SdI (anche `.p7m` firmati e ZIP annidati), riconosce da solo azienda, verso, controparte e conti di costo/ricavo con una catena di regole (parola chiave → P.IVA fornitore → nome fornitore → categoria merceologica sul piano dei conti dell'azienda) e genera il file di import per il gestionale contabile più un report Excel. I casi incerti non vengono mai registrati: finiscono nei "dubbi" con il motivo. In produzione presso uno studio di consulenza fiscale e del lavoro: **primo lotto reale di 1.985 fatture su 29 aziende, 76% registrate in automatico.** Dati di esempio interamente fittizi.

Author: Francesco Aversano
