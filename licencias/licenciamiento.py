# -*- coding: utf-8 -*-
"""
licenciamiento.py — Sistema de licencias V12 con Ed25519 + retrocompatibilidad V11.

ARQUITECTURA:
  - Ed25519 asimétrico: clave pública embebida en cliente, privada solo en generador
  - Licencia V12 = base64(JSON{"payload":b64(JSON),"signature":b64url_ed25519})
  - Retrocompatibilidad total con licencias HMAC-SHA256 V11
  - Modo restringido automático si licencia inválida
  - grace_days: días de gracia tras expiración
  - features: activa/desactiva módulos

FORMATO LICENCIA V12:
  {
    "lic_id": "<uuid4>",
    "cliente": "<nombre>",
    "email": "<email>",
    "edicion": "Standard|Pro",
    "features": ["ocr","visor_pdf","informes","excel_contable",...],
    "expira": "YYYY-MM-DD",
    "emitida": "YYYY-MM-DD",
    "max_seats": 1,
    "hwid": "<opcional>",
    "grace_days": 7
  }
"""
from __future__ import annotations
import base64, hashlib, json, os, sys
from datetime import date, datetime, timedelta
from typing import List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Clave pública Ed25519 embebida ─────────────────────────────────────────────
# En producción, sustituir por la clave real generada con keygen_licencias.py
# Formato DER SubjectPublicKeyInfo → base64 estándar
_PUBLIC_KEY_B64 = (
    "MCowBQYDK2VwAyEAZT4qMgGOHACE9qFCdBT9n2YvAQr8sXkUv5bF1gJH3tI="
)

# Clave HMAC para licencias V11 legacy
_LEGACY_SECRET = "JAMF-GESTOR-FACTURAS-2025"
_LIC_FILE      = "licencia.lic"

ALL_FEATURES      = ["ocr","visor_pdf","informes","excel_contable","excel_resumen",
                     "clasificacion","correo","watermark","reglas_avanzadas","multiseat"]
STANDARD_FEATURES = ["ocr","visor_pdf","excel_resumen","clasificacion","watermark"]
PRO_FEATURES      = ALL_FEATURES.copy()


def _verify_ed25519(payload_b64: str, sig_b64: str) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.exceptions import InvalidSignature
        pub_der = base64.b64decode(_PUBLIC_KEY_B64 + "==")
        pub_key = load_der_public_key(pub_der)
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        pub_key.verify(sig, payload_b64.encode("utf-8"))
        return True
    except Exception:
        return False


def _verify_hmac_v11(data: dict, firma: str) -> bool:
    cadena = f"{data.get('tipo')}{data.get('empresa')}{data.get('fecha_creacion')}{_LEGACY_SECRET}"
    return hashlib.sha256(cadena.encode()).hexdigest()[:32] == firma


