# Test end-to-end sulle fatture sintetiche: ogni caso deve dare l'esito
# atteso (ok/dubbio) e, quando ok, il conto previsto.
#
# Uso:  python genera_esempi.py && python test_esempi.py
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)

import decisore
import lettore_xml
from genera_esempi import CASI, ESEMPI

CONTI_ATTESI = {
    "01_carburante.xml": "29-15-103",   # categoria carburanti -> piano del cliente
    "02_energia.xml": "29-5-19",        # categoria energia elettrica
    "03_fornitore_noto.xml": "27-5-4",  # regola fornitore per P.IVA
    "04_nota_credito.xml": "27-5-4",
    "05_vendita.xml": "44-5-1",         # fattura attiva -> conto ricavi
    "06_regola_comune.xml": "29-15-60", # parola chiave nelle regole comuni
}


def main():
    _, per_codice, _ = decisore.carica_clienti()
    errori = 0
    for nome, *_, atteso in CASI:
        fattura = lettore_xml.leggi_fattura(os.path.join(ESEMPI, nome))
        cliente, verso = decisore.identifica(fattura, per_codice)
        esito = decisore.decidi(fattura, cliente, verso)
        conti = {r["codice"] for r in esito.get("righe_conto", [])}
        ok = esito["stato"] == atteso and (
            atteso != "ok" or conti == {CONTI_ATTESI[nome]})
        errori += not ok
        dettaglio = ", ".join(sorted(c for c in conti if c)) or "; ".join(esito["motivi"])
        print(f"{'PASS' if ok else 'FAIL'}  {nome:<26} {esito['stato']:<7} {dettaglio}")
    print(f"\n{len(CASI) - errori}/{len(CASI)} casi corretti")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
