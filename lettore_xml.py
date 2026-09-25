# Lettore di fatture elettroniche XML (tracciato SdI, anche .p7m firmati).
# Estrae tutto quello che serve al motore decisionale: cedente, cessionario,
# tipo documento, righe, riepiloghi IVA, ritenute.
import os
import re
import xml.etree.ElementTree as ET


def _senza_namespace(root):
    """Toglie i namespace da tutti i tag (i tracciati SdI ne usano di diversi)."""
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _estrai_xml_da_p7m(dati):
    """Un .p7m e' una busta PKCS#7 (DER o base64) con dentro l'XML.
    Prima si spacchetta la busta per davvero (ASN.1); se non riesce si
    ripiega sul ritaglio testuale."""
    if b"<?xml" not in dati and b"FatturaElettronica" not in dati:
        # forse e' base64: prova a decodificare
        import base64
        try:
            compatto = re.sub(rb"\s+", b"", dati)
            dati = base64.b64decode(compatto, validate=False)
        except Exception:
            pass
    try:
        from asn1crypto import cms
        busta = cms.ContentInfo.load(dati)
        contenuto = busta["content"]["encap_content_info"]["content"].native
        if contenuto and b"FatturaElettronica" in contenuto:
            return contenuto
    except Exception:
        pass
    inizio = dati.find(b"<?xml")
    if inizio < 0:
        m = re.search(rb"<[\w:]*FatturaElettronica[\s>]", dati)
        if not m:
            raise ValueError("XML non trovato dentro il p7m")
        inizio = m.start()
    m = re.search(rb"</[\w:]*FatturaElettronica\s*>", dati)
    if not m:
        raise ValueError("chiusura FatturaElettronica non trovata nel p7m")
    return dati[inizio:m.end()]


def _testo(nodo, percorso, predef=""):
    el = nodo.find(percorso)
    return (el.text or "").strip() if el is not None and el.text else predef


def _numero(nodo, percorso, predef=0.0):
    t = _testo(nodo, percorso, "")
    if not t:
        return predef
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return predef


def _anagrafica(nodo):
    """DatiAnagrafici + Sede di CedentePrestatore/CessionarioCommittente."""
    if nodo is None:
        return {"piva": "", "codfis": "", "nome": ""}
    piva = _testo(nodo, ".//IdFiscaleIVA/IdCodice")
    codfis = _testo(nodo, ".//CodiceFiscale")
    nome = _testo(nodo, ".//Anagrafica/Denominazione")
    if not nome:
        nome = (_testo(nodo, ".//Anagrafica/Cognome") + " "
                + _testo(nodo, ".//Anagrafica/Nome")).strip()
    return {"piva": piva, "codfis": codfis, "nome": nome}


