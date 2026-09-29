# FATTURE AUTO - motore decisionale di registrazione fatture elettroniche.
#
# Legge le fatture elettroniche XML da una cartella, riconosce da solo
# l'azienda (dalla P.IVA), il verso (attiva/passiva), il fornitore/cliente
# e i conti di costo/ricavo con le regole addestrate, poi genera:
#   - un file di import per azienda (per il gestionale contabile)
#   - un report Excel con le fatture pronte e quelle accantonate (dubbi)
# Le fatture dubbie vengono copiate in USCITE\DUBBI per la registrazione manuale.
#
# Uso:  python fatture_auto.py [cartella_xml]
#       (senza argomenti usa la cartella di config\impostazioni.ini)
import configparser
import os
import shutil
import sys
from datetime import datetime

if getattr(sys, "frozen", False):
    QUI = os.path.dirname(sys.executable)
else:
    QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)

import decisore
import esporta_import
import lettore_xml


def carica_impostazioni():
    ini = configparser.ConfigParser()
    ini.read(os.path.join(QUI, "config", "impostazioni.ini"), encoding="utf-8")
    return ini["FATTURE AUTO"] if ini.has_section("FATTURE AUTO") else {}


def raccogli(cartella_xml, per_nome):
    """Elenca (percorso, cliente_da_cartella, verso_da_cartella).

    Due strutture accettate:
    - cartella piatta piena di XML -> cliente e verso decisi dalla P.IVA/CF;
    - una sottocartella per azienda con dentro
      EMESSE (attive) e RICEVUTE (passive).
    """
    voci = []
    lettore_xml.estrai_zip(cartella_xml)
    for xml in lettore_xml.trova_fatture(cartella_xml):
        voci.append((xml, None, None))
    for nome in sorted(os.listdir(cartella_xml)):
        base = os.path.join(cartella_xml, nome)
        if not os.path.isdir(base) or nome.upper() == "DUBBI":
            continue
        cliente = per_nome.get(decisore._norm(nome))
        for sotto, verso in (("EMESSE", "attiva"), ("RICEVUTE", "passiva")):
            dentro = os.path.join(base, sotto)
            if os.path.isdir(dentro):
                estratti = lettore_xml.estrai_zip(dentro)
                if estratti:
                    print(f"  {nome}\\{sotto}: {estratti} fatture estratte dagli ZIP")
                for xml in lettore_xml.trova_fatture(dentro):
                    voci.append((xml, cliente, verso))
        # XML lasciati nella cartella dell'azienda senza EMESSE/RICEVUTE
        lettore_xml.estrai_zip(base)
        for xml in lettore_xml.trova_fatture(base):
            voci.append((xml, cliente, None))
    return voci


def main():
    imp = carica_impostazioni()
    argomenti = [a for a in sys.argv[1:] if not a.startswith("--")]
    cartella_xml = argomenti[0] if argomenti else (imp.get("cartella_xml", "") or "XML DA REGISTRARE")
    if not os.path.isabs(cartella_xml):
        cartella_xml = os.path.join(QUI, cartella_xml)
    if not cartella_xml or not os.path.isdir(cartella_xml):
        print(f"Cartella XML non trovata: '{cartella_xml}'")
        print("Indicala in config\\impostazioni.ini oppure come argomento.")
        return 1

    uscite = os.path.join(QUI, "USCITE")
    dubbi_dir = os.path.join(uscite, "DUBBI")
    os.makedirs(dubbi_dir, exist_ok=True)

    clienti, per_codice, per_nome = decisore.carica_clienti()
    print(f"Clienti configurati: {len(clienti)} "
          f"({sum(1 for c in clienti if not c.solo_comuni)} con regole proprie)")

    voci = raccogli(cartella_xml, per_nome)
    print(f"Fatture XML trovate in '{cartella_xml}': {len(voci)}")
    if not voci:
        return 0

    pronte = {}       # Cliente -> [(fattura, esito)]
    registrate, dubbi, illeggibili = [], [], []

    for percorso, cliente_cartella, verso_cartella in voci:
        try:
            fattura = lettore_xml.leggi_fattura(percorso)
        except Exception as errore:
            illeggibili.append((os.path.basename(percorso), str(errore)))
            continue

        cliente, verso = decisore.identifica(fattura, per_codice)
        if cliente is None:
            cliente, verso = cliente_cartella, verso_cartella
        elif cliente_cartella and cliente is not cliente_cartella:
            dubbi.append((cliente_cartella, fattura, {"motivi": [
                f"la fattura appartiene a '{cliente.nome}' (P.IVA/CF) ma sta "
                f"nella cartella di '{cliente_cartella.nome}'"]}))
            shutil.copy2(percorso, dubbi_dir)
            continue
        if verso is None and cliente is not None:
            verso = verso_cartella
        if cliente is None or verso is None:
            piva_cess = fattura["cessionario"]["piva"]
            piva_ced = fattura["cedente"]["piva"]
            if cliente is None:
                motivo = (f"azienda non riconosciuta: P.IVA {piva_cess or '?'} "
                          f"(cessionario) / {piva_ced or '?'} (cedente) non in "
                          "clienti.csv e cartella non abbinata")
            else:
                motivo = ("verso non determinabile: mettere il file in EMESSE "
                          "o RICEVUTE (P.IVA dell'azienda assente in clienti.csv)")
            dubbi.append((cliente, fattura, {"motivi": [motivo]}))
            shutil.copy2(percorso, dubbi_dir)
            continue

        esito = decisore.decidi(fattura, cliente, verso)
        if esito["stato"] == "ok":
            pronte.setdefault(cliente, []).append((fattura, esito))
            registrate.append((cliente, fattura, esito))
        else:
            dubbi.append((cliente, fattura, esito))
            shutil.copy2(percorso, dubbi_dir)

    bollo = datetime.now().strftime("%Y%m%d_%H%M")
    for cliente, decisioni in pronte.items():
        # file separati per fatture passive e attive
        passive = [d for d in decisioni
                   if d[1]["causale"] in esporta_import.CAUSALI_PASSIVE]
        attive = [d for d in decisioni
                  if d[1]["causale"] not in esporta_import.CAUSALI_PASSIVE]
        base = (cliente.codice_gestionale or cliente.nome).replace(" ", "_")
        scritti = []
        for verso_file, gruppo in (("PASSIVE", passive), ("ATTIVE", attive)):
            # scritto sempre (senza fatture contiene solo la riga "X", che nessuna
            # regola T/D riconosce): l'import trova sempre entrambi i file.
            nome = f"import_{base}_{verso_file}_{bollo}.csv"
            percorso_v = os.path.join(uscite, nome)
            if gruppo:
                esporta_import.scrivi_import(percorso_v, gruppo)
            else:
                with open(percorso_v, "w", newline="") as fv:
                    fv.write("X\r\n")
            scritti.append(f"{nome} ({len(gruppo)})")
        print(f"  {cliente.nome}: {len(decisioni)} fatture -> "
              + "; ".join(scritti))

    report = os.path.join(uscite, f"report_{bollo}.xlsx")
    esporta_import.scrivi_report(report, registrate, dubbi)

    print()
    print(f"Pronte per l'import : {len(registrate)}")
    print(f"Accantonate (dubbi) : {len(dubbi)}  -> copie in USCITE\\DUBBI")
    for nome, errore in illeggibili:
        print(f"  ILLEGGIBILE {nome}: {errore}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    codice = main()
    if "--pausa" in sys.argv or getattr(sys, "frozen", False):
        input("\nPremi Invio per chiudere...")
    sys.exit(codice)
