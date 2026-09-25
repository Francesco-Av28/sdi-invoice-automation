# Genera fatture elettroniche XML SINTETICHE (tracciato FatturaPA/SdI) in
# esempi\ per provare il motore senza dati reali. Aziende, P.IVA, fornitori e
# importi sono inventati.
#
# Uso:  python genera_esempi.py
import os

QUI = os.path.dirname(os.path.abspath(__file__))
ESEMPI = os.path.join(QUI, "esempi")

ALFA = ("01111111118", "ALFA SRL")        # azienda con regole proprie
BETA = ("02222222226", "BETA SNC")        # azienda con sole regole comuni

MODELLO = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici>
      <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{ced_piva}</IdCodice></IdFiscaleIVA>
      <Anagrafica><Denominazione>{ced_nome}</Denominazione></Anagrafica>
    </DatiAnagrafici></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici>
      <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{cess_piva}</IdCodice></IdFiscaleIVA>
      <Anagrafica><Denominazione>{cess_nome}</Denominazione></Anagrafica>
    </DatiAnagrafici></CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali><DatiGeneraliDocumento>
      <TipoDocumento>{tipo}</TipoDocumento><Divisa>EUR</Divisa>
      <Data>2026-07-15</Data><Numero>{numero}</Numero>{ritenuta}
      <ImportoTotaleDocumento>{totale:.2f}</ImportoTotaleDocumento>
    </DatiGeneraliDocumento></DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>{descrizione}</Descrizione>
        <PrezzoTotale>{imponibile:.2f}</PrezzoTotale><AliquotaIVA>{aliquota:.2f}</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>{aliquota:.2f}</AliquotaIVA>
        <ImponibileImporto>{imponibile:.2f}</ImponibileImporto><Imposta>{imposta:.2f}</Imposta>
        <EsigibilitaIVA>I</EsigibilitaIVA>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>
"""

RITENUTA = ("<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>40.00</ImportoRitenuta>"
            "<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>")

# file, cedente, cessionario, tipo, descrizione, imponibile, esito atteso
CASI = [
    ("01_carburante.xml", ("03333333334", "DISTRIBUTORE ESEMPIO SPA"), ALFA, "TD01",
     "Gasolio autotrazione rifornimento", 100.00, "ok"),
    ("02_energia.xml", ("04444444445", "ENERGIA DEMO SRL"), ALFA, "TD01",
     "Materia energia elettrica kWh e oneri di rete", 250.00, "ok"),
    ("03_fornitore_noto.xml", ("05555555556", "FORNITORE NOTO SRL"), ALFA, "TD01",
     "Articoli vari", 300.00, "ok"),
    ("04_nota_credito.xml", ("05555555556", "FORNITORE NOTO SRL"), ALFA, "TD04",
     "Reso merce", 50.00, "ok"),
    ("05_vendita.xml", ALFA, ("06666666667", "CLIENTE FINALE SRL"), "TD01",
     "Fornitura merce", 1000.00, "ok"),
    ("06_regola_comune.xml", ("07777777778", "CARTOLERIA DEMO"), BETA, "TD01",
     "Cancelleria e toner", 80.00, "ok"),
    ("07_parcella_ritenuta.xml", ("08888888889", "STUDIO PROFESSIONALE DEMO"), ALFA, "TD06",
     "Onorario per consulenza", 200.00, "dubbio"),
    ("08_reverse_charge.xml", ("09999999990", "IMPRESA EDILE DEMO"), ALFA, "TD17",
     "Integrazione reverse charge", 500.00, "dubbio"),
    ("09_sconosciuto.xml", ("01212121212", "DITTA MAI VISTA SRL"), ALFA, "TD01",
     "Prestazione generica", 120.00, "dubbio"),
    ("10_acquisto_auto.xml", ("01313131313", "CONCESSIONARIA DEMO SPA"), ALFA, "TD01",
     "Autovettura nuova telaio ZZZ000 immatricolazione", 18000.00, "dubbio"),
]


def main():
    os.makedirs(ESEMPI, exist_ok=True)
    for i, (nome, ced, cess, tipo, descr, imponibile, _) in enumerate(CASI, 1):
        aliquota = 22.0
        imposta = round(imponibile * aliquota / 100, 2)
        xml = MODELLO.format(
            ced_piva=ced[0], ced_nome=ced[1], cess_piva=cess[0], cess_nome=cess[1],
            tipo=tipo, numero=f"DEMO-{i:03d}", descrizione=descr,
            ritenuta=RITENUTA if "ritenuta" in nome else "",
            imponibile=imponibile, aliquota=aliquota, imposta=imposta,
            totale=imponibile + imposta)
        with open(os.path.join(ESEMPI, nome), "w", encoding="utf-8") as f:
            f.write(xml)
    print(f"{len(CASI)} fatture sintetiche scritte in {ESEMPI}")


if __name__ == "__main__":
    main()
