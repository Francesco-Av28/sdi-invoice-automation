# Motore decisionale: dato il contenuto di una fattura XML decide azienda,
# causale e conti di costo/ricavo usando le regole addestrate nella
# cartella regole\ (CSV per azienda + regole comuni).
import csv
import os
import re
import sys

# dentro il .exe PyInstaller __file__ punta alla cartella temporanea di
# estrazione: la base giusta e' la cartella del .exe stesso
if getattr(sys, "frozen", False):
    QUI = os.path.dirname(sys.executable)
else:
    QUI = os.path.dirname(os.path.abspath(__file__))
REGOLE_DIR = os.path.join(QUI, "regole")
CONFIG_DIR = os.path.join(QUI, "config")

# Categorie merceologiche, costruite sulle descrizioni reali delle fatture.
# Ogni categoria: (nome, codice_predefinito, parole_indizio, pattern_piano).
# Il codice effettivo si risolve PER CLIENTE cercando pattern_piano nelle
# descrizioni del suo piano_conti_costi.csv; se non c'e', vale il
# predefinito (solo se presente nel piano del cliente o se il piano manca).
CATEGORIE = [
    ("carburanti", "29-15-103", [
        "carburante", "diesel", "gasolio", "benzina", "senza pb", "super sp",
        "ad blue", "adblue", "rifornimento", "lubrificant",
        "distributore carburanti", "autotrazione",
    ], "carbur"),
    ("alimentari", "27-5-4", [
        "alimentar", "farina", "pasta", "olio", "latte", "latticin", "formagg",
        "mozzarell", "salum", "carne", "pesce", "zuccher", "lievito", "uova",
        "bevand", "acqua mineral", "vino", "birra", "caff", "dolciar", "biscott",
        "cioccolat", "panific", "surgelat", "gelat", "frutta", "verdur",
        "ortofrutt", "conserv", "pomodor", "salsa", "aceto", "spezie",
        "prosciutt", "wurstel", "tonno", "margarin", "burro", "panna", "yogurt",
        "gastronom", "drogheria", "semi di girasole", "merend", "snack", "patatin",
    ], "merci"),
    ("energia elettrica", "29-5-19", [
        "energia elettrica", "kwh", "potenza impegnata", "dispacciamento",
        "materia energia", "perequativ", "oneri di rete", "quota energia",
        "consumi rilevati", "pod it",
    ], "energia"),
    ("utenze acqua/gas", "29-5-13", [
        "servizio idrico", "acquedotto", "depurazione", "fognatura",
        "gas naturale", "metano", "smc",
    ], "acqua"),
    ("telefonia/internet", "29-15-75", [
        "telefonia", "telefonic", "fibra", "internet", "canone adsl", "ricarica sim",
    ], "utenz"),
    ("pedaggi", "29-15-30", [
        "pedaggi", "telepass", "autostrad",
    ], "pedagg"),
    ("vigilanza/allarme", "29-15-101", [
        "vigilanza", "antifurto", "allarme", "teleassistenza",
    ], "vigilanza"),
    ("assicurazioni", "29-15-7", [
        "polizza", "premio assicur", "assicurazion",
    ], "assicura"),
    ("servizi telematici/camerali", "29-15-53", [
        "telemaco", "diritti camerali", "visura", "firma digitale",
        "identita digitale", "identità digitale", "casella pec",
        "conservazione digitale", "dominio", "hosting", "spid",
    ], "amministr"),
    ("commissioni/pos", None, [
        "canone pos", "commission", "merchant", "transazioni pos",
    ], "servizi vari"),
    ("noleggio", None, [
        "canone di noleggio", "noleggio a lungo termine", "canoni di noleggio",
    ], "nolegg"),
    ("leasing", "31-5-9", [
        "canone leasing", "canoni leasing", "leasing",
    ], "leasing"),
    ("provvigioni", None, [
        "provvigioni",
    ], "provvigion"),
    ("consulenze", None, [
        "consulenza", "consulenze",
    ], "consulenz"),
    ("spedizioni", None, [
        "spedizione", "corriere espresso", "costi di spedizione",
    ], "trasporto"),
    ("manutenzioni/lavori", None, [
        "manutenzione", "riparazione", "posa in opera", "ristrutturazione",
        "lavori di",
    ], "manut"),
    ("materiale edile/ferramenta", "27-5-4", [
        "cemento", "malta", "rasante", "premiscelato", "piastrell", "sabbione",
        "ferramenta", "guarnizione", "flessibile acciaio", "punta sds",
        "cartongesso", "intonac", "calcestruzzo",
    ], "merci"),
    ("materiale odontoiatrico", "27-5-4", [
        "dental", "implant", "zirconia", "moncone", "endodonzia",
        "mascherine chirurgiche", "ortodonz", "protesi",
    ], "merci"),
    # veicoli: gestione dedicata in classifica_riga (acquisto vs autocarro)
    ("veicoli", None, [
        "autovettur", "autocarr", "targa", "tg:", "telaio", "veicol", "furgon",
        "rimorchi", "motocicl", "trasferimento di propriet", "immatricolaz",
    ], None),
]

