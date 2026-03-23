# -*- coding: utf-8 -*-
"""
generador_licencias.py — Generador de licencias profesional V12 con PyQt5.

USO: Solo para el AUTOR (JAMF).
     Usa la clave PRIVADA Ed25519 para firmar licencias.
     Los clientes solo tienen la clave PÚBLICA embebida.

FUNCIONES:
  - Campos: cliente, email, edición, expiración, features, HWID opcional
  - Botón GENERAR: crea archivo .lic firmado con Ed25519
  - Copia al portapapeles
  - Muestra detalles y firma
  - Genera pares de claves Ed25519

Ejecutar directamente:
  python licencias/generador_licencias.py
  (requiere la clave privada en 'licencias/private_key.pem')
"""
from __future__ import annotations
import base64, json, os, sys, uuid
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox,
    QPushButton, QTextEdit, QDateEdit, QMessageBox, QFileDialog,
    QTabWidget, QScrollArea, QSizePolicy, QFrame, QSpinBox
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont

# ── Estilos ──────────────────────────────────────────────────────────────────
BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
         "padding:7px 16px;font-weight:bold;font-size:12px;}"
         "QPushButton:hover{background:#2B6CB0;}")
BTN_G = ("QPushButton{background:#276749;color:white;border-radius:4px;"
         "padding:7px 16px;font-weight:bold;font-size:12px;}"
         "QPushButton:hover{background:#38A169;}")
BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
         "border-radius:4px;padding:7px 16px;}QPushButton:hover{background:#E2E8F0;}")
BTN_D = ("QPushButton{background:#C53030;color:white;border-radius:4px;"
         "padding:7px 16px;}QPushButton:hover{background:#9B2C2C;}")
INP   = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
         "padding:6px 10px;background:white;font-size:11px;}"
         "QLineEdit:focus{border:1px solid #3182CE;}")
CMB   = ("QComboBox{border:1px solid #CBD5E0;border-radius:4px;"
         "padding:6px 10px;background:white;font-size:11px;}"
         "QComboBox:focus{border:1px solid #3182CE;}")
GRP   = ("QGroupBox{font-weight:bold;border:1px solid #CBD5E0;"
         "border-radius:6px;margin-top:10px;padding-top:14px;"
         "font-size:11px;color:#2D3748;}")

_PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), "private_key.pem")
_PUBLIC_KEY_FILE  = os.path.join(os.path.dirname(__file__), "public_key.pem")