def leggi_fattura(percorso):
    """Ritorna un dict con tutti i dati utili della fattura.

    Chiavi: file, tipo_doc, data, numero, cedente, cessionario, totale,
    righe=[{descrizione, importo, aliquota, natura}], riepiloghi=[{aliquota,
    natura, imponibile, imposta, esigibilita}], ritenuta={...}|None,
    testo (tutte le descrizioni concatenate, per le regole parola/categoria).
    """
    with open(percorso, "rb") as f:
        dati = f.read()
    if percorso.lower().endswith(".p7m") or b"<?xml" not in dati[:200]:
        try:
            dati = _estrai_xml_da_p7m(dati)
        except ValueError:
            pass  # magari e' un XML normale senza dichiarazione
    root = _senza_namespace(ET.fromstring(dati))

    corpo = root.find(".//FatturaElettronicaBody")
    if corpo is None:
        raise ValueError("FatturaElettronicaBody assente: non e' una fattura SdI")
    dati_gen = corpo.find(".//DatiGeneraliDocumento")

    fattura = {
        "file": os.path.basename(percorso),
        "tipo_doc": _testo(dati_gen, "TipoDocumento"),
        "divisa": _testo(dati_gen, "Divisa", "EUR"),
        "data": _testo(dati_gen, "Data"),
        "numero": _testo(dati_gen, "Numero"),
        "totale": _numero(dati_gen, "ImportoTotaleDocumento"),
        "cedente": _anagrafica(root.find(".//CedentePrestatore")),
        "cessionario": _anagrafica(root.find(".//CessionarioCommittente")),
        "righe": [],
        "riepiloghi": [],
        "ritenuta": None,
        "cassa_previdenziale": _numero(corpo, ".//DatiCassaPrevidenziale/ImportoContributoCassa"),
        "bollo": _numero(corpo, ".//DatiBollo/ImportoBollo"),
    }

    rit = dati_gen.find("DatiRitenuta") if dati_gen is not None else None
    if rit is not None:
        fattura["ritenuta"] = {
            "tipo": _testo(rit, "TipoRitenuta"),
            "importo": _numero(rit, "ImportoRitenuta"),
            "aliquota": _numero(rit, "AliquotaRitenuta"),
            "causale": _testo(rit, "CausalePagamento"),
        }

    for linea in corpo.findall(".//DettaglioLinee"):
        fattura["righe"].append({
            "descrizione": _testo(linea, "Descrizione"),
            "importo": _numero(linea, "PrezzoTotale"),
            "aliquota": _numero(linea, "AliquotaIVA"),
            "natura": _testo(linea, "Natura"),
        })

    for riep in corpo.findall(".//DatiRiepilogo"):
        fattura["riepiloghi"].append({
            "aliquota": _numero(riep, "AliquotaIVA"),
            "natura": _testo(riep, "Natura"),
            "imponibile": _numero(riep, "ImponibileImporto"),
            "imposta": _numero(riep, "Imposta"),
            "esigibilita": _testo(riep, "EsigibilitaIVA", "I"),
        })

    fattura["testo"] = " ".join(r["descrizione"] for r in fattura["righe"])
    return fattura


def trova_fatture(cartella):
    """Tutti gli XML/P7M di fattura nella cartella (non ricorsivo),
    esclusi i metadati SdI (_metaDato / MT_)."""
    trovati = []
    for nome in sorted(os.listdir(cartella)):
        basso = nome.lower()
        if not (basso.endswith(".xml") or basso.endswith(".p7m")):
            continue
        if "metadato" in basso or basso.startswith("mt_"):
            continue
        trovati.append(os.path.join(cartella, nome))
    return trovati


def estrai_zip(cartella):
    """Tira fuori le fatture (.xml/.p7m) dagli ZIP presenti nella cartella,
    anche da zip annidati (i download massivi AdE/portali sono cosi').
    L'estrazione e' nella cartella stessa; i file gia' estratti si saltano.
    Ritorna il numero di file nuovi."""
    import zipfile
    nuovi = 0
    for nome in sorted(os.listdir(cartella)):
        if not nome.lower().endswith(".zip"):
            continue
        try:
            with zipfile.ZipFile(os.path.join(cartella, nome)) as zf:
                nuovi += _estrai_da_zip(zf, cartella)
        except zipfile.BadZipFile:
            continue
    return nuovi


def _estrai_da_zip(zf, destinazione, livello=0):
    import io
    import zipfile
    n = 0
    for info in zf.infolist():
        basso = info.filename.lower()
        base = os.path.basename(info.filename)
        if basso.endswith(".zip") and livello < 3:
            with zf.open(info) as f:
                dentro = io.BytesIO(f.read())
            try:
                with zipfile.ZipFile(dentro) as zf2:
                    n += _estrai_da_zip(zf2, destinazione, livello + 1)
            except zipfile.BadZipFile:
                pass
        elif base and (basso.endswith(".xml") or basso.endswith(".p7m")):
            if "metadato" in basso or base.lower().startswith("mt_"):
                continue
            dest = os.path.join(destinazione, base)
            if not os.path.exists(dest):
                with zf.open(info) as f, open(dest, "wb") as out:
                    out.write(f.read())
                n += 1
    return n