# tipi documento SdI che il motore gestisce in autonomia
TIPI_GESTITI = {"TD01", "TD02", "TD03", "TD24", "TD25", "TD04", "TD05", "TD26"}
TIPI_NOTA_CREDITO = {"TD04", "TD08"}
# autofatture / reverse charge: sempre accantonate (procedura a 3 fasi manuale)
TIPI_REVERSE = {"TD16", "TD17", "TD18", "TD19", "TD20", "TD21", "TD22", "TD23"}


def _norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


class Cliente:
    """Un'azienda gestita: righe di config\\clienti.csv."""

    def __init__(self, riga):
        self.nome = riga["nome"].strip()
        self.piva = riga["piva"].strip()
        self.cf = (riga.get("cf") or "").strip().upper()
        self.codice_gestionale = riga["codice_gestionale"].strip()
        self.sede = riga["sede"].strip().lower() or "locale"
        self.cartella_regole = riga["cartella_regole"].strip()
        self.conto_ricavi = riga["conto_ricavi"].strip() or "44-5-1"
        self.regole = None       # caricate pigramente
        self.piano = None
        self.categorie = None

    @property
    def solo_comuni(self):
        return self.cartella_regole.lower() in ("", "comuni")

    def carica(self):
        if self.regole is not None:
            return
        self.regole = {"parola": [], "fornitore": {}, "fornitore_nome": []}
        self.piano = {}          # codice -> descrizione
        if not self.solo_comuni:
            cartella = os.path.join(REGOLE_DIR, self.cartella_regole)
            self._leggi_regole(os.path.join(cartella, "codici_passive.csv"))
            p = os.path.join(cartella, "piano_conti_costi.csv")
            if os.path.exists(p):
                with open(p, encoding="utf-8-sig", newline="") as f:
                    for r in csv.reader(f, delimiter=";"):
                        if r and not r[0].startswith("#"):
                            self.piano[r[0].strip()] = (
                                r[1].strip().lower() if len(r) > 1 else "")
        self._leggi_regole(os.path.join(REGOLE_DIR, "regole_comuni.csv"))
        # risolve il codice di ogni categoria sul piano del cliente:
        # prima per descrizione (pattern_piano), poi col predefinito
        self.categorie = []
        for nome, codice, chiavi, pattern in CATEGORIE:
            self.categorie.append(
                (nome, self.codice_dal_piano(pattern, codice), chiavi))

    def codice_dal_piano(self, pattern, predefinito=None):
        """Codice del piano del cliente la cui descrizione contiene pattern;
        altrimenti il predefinito (se compare nel piano o se il piano manca)."""
        if pattern and self.piano:
            for codice, descr in self.piano.items():
                if pattern in descr:
                    return codice
        if predefinito and self.piano and predefinito not in self.piano:
            return None
        return predefinito

    def _leggi_regole(self, percorso):
        if not os.path.exists(percorso):
            return
        gia = {c for c, _, _ in self.regole["fornitore_nome"]}
        with open(percorso, encoding="utf-8-sig", newline="") as f:
            for r in csv.reader(f, delimiter=";"):
                if len(r) < 3 or r[0].startswith("#"):
                    continue
                tipo, chiave, codice = r[0].strip(), r[1].strip(), r[2].strip()
                if tipo == "parola":
                    self.regole["parola"].append((chiave.lower(), codice))
                elif tipo == "fornitore":
                    self.regole["fornitore"].setdefault(chiave, codice)
                elif tipo == "fornitore_nome" and _norm(chiave) not in gia:
                    self.regole["fornitore_nome"].append((_norm(chiave), chiave, codice))
                    gia.add(_norm(chiave))