ALL_FEATURES = [
    ("ocr",              "OCR (extracción texto)"),
    ("visor_pdf",        "Visor PDF + selección"),
    ("informes",         "Módulo de informes"),
    ("excel_contable",   "Excel contable"),
    ("excel_resumen",    "Excel resumen"),
    ("clasificacion",    "Clasificación automática"),
    ("correo",           "Procesado de correo"),
    ("watermark",        "Archivado con marca de agua"),
    ("reglas_avanzadas", "Reglas visuales avanzadas"),
    ("multiseat",        "Multi-puesto"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Lógica de generación
# ═══════════════════════════════════════════════════════════════════════════════

def _load_private_key():
    """Carga la clave privada Ed25519 desde PEM."""
    if not os.path.exists(_PRIVATE_KEY_FILE):
        raise FileNotFoundError(
            f"Clave privada no encontrada: {_PRIVATE_KEY_FILE}\n"
            "Genera el par de claves primero con 'Generar Par de Claves'.")
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    pem = open(_PRIVATE_KEY_FILE,"rb").read()
    return load_pem_private_key(pem, password=None)


def _load_public_key():
    """Carga la clave pública Ed25519 desde PEM."""
    if not os.path.exists(_PUBLIC_KEY_FILE):
        raise FileNotFoundError(f"Clave pública no encontrada: {_PUBLIC_KEY_FILE}")
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    pem = open(_PUBLIC_KEY_FILE,"rb").read()
    return load_pem_public_key(pem)


def generar_par_claves():
    """Genera un nuevo par de claves Ed25519 y los guarda en PEM."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption
    )
    priv = Ed25519PrivateKey.generate()
    pub  = priv.public_key()
    priv_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pub_pem  = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    open(_PRIVATE_KEY_FILE,"wb").write(priv_pem)
    open(_PUBLIC_KEY_FILE, "wb").write(pub_pem)
    pub_b64 = base64.b64encode(pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).decode()
    return priv_pem.decode(), pub_pem.decode(), pub_b64


def generar_licencia(
    cliente:   str,
    email:     str,
    edicion:   str,
    features:  list,
    expira:    str,         # YYYY-MM-DD
    max_seats: int  = 1,
    hwid:      str  = None,
    grace_days: int = 7,
) -> str:
    """
    Genera una licencia V12 firmada con Ed25519.
    Devuelve el string base64 del archivo .lic.
    """
    payload = {
        "lic_id":    str(uuid.uuid4()),
        "cliente":   cliente,
        "email":     email,
        "edicion":   edicion,
        "features":  features,
        "expira":    expira,
        "emitida":   date.today().isoformat(),
        "max_seats": max_seats,
        "hwid":      hwid or None,
        "grace_days": grace_days,
    }
    payload_bytes = json.dumps(payload, separators=(",",":"), ensure_ascii=False).encode("utf-8")
    payload_b64   = base64.b64encode(payload_bytes).decode("utf-8")

    # Firmar con clave privada Ed25519
    priv = _load_private_key()
    sig  = priv.sign(payload_b64.encode("utf-8"))
    sig_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

    outer = {"payload": payload_b64, "signature": sig_b64}
    outer_bytes = json.dumps(outer, separators=(",",":")).encode("utf-8")
    lic_b64 = base64.b64encode(outer_bytes).decode("utf-8")
    return lic_b64, payload


# ═══════════════════════════════════════════════════════════════════════════════
# Interfaz PyQt5
# ═══════════════════════════════════════════════════════════════════════════════

class GeneradorLicencias(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🔐 Generador de Licencias JAMF — V12")
        self.setMinimumSize(900, 700)
        self._build()
        self._check_keys()

    def _check_keys(self):
        if not os.path.exists(_PRIVATE_KEY_FILE):
            self._log("⚠️ No se encontró clave privada. Ve a 'Claves' → 'Generar Par de Claves'.")

    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        main_lay = QVBoxLayout(central); main_lay.setContentsMargins(16,16,16,16)

        # Título
        title = QLabel("🔐  Generador de Licencias JAMF — V12")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#1F4E79;padding:8px 0;")
        main_lay.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab{padding:8px 16px;font-size:11px;}"
                           "QTabBar::tab:selected{background:#1F4E79;color:white;font-weight:bold;}")
        tabs.addTab(self._tab_generar(), "📄 Generar Licencia")
        tabs.addTab(self._tab_claves(),  "🔑 Gestión de Claves")
        main_lay.addWidget(tabs)

        # Log
        log_lbl = QLabel("📋 Log:")
        log_lbl.setStyleSheet("font-weight:bold;color:#2D3748;")
        main_lay.addWidget(log_lbl)
        self._txt_log = QTextEdit(); self._txt_log.setReadOnly(True)
        self._txt_log.setFixedHeight(120)
        self._txt_log.setStyleSheet("font-family:Consolas;font-size:9px;"
                                     "background:#1A202C;color:#68D391;border:none;")
        main_lay.addWidget(self._txt_log)

    def _tab_generar(self) -> QWidget:
        w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(12,12,12,12)

        # Izquierda: formulario
        left = QWidget(); left.setFixedWidth(420)
        fl = QVBoxLayout(left)

        # ── Datos cliente ─────────────────────────────────────────────────────
        grp1 = QGroupBox("Datos del Cliente"); grp1.setStyleSheet(GRP)
        f1 = QFormLayout(grp1); f1.setSpacing(8)
        self.inp_cliente = QLineEdit(); self.inp_cliente.setStyleSheet(INP)
        self.inp_cliente.setPlaceholderText("Nombre empresa o persona")
        self.inp_email   = QLineEdit(); self.inp_email.setStyleSheet(INP)
        self.inp_email.setPlaceholderText("email@dominio.com")
        self.inp_hwid    = QLineEdit(); self.inp_hwid.setStyleSheet(INP)
        self.inp_hwid.setPlaceholderText("Opcional: hash hardware")
        f1.addRow("Cliente:", self.inp_cliente)
        f1.addRow("Email:",   self.inp_email)
        f1.addRow("HWID:",    self.inp_hwid)
        fl.addWidget(grp1)

        # ── Edición ───────────────────────────────────────────────────────────
        grp2 = QGroupBox("Edición y Validez"); grp2.setStyleSheet(GRP)
        f2 = QFormLayout(grp2); f2.setSpacing(8)
        self.cmb_edicion = QComboBox(); self.cmb_edicion.setStyleSheet(CMB)
        self.cmb_edicion.addItems(["Standard","Pro","Trial","Enterprise"])
        self.cmb_edicion.currentTextChanged.connect(self._on_edicion_change)
        self.dte_expira = QDateEdit(QDate.currentDate().addYears(1))
        self.dte_expira.setCalendarPopup(True); self.dte_expira.setDisplayFormat("dd/MM/yyyy")
        self.spn_grace = QSpinBox(); self.spn_grace.setRange(0,30); self.spn_grace.setValue(7)
        self.spn_seats = QSpinBox(); self.spn_seats.setRange(1,100); self.spn_seats.setValue(1)
        f2.addRow("Edición:",    self.cmb_edicion)
        f2.addRow("Expira:",     self.dte_expira)
        f2.addRow("Grace days:", self.spn_grace)
        f2.addRow("Max seats:",  self.spn_seats)
        fl.addWidget(grp2)

        # ── Features ─────────────────────────────────────────────────────────
        grp3 = QGroupBox("Features habilitados"); grp3.setStyleSheet(GRP)
        f3 = QVBoxLayout(grp3); f3.setSpacing(4)
        self._chk_features = {}
        for key, label in ALL_FEATURES:
            chk = QCheckBox(label)
            self._chk_features[key] = chk
            f3.addWidget(chk)
        # Botones de selección rápida
        rb = QHBoxLayout()
        bs = QPushButton("Standard"); bs.setStyleSheet(BTN_S); bs.setFixedHeight(28)
        bs.clicked.connect(self._sel_standard)
        bp = QPushButton("Pro"); bp.setStyleSheet(BTN_S); bp.setFixedHeight(28)
        bp.clicked.connect(self._sel_pro)
        bn = QPushButton("Ninguno"); bn.setStyleSheet(BTN_S); bn.setFixedHeight(28)
        bn.clicked.connect(self._sel_none)
        rb.addWidget(bs); rb.addWidget(bp); rb.addWidget(bn)
        f3.addLayout(rb)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setWidget(grp3); sc.setFixedHeight(260)
        fl.addWidget(sc)

        btn_gen = QPushButton("⚡ GENERAR LICENCIA")
        btn_gen.setStyleSheet(BTN_G); btn_gen.setFixedHeight(44)
        btn_gen.clicked.connect(self._generar)
        fl.addWidget(btn_gen)

        lay.addWidget(left)

        # Derecha: resultado
        right = QWidget(); rl = QVBoxLayout(right)

        rl.addWidget(QLabel("📄 Licencia generada (base64):"))
        self._txt_lic = QTextEdit(); self._txt_lic.setReadOnly(True)
        self._txt_lic.setStyleSheet("font-family:Consolas;font-size:8px;"
                                    "background:#F7FAFC;border:1px solid #CBD5E0;")
        rl.addWidget(self._txt_lic)

        rl.addWidget(QLabel("🔍 Detalles del payload:"))
        self._txt_det = QTextEdit(); self._txt_det.setReadOnly(True)
        self._txt_det.setStyleSheet("font-family:Consolas;font-size:10px;"
                                    "background:#FFFFF0;border:1px solid #ECC94B;")
        self._txt_det.setFixedHeight(180)
        rl.addWidget(self._txt_det)

        btn_bar = QHBoxLayout()
        bc = QPushButton("📋 Copiar al portapapeles"); bc.setStyleSheet(BTN_P)
        bc.clicked.connect(self._copiar)
        bs = QPushButton("💾 Guardar .lic"); bs.setStyleSheet(BTN_G)
        bs.clicked.connect(self._guardar)
        btn_bar.addWidget(bc); btn_bar.addWidget(bs)
        rl.addLayout(btn_bar)
        lay.addWidget(right)

        self._sel_standard()   # seleccionar features Standard por defecto
        return w

    def _tab_claves(self) -> QWidget:
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(16,16,16,16)
        lay.setAlignment(Qt.AlignTop)

        info = QLabel(
            "El par de claves Ed25519 debe generarse UNA VEZ.\n"
            "La clave privada (private_key.pem) debe mantenerse segura.\n"
            "La clave pública (public_key.pem) se embebe en el cliente.")
        info.setStyleSheet("color:#4A5568;font-size:11px;background:#EDF2F7;"
                           "padding:10px;border-radius:6px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        grp = QGroupBox("Claves actuales"); grp.setStyleSheet(GRP)
        fl = QVBoxLayout(grp)
        self._txt_pub = QTextEdit(); self._txt_pub.setReadOnly(True)
        self._txt_pub.setStyleSheet("font-family:Consolas;font-size:9px;")
        self._txt_pub.setFixedHeight(140)
        self._txt_pub.setPlaceholderText("Clave pública PEM...")
        fl.addWidget(QLabel("Clave Pública (PEM):"))
        fl.addWidget(self._txt_pub)
        self._lbl_pub_b64 = QLineEdit(); self._lbl_pub_b64.setReadOnly(True)
        self._lbl_pub_b64.setStyleSheet(INP)
        self._lbl_pub_b64.setPlaceholderText("Clave pública DER en base64 (para embeber en licenciamiento.py)")
        fl.addWidget(QLabel("Clave Pública Base64 (para licenciamiento.py):"))
        fl.addWidget(self._lbl_pub_b64)
        lay.addWidget(grp)

        btn_bar = QHBoxLayout()
        bg = QPushButton("🔑 Generar NUEVO Par de Claves"); bg.setStyleSheet(BTN_G)
        bg.clicked.connect(self._generar_claves)
        bl = QPushButton("📂 Cargar par existente"); bl.setStyleSheet(BTN_S)
        bl.clicked.connect(self._cargar_claves)
        bc = QPushButton("📋 Copiar Clave Pública B64"); bc.setStyleSheet(BTN_P)
        bc.clicked.connect(lambda: QApplication.clipboard().setText(self._lbl_pub_b64.text()))
        btn_bar.addWidget(bg); btn_bar.addWidget(bl); btn_bar.addWidget(bc)
        lay.addLayout(btn_bar)

        warn = QLabel("⚠️ IMPORTANTE: Guarda private_key.pem en un lugar SEGURO. "
                      "Sin ella no podrás generar más licencias.")
        warn.setStyleSheet("color:#C53030;font-weight:bold;font-size:11px;"
                           "background:#FFF5F5;padding:8px;border-radius:4px;")
        warn.setWordWrap(True); lay.addWidget(warn)

        self._refresh_keys_ui()
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_edicion_change(self, ed):
        if ed == "Pro":       self._sel_pro()
        elif ed == "Standard": self._sel_standard()
        elif ed == "Trial":   self._sel_standard()

    def _sel_standard(self):
        standard = ["ocr","visor_pdf","excel_resumen","clasificacion","watermark"]
        for k, chk in self._chk_features.items():
            chk.setChecked(k in standard)

    def _sel_pro(self):
        for chk in self._chk_features.values(): chk.setChecked(True)

    def _sel_none(self):
        for chk in self._chk_features.values(): chk.setChecked(False)

    def _generar(self):
        cliente  = self.inp_cliente.text().strip()
        email    = self.inp_email.text().strip()
        edicion  = self.cmb_edicion.currentText()
        expira   = self.dte_expira.date().toString("yyyy-MM-dd")
        grace    = self.spn_grace.value()
        seats    = self.spn_seats.value()
        hwid     = self.inp_hwid.text().strip() or None
        features = [k for k, chk in self._chk_features.items() if chk.isChecked()]

        if not cliente:
            QMessageBox.warning(self,"Datos incompletos","Introduce el nombre del cliente."); return
        if not features:
            QMessageBox.warning(self,"Sin features","Selecciona al menos un feature."); return

        try:
            lic_b64, payload = generar_licencia(
                cliente=cliente, email=email, edicion=edicion,
                features=features, expira=expira, max_seats=seats,
                hwid=hwid, grace_days=grace)
            self._txt_lic.setPlainText(lic_b64)
            det = json.dumps(payload, indent=2, ensure_ascii=False)
            self._txt_det.setPlainText(det)
            self._log(f"✅ Licencia generada: {payload['lic_id']} | {edicion} | {cliente} | expira {expira}")
        except FileNotFoundError as exc:
            QMessageBox.critical(self,"Sin clave privada",str(exc))
        except Exception as exc:
            QMessageBox.critical(self,"Error",str(exc))
            self._log(f"❌ Error: {exc}")

    def _copiar(self):
        txt = self._txt_lic.toPlainText()
        if txt:
            QApplication.clipboard().setText(txt)
            self._log("📋 Licencia copiada al portapapeles.")
        else:
            QMessageBox.warning(self,"Sin licencia","Genera una licencia primero.")

    def _guardar(self):
        txt = self._txt_lic.toPlainText()
        if not txt:
            QMessageBox.warning(self,"Sin licencia","Genera una licencia primero."); return
        path, _ = QFileDialog.getSaveFileName(self,"Guardar licencia","licencia.lic",
                                               "Licencias (*.lic);;Todos (*)")
        if path:
            open(path,"w",encoding="utf-8").write(txt)
            self._log(f"💾 Licencia guardada: {path}")

    def _generar_claves(self):
        resp = QMessageBox.question(self,"Confirmar",
            "¿Generar NUEVO par de claves Ed25519?\n\n"
            "⚠️ Las licencias firmadas con claves antiguas DEJARÁN DE FUNCIONAR\n"
            "si cambias la clave pública en licenciamiento.py.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        try:
            priv_pem, pub_pem, pub_b64 = generar_par_claves()
            self._refresh_keys_ui()
            QMessageBox.information(self,"✅ Claves generadas",
                f"Par de claves Ed25519 generado:\n"
                f"  private_key.pem → {_PRIVATE_KEY_FILE}\n"
                f"  public_key.pem  → {_PUBLIC_KEY_FILE}\n\n"
                f"Copia la clave pública base64 en licenciamiento.py\n"
                f"en la variable _PUBLIC_KEY_B64")
            self._log("✅ Par de claves Ed25519 generado.")
        except Exception as exc:
            QMessageBox.critical(self,"Error",str(exc))

    def _cargar_claves(self):
        self._refresh_keys_ui()
        self._log("🔑 Claves recargadas.")

    def _refresh_keys_ui(self):
        if os.path.exists(_PUBLIC_KEY_FILE):
            try:
                from cryptography.hazmat.primitives.serialization import (
                    load_pem_public_key, Encoding, PublicFormat
                )
                pub_pem = open(_PUBLIC_KEY_FILE,"rb").read()
                pub_key = load_pem_public_key(pub_pem)
                pub_b64 = base64.b64encode(
                    pub_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
                ).decode()
                self._txt_pub.setPlainText(pub_pem.decode())
                self._lbl_pub_b64.setText(pub_b64)
            except Exception as exc:
                self._txt_pub.setPlainText(f"Error cargando: {exc}")
        else:
            self._txt_pub.setPlainText("(no encontrada — genera el par de claves)")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._txt_log.append(f"[{ts}] {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = GeneradorLicencias()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