class GestorLicencias:
    """Gestor de licencias V12. Compatible en API con versiones anteriores."""

    ARCHIVO_LICENCIA = _LIC_FILE
    CLAVE_MAESTRA    = _LEGACY_SECRET
    AUTOR            = "JAMF"

    def __init__(self, lic_file: str = None):
        self._lic_file = lic_file or _LIC_FILE
        # Estado
        self.valida         = False
        self.tipo_licencia  = "TRIAL"
        self.cliente        = ""
        self.email          = ""
        self.edicion        = "Trial"
        self.features:      List[str] = []
        self.expira:        Optional[date] = None
        self.grace_days     = 7
        self.dias_restantes = 0
        self.max_seats      = 1
        self.lic_id         = ""
        self._cargar()

    # Aliases retrocompatibilidad
    @property
    def licencia_valida(self): return self.valida
    @property
    def empresa(self):         return self.cliente

    def _cargar(self):
        if not os.path.exists(self._lic_file):
            self._crear_trial(); return
        try:
            raw = open(self._lic_file, "r", encoding="utf-8").read().strip()
            # ── Intentar V12 (base64 compuesto) ──────────────────────────────
            try:
                outer = json.loads(base64.b64decode(raw + "==").decode("utf-8"))
                if "payload" in outer and "signature" in outer:
                    if self._cargar_v12(outer): return
            except Exception:
                pass
            # ── Intentar V11 (JSON plano) ─────────────────────────────────────
            try:
                data = json.loads(raw)
                if self._cargar_v11(data): return
            except Exception:
                pass
        except Exception:
            pass
        self._crear_trial()

    def _cargar_v12(self, outer: dict) -> bool:
        payload_b64 = outer["payload"]
        sig_b64     = outer["signature"]
        # En modo desarrollo (clave placeholder), saltamos verificación
        if not _verify_ed25519(payload_b64, sig_b64):
            if "ZT4qMgGOHACE" not in _PUBLIC_KEY_B64:   # clave real presente
                return False   # firma inválida
            # else: modo dev, aceptamos sin verificar
        try:
            payload = json.loads(base64.b64decode(payload_b64 + "==").decode("utf-8"))
        except Exception:
            return False

        try:
            expira = date.fromisoformat(payload.get("expira","2099-12-31"))
        except Exception:
            expira = date(2099,12,31)

        grace    = int(payload.get("grace_days",7))
        efectivo = expira + timedelta(days=grace)
        hoy      = date.today()

        if hoy > efectivo:
            self.valida = False; self.tipo_licencia = "EXPIRADA"
            self.dias_restantes = 0; return True

        self.valida         = True
        self.tipo_licencia  = "V12"
        self.lic_id         = payload.get("lic_id","")
        self.cliente        = payload.get("cliente","")
        self.email          = payload.get("email","")
        self.edicion        = payload.get("edicion","Standard")
        self.features       = payload.get("features", STANDARD_FEATURES)
        self.expira         = expira
        self.grace_days     = grace
        self.max_seats      = int(payload.get("max_seats",1))
        self.dias_restantes = (efectivo - hoy).days
        return True

    def _cargar_v11(self, data: dict) -> bool:
        if not _verify_hmac_v11(data, data.get("firma","")):
            return False
        tipo = data.get("tipo","TRIAL")
        if tipo == "FULL":
            self.valida = True; self.tipo_licencia = "FULL"
            self.cliente = data.get("empresa",""); self.dias_restantes = 99999
            self.features = ALL_FEATURES; self.edicion = "Pro"; return True
        if tipo == "TRIAL":
            try:
                fecha_exp = datetime.fromisoformat(data.get("fecha_expiracion",""))
                if datetime.now() <= fecha_exp:
                    self.valida = True; self.tipo_licencia = "TRIAL"
                    self.dias_restantes = (fecha_exp-datetime.now()).days
                    self.features = STANDARD_FEATURES; self.edicion = "Trial"
                    self.cliente = data.get("empresa",""); return True
            except Exception: pass
            self.valida = False; self.tipo_licencia = "EXPIRADA"; return True
        return False

    def _crear_trial(self):
        self.valida = True; self.tipo_licencia = "TRIAL"
        self.cliente = "TRIAL"; self.edicion = "Trial"
        self.features = STANDARD_FEATURES; self.dias_restantes = 30
        datos = {"tipo":"TRIAL","empresa":"TRIAL",
                 "fecha_creacion": datetime.now().isoformat(),
                 "fecha_expiracion": (datetime.now()+timedelta(days=30)).isoformat(),
                 "autor":"JAMF"}
        datos["firma"] = hashlib.sha256(
            f"{datos['tipo']}{datos['empresa']}{datos['fecha_creacion']}{_LEGACY_SECRET}".encode()
        ).hexdigest()[:32]
        try:
            open(self._lic_file,"w",encoding="utf-8").write(json.dumps(datos))
        except Exception: pass

    # ── API pública ────────────────────────────────────────────────────────────

    def puede_usar_software(self) -> bool:
        return self.valida

    def puede_usar(self) -> bool:
        return self.valida

    def tiene_feature(self, feature: str) -> bool:
        return self.valida and feature in self.features

    def activar_desde_archivo(self, ruta: str) -> tuple:
        try:
            import shutil
            shutil.copy(ruta, self._lic_file)
            self.__init__(self._lic_file)
            if self.valida:
                return True, f"Licencia activada: {self.edicion} para {self.cliente}"
            return False, "Licencia inválida o expirada."
        except Exception as exc:
            return False, str(exc)

    def activar_desde_texto(self, texto: str) -> tuple:
        try:
            open(self._lic_file,"w",encoding="utf-8").write(texto.strip())
            self.__init__(self._lic_file)
            if self.valida:
                return True, f"Licencia activada: {self.edicion} para {self.cliente}"
            return False, "Licencia inválida o expirada."
        except Exception as exc:
            return False, str(exc)

    def activar_licencia_full(self, codigo: str, nombre_empresa: str) -> bool:
        esperado = hashlib.sha256(
            f"{nombre_empresa.upper()}{_LEGACY_SECRET}".encode()
        ).hexdigest()[:24].upper()
        if codigo.upper().strip() != esperado:
            return False
        datos = {"tipo":"FULL","empresa":nombre_empresa,
                 "fecha_creacion":datetime.now().isoformat(),
                 "fecha_expiracion":"9999-12-31T00:00:00","autor":"JAMF"}
        datos["firma"] = hashlib.sha256(
            f"{datos['tipo']}{datos['empresa']}{datos['fecha_creacion']}{_LEGACY_SECRET}".encode()
        ).hexdigest()[:32]
        try:
            open(self._lic_file,"w",encoding="utf-8").write(json.dumps(datos))
        except Exception:
            return False
        self._cargar_v11(datos)
        return True

    def generar_codigo_activacion(self, nombre: str) -> str:
        return hashlib.sha256(
            f"{nombre.upper()}{_LEGACY_SECRET}".encode()
        ).hexdigest()[:24].upper()

    def obtener_info_licencia(self) -> dict:
        return {
            "tipo":           self.tipo_licencia,
            "empresa":        self.cliente,
            "email":          self.email,
            "edicion":        self.edicion,
            "features":       self.features,
            "dias_restantes": self.dias_restantes if self.tipo_licencia not in ("FULL","V12") else "∞",
            "valida":         self.valida,
            "lic_id":         self.lic_id,
            "autor":          "JAMF",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# UI PyQt5 — Ventana de activación
# ═══════════════════════════════════════════════════════════════════════════════

class VentanaActivarLicencia:
    """Ventana de activación V12. Soporta código HMAC (V11) y archivo .lic (V12)."""

    def __new__(cls, parent, gestor: GestorLicencias):
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QFormLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QHBoxLayout, QMessageBox,
            QTabWidget, QWidget, QTextEdit, QFileDialog
        )
        from PyQt5.QtCore import Qt

        BTN_P = ("QPushButton{background:#1F4E79;color:white;border-radius:4px;"
                 "padding:6px 14px;font-weight:bold;}QPushButton:hover{background:#2B6CB0;}")
        BTN_S = ("QPushButton{background:#EDF2F7;color:#2D3748;border:1px solid #CBD5E0;"
                 "border-radius:4px;padding:6px 14px;}QPushButton:hover{background:#E2E8F0;}")
        INP   = ("QLineEdit{border:1px solid #CBD5E0;border-radius:4px;"
                 "padding:5px 8px;background:white;}QLineEdit:focus{border:1px solid #3182CE;}")

        class _Dlg(QDialog):
            def __init__(self_, g, par):
                super().__init__(par)
                self_.g = g
                self_.setWindowTitle("🔐 Activar Licencia — JES⚡THOR JAMF")
                self_.setMinimumWidth(540)
                self_.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
                self_._build()

            def _build(self_):
                lay = QVBoxLayout(self_); lay.setContentsMargins(20,18,20,16); lay.setSpacing(12)
                info = self_.g.obtener_info_licencia()
                c = "#276749" if info["valida"] and info["tipo"] not in ("TRIAL","EXPIRADA") else "#C05621"
                lbl = QLabel(f"<b>Estado:</b> <span style='color:{c};'>{info['tipo']}</span>  "
                             f"| Edición: <b>{info['edicion']}</b>  "
                             f"| Días: <b>{info['dias_restantes']}</b>")
                lbl.setStyleSheet("font-size:12px;"); lay.addWidget(lbl)

                tabs = QTabWidget()

                # ── Tab código HMAC (V11) ─────────────────────────────────────
                t1 = QWidget(); f1 = QFormLayout(t1); f1.setContentsMargins(12,12,12,12)
                self_.inp_empresa = QLineEdit(); self_.inp_empresa.setStyleSheet(INP)
                self_.inp_empresa.setPlaceholderText("Nombre exacto de empresa")
                self_.inp_codigo  = QLineEdit(); self_.inp_codigo.setStyleSheet(INP)
                self_.inp_codigo.setPlaceholderText("Código de 24 caracteres")
                f1.addRow("Empresa:", self_.inp_empresa); f1.addRow("Código:", self_.inp_codigo)
                r1 = QHBoxLayout()
                bp = QPushButton("📋 Pegar"); bp.setStyleSheet(BTN_S)
                bp.clicked.connect(lambda: self_.inp_codigo.setText(
                    __import__("PyQt5.QtWidgets", fromlist=["QApplication"]).QApplication.clipboard().text().strip()))
                ba = QPushButton("🔐 Activar"); ba.setStyleSheet(BTN_P)
                ba.clicked.connect(self_._activar_codigo)
                r1.addWidget(bp); r1.addStretch(); r1.addWidget(ba)
                f1.addRow("", r1)
                tabs.addTab(t1, "🔑 Código V11")

                # ── Tab archivo .lic V12 ──────────────────────────────────────
                t2 = QWidget(); f2 = QVBoxLayout(t2); f2.setContentsMargins(12,12,12,12)
                f2.addWidget(QLabel("Importa un archivo .lic generado por JAMF:"))
                self_.inp_path = QLineEdit(); self_.inp_path.setStyleSheet(INP)
                self_.inp_path.setReadOnly(True); self_.inp_path.setPlaceholderText("ruta/licencia.lic")
                r2 = QHBoxLayout()
                bsel = QPushButton("📂 Seleccionar .lic"); bsel.setStyleSheet(BTN_S)
                bsel.clicked.connect(self_._seleccionar)
                bimp = QPushButton("📥 Importar"); bimp.setStyleSheet(BTN_P)
                bimp.clicked.connect(self_._importar)
                r2.addWidget(bsel); r2.addStretch(); r2.addWidget(bimp)
                f2.addWidget(self_.inp_path); f2.addLayout(r2)
                f2.addWidget(QLabel("\nO pega el contenido base64 de la licencia:"))
                self_.txt_b64 = QTextEdit(); self_.txt_b64.setFixedHeight(90)
                self_.txt_b64.setStyleSheet("font-family:Consolas;font-size:8px;")
                f2.addWidget(self_.txt_b64)
                bpt = QPushButton("📥 Activar desde texto"); bpt.setStyleSheet(BTN_P)
                bpt.clicked.connect(self_._activar_texto)
                f2.addWidget(bpt)
                tabs.addTab(t2, "📄 Archivo .lic V12")

                lay.addWidget(tabs)
                bc = QPushButton("Cerrar"); bc.setStyleSheet(BTN_S)
                bc.clicked.connect(self_.reject); lay.addWidget(bc)

            def _activar_codigo(self_):
                emp = self_.inp_empresa.text().strip()
                cod = self_.inp_codigo.text().strip()
                if not emp or not cod:
                    QMessageBox.warning(self_,"Datos incompletos","Introduce empresa y código."); return
                if self_.g.activar_licencia_full(cod, emp):
                    QMessageBox.information(self_,"✅ Activado",f"Licencia FULL activada para:\n{emp}"); self_.accept()
                else:
                    QMessageBox.critical(self_,"Error de Activación","Código inválido.\nVerifica empresa y código.")

            def _seleccionar(self_):
                from PyQt5.QtWidgets import QFileDialog
                p,_ = QFileDialog.getOpenFileName(self_,"Seleccionar licencia","","Licencias (*.lic);;Todos (*)")
                if p: self_.inp_path.setText(p)

            def _importar(self_):
                p = self_.inp_path.text().strip()
                if not p: QMessageBox.warning(self_,"Sin archivo","Selecciona un .lic"); return
                ok, msg = self_.g.activar_desde_archivo(p)
                (QMessageBox.information if ok else QMessageBox.critical)(self_, "✅" if ok else "Error", msg)
                if ok: self_.accept()

            def _activar_texto(self_):
                txt = self_.txt_b64.toPlainText().strip()
                if not txt: QMessageBox.warning(self_,"Sin texto","Pega el contenido de la licencia"); return
                ok, msg = self_.g.activar_desde_texto(txt)
                (QMessageBox.information if ok else QMessageBox.critical)(self_, "✅" if ok else "Error", msg)
                if ok: self_.accept()

        dlg = _Dlg(gestor, parent); dlg.exec_(); return dlg


# ── Funciones de utilidad (API V11) ──────────────────────────────────────────

def verificar_licencia_al_inicio() -> bool:
    g = GestorLicencias()
    if not g.puede_usar_software():
        from PyQt5.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None,"Licencia Expirada",
            "La licencia ha expirado.\nContacta con JAMF para renovarla.")
        return False
    return True


def mostrar_ventana_licencia(parent=None):
    VentanaActivarLicencia(parent, GestorLicencias())


def generar_codigo_para_empresa(nombre: str) -> str:
    g = GestorLicencias()
    c = g.generar_codigo_activacion(nombre)
    print(f"\nCódigo para '{nombre}':\n{'='*50}\n{c}\n{'='*50}\n")
    return c


if __name__ == "__main__":
    nombre = input("Empresa: ").strip()
    if nombre: generar_codigo_para_empresa(nombre)
    else:       mostrar_ventana_licencia()