def carica_clienti():
    """config\\clienti.csv -> lista + indici per P.IVA/CF e per nome."""
    percorso = os.path.join(CONFIG_DIR, "clienti.csv")
    clienti, per_codice, per_nome = [], {}, {}
    with open(percorso, encoding="utf-8-sig", newline="") as f:
        for riga in csv.DictReader(f, delimiter=";"):
            if not riga.get("nome") or riga["nome"].startswith("#"):
                continue
            c = Cliente(riga)
            clienti.append(c)
            if c.piva:
                per_codice[c.piva] = c
            if c.cf:
                per_codice[c.cf] = c
            per_nome[_norm(c.nome)] = c
    return clienti, per_codice, per_nome


def identifica(fattura, per_codice):
    """Riconosce cliente e verso dalla P.IVA/CF nell'XML.
    Ritorna (cliente, 'passiva'|'attiva') o (None, None)."""
    cess, ced = fattura["cessionario"], fattura["cedente"]
    for codice in (cess["piva"], cess["codfis"].upper()):
        if codice and codice in per_codice:
            return per_codice[codice], "passiva"
    for codice in (ced["piva"], ced["codfis"].upper()):
        if codice and codice in per_codice:
            return per_codice[codice], "attiva"
    return None, None


def classifica_riga(testo, piva_fornitore, nome_fornitore, cliente):
    """Catena di priorita':
    parola chiave > fornitore per P.IVA > fornitore per nome > categoria.
    Ritorna (codice, origine) o (None, motivo_del_dubbio)."""
    cliente.carica()
    t = (testo or "").lower()
    for chiave, codice in cliente.regole["parola"]:
        if chiave and chiave in t:
            return codice, f"parola '{chiave}'"
    if piva_fornitore and piva_fornitore in cliente.regole["fornitore"]:
        return cliente.regole["fornitore"][piva_fornitore], f"fornitore P.IVA {piva_fornitore}"
    nf = _norm(nome_fornitore)
    if nf:
        for chiave_n, chiave, codice in cliente.regole["fornitore_nome"]:
            if chiave_n and (chiave_n in nf or nf in chiave_n):
                return codice, f"fornitore '{chiave}'"
    # categorie merceologiche (punteggio per indizi)
    migliore = (0, None, None)
    for nome, codice, chiavi in cliente.categorie:
        punti = sum(1 for k in chiavi if k in t)
        if punti > migliore[0]:
            migliore = (punti, nome, codice)
    if migliore[0] > 0:
        if migliore[1] == "veicoli":
            return _classifica_veicolo(t, cliente)
        if migliore[2] is None:
            return None, f"categoria '{migliore[1]}' senza codice nel piano del cliente"
        return migliore[2], f"categoria '{migliore[1]}' ({migliore[0]} indizi)"
    return None, "fornitore sconosciuto e nessun indizio nel testo"


def _classifica_veicolo(t, cliente):
    """Regole generiche per i veicoli: canone -> leasing/noleggio; acquisto
    -> cespite Autocarri o Autovetture (dal piano del cliente)."""
    if "leasing" in t:
        codice = cliente.codice_dal_piano("leasing")
        if codice:
            return codice, "veicolo in leasing"
        return None, "veicolo in leasing ma nessun conto leasing nel piano"
    if "nolegg" in t:
        codice = cliente.codice_dal_piano("nolegg")
        if codice:
            return codice, "veicolo a noleggio"
        return None, "veicolo a noleggio ma nessun conto noleggi nel piano"
    # acquisto: e' un cespite (4-20-4 autovetture / 4-20-5 autocarri) e in
    # nel gestionale va registrato col flag beni ammortizzabili manuale -> mai in automatico
    tipo = ("autocarro 4-20-5" if ("autocarr" in t or "furgon" in t or "rimorchi" in t)
            else "autovettura 4-20-4")
    return None, f"acquisto veicolo: cespite {tipo}, richiede flag BA manuale"


def decidi(fattura, cliente, verso):
    """Decisione completa su una fattura.

    verso: 'passiva' (cliente = cessionario) o 'attiva' (cliente = cedente).
    Ritorna dict: stato ('ok'|'dubbio'), causale, righe_conto=[{gruppo, conto,
    sottoconto, codice, imponibile, imposta, aliquota, natura, origine}],
    motivi (lista, se dubbio).
    """
    motivi = []
    tipo = fattura["tipo_doc"]
    if tipo in TIPI_REVERSE:
        return {"stato": "dubbio", "motivi": [f"autofattura/reverse charge ({tipo}): procedura manuale a 3 fasi"]}
    if tipo not in TIPI_GESTITI:
        motivi.append(f"tipo documento {tipo} mai gestito")
    if fattura["ritenuta"]:
        motivi.append("parcella con ritenuta d'acconto: registrazione a piu' conti dedicata")
    if fattura["divisa"] != "EUR":
        motivi.append(f"divisa {fattura['divisa']}")
    if not fattura["riepiloghi"]:
        motivi.append("nessun riepilogo IVA nell'XML")

    nota_credito = tipo in TIPI_NOTA_CREDITO
    if verso == "passiva":
        causale = "NOTA CREDITO FORNITORE" if nota_credito else "FATTURA ACQUISTI"
        controparte = fattura["cedente"]
    else:
        causale = "NOTA CREDITO CLIENTE" if nota_credito else "FATTURA DI VENDITA"
        controparte = fattura["cessionario"]
    if any(r["esigibilita"] == "S" for r in fattura["riepiloghi"]):
        causale = "SPLIT PAYMENT"

    righe_conto = []
    for riep in fattura["riepiloghi"]:
        if verso == "attiva":
            codice, origine = cliente.conto_ricavi, "conto ricavi del cliente"
        else:
            # testo delle sole righe con la stessa aliquota/natura del riepilogo
            testo = " ".join(
                r["descrizione"] for r in fattura["righe"]
                if abs(r["aliquota"] - riep["aliquota"]) < 0.01
                and (r["natura"] or "") == (riep["natura"] or "")
            ) or fattura["testo"]
            codice, origine = classifica_riga(
                testo, controparte["piva"], controparte["nome"], cliente)
            if codice is None:
                motivi.append(f"aliquota {riep['aliquota']:g}%: {origine}")
        pezzi = (codice or "--").split("-")
        righe_conto.append({
            "codice": codice,
            "gruppo": pezzi[0] if len(pezzi) == 3 else "",
            "conto": pezzi[1] if len(pezzi) == 3 else "",
            "sottoconto": pezzi[2] if len(pezzi) == 3 else "",
            "imponibile": riep["imponibile"],
            "imposta": riep["imposta"],
            "aliquota": riep["aliquota"],
            "natura": riep["natura"],
            "origine": origine,
        })

    # piu' riepiloghi decisi con codici diversi da regole deboli -> conferma umana
    if verso == "passiva" and len(righe_conto) > 1:
        codici = {r["codice"] for r in righe_conto}
        if len(codici) > 1 and any(
                r["origine"] and r["origine"].startswith("categoria") for r in righe_conto):
            motivi.append("multi-aliquota con codici diversi decisi solo per categoria")

    if motivi:
        return {"stato": "dubbio", "motivi": motivi, "causale": causale,
                "righe_conto": righe_conto}
    return {"stato": "ok", "causale": causale, "righe_conto": righe_conto,
            "motivi": []}
