# -*- coding: utf-8 -*-
"""
ia/cliente.py — Cliente unificado para Gemini y Copilot V14.
"""
from __future__ import annotations
from typing import Optional


class GeminiClient:
    """Cliente para Google Gemini API."""

    def __init__(self, api_key: str, modelo: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.modelo = modelo
        self._genai = None

    def _init_sdk(self):
        if self._genai is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._genai = genai
            except ImportError:
                raise ImportError(
                    "Instala: pip install google-generativeai"
                )

    def analizar_texto(self, texto: str, instruccion: str = "") -> str:
        self._init_sdk()
        model = self._genai.GenerativeModel(self.modelo)
        prompt = instruccion + "\n\n" + texto if instruccion else texto
        resp = model.generate_content(prompt)
        return resp.text

    def corregir_ocr(self, datos_ocr: dict) -> dict:
        """Pide a Gemini que corrija/valide los datos extraídos por OCR."""
        import json
        self._init_sdk()
        prompt = (
            "Eres un sistema de validación de facturas. "
            "Corrige los posibles errores OCR en estos datos extraídos. "
            "Responde SOLO en JSON con las mismas claves.\n\n"
            f"{json.dumps(datos_ocr, ensure_ascii=False, indent=2)}"
        )
        model = self._genai.GenerativeModel(self.modelo)
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except Exception:
            return datos_ocr

    def sugerir_regla(self, texto_factura: str) -> str:
        self._init_sdk()
        prompt = (
            "Analiza esta factura y sugiere qué campos OCR deberían extraerse "
            "y cómo identificar al proveedor. Responde en español.\n\n"
            + texto_factura[:3000]
        )
        model = self._genai.GenerativeModel(self.modelo)
        return model.generate_content(prompt).text

    def sugerir_para_visor(self, texto_factura: str) -> dict:
        """
        E: Analiza el texto OCR de una factura y sugiere proveedor, triggers,
        tipo de factura y valida campos (CIF/Base/IVA/Total).
        Devuelve dict con claves: proveedor, triggers, tipo_factura, campos, aviso_orientacion.
        """
        import json
        self._init_sdk()
        prompt = (
            "Eres un experto en gestión de facturas españolas. "
            "Analiza el siguiente texto OCR de una factura y devuelve SOLO un JSON con estas claves:\n"
            "  - proveedor: nombre probable del proveedor (string)\n"
            "  - triggers: lista de palabras/frases clave que identifican al proveedor (array de strings, max 5)\n"
            "  - tipo_factura: FACTURA|ABONO|TICKET|RECIBO (string)\n"
            "  - campos: objeto con cif_nif, base_imponible, iva, total, numero_factura si los detectas\n"
            "  - aviso_orientacion: true si el texto parece desordenado/cortado (posible mal orientación)\n"
            "Responde SOLO JSON, sin markdown.\n\n"
            f"{texto_factura[:4000]}"
        )
        model = self._genai.GenerativeModel(self.modelo)
        try:
            resp = model.generate_content(prompt)
            text = resp.text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:])
                text = text.split("```")[0]
            return json.loads(text)
        except Exception as exc:
            return {"error": str(exc), "proveedor": "", "triggers": [], "tipo_factura": "FACTURA",
                    "campos": {}, "aviso_orientacion": False}

    def ejecutar_instruccion(self, instruccion: str, ocr_text: str,
                              campos_actuales: dict = None) -> dict:
        """E/D: Ejecuta instrucción libre sobre el OCR. Retorna JSON de sugerencias."""
        import json
        self._init_sdk()
        ctx = ""
        if campos_actuales:
            ctx = f"\nCampos actuales detectados: {json.dumps(campos_actuales, ensure_ascii=False)}"
        prompt = (
            f"Instrucción del usuario: {instruccion}\n"
            f"Texto OCR de la factura:{ctx}\n\n{ocr_text[:3000]}\n\n"
            "Responde SOLO en JSON (sin markdown) con claves opcionales: "
            "trigger (string), triggers (array max 5), proveedor (string), "
            "cif_nif, base_imponible, iva, total, numero_factura, tipo_factura, "
            "zona_blanca_norm (objeto con x0,y0,x1,y1 en 0-1), razon (string)."
        )
        model = self._genai.GenerativeModel(self.modelo)
        try:
            resp = model.generate_content(prompt)
            text = resp.text.strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:]).split("```")[0]
            return json.loads(text)
        except Exception as exc:
            return {"razon": f"Error Gemini: {exc}"}

    def chat(self, historial: list, mensaje: str) -> str:
        self._init_sdk()
        model = self._genai.GenerativeModel(self.modelo)
        chat_session = model.start_chat(history=historial)
        resp = chat_session.send_message(mensaje)
        return resp.text


class CopilotClient:
    """Cliente para Microsoft Copilot via Azure AD / Graph API."""

    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    GRAPH_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None

    def _get_token(self) -> str:
        import urllib.request
        import urllib.parse
        import json
        if self._token:
            return self._token
        url = self.TOKEN_URL.format(tenant=self.tenant_id)
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        self._token = resp.get("access_token", "")
        return self._token

    def chat(self, mensaje: str, contexto: str = "") -> str:
        """
        Envía mensaje al endpoint de Copilot.
        Nota: requiere licencia M365 Copilot y permisos de API correctos.
        """
        import urllib.request
        import json
        token = self._get_token()
        # Usar el endpoint de chat completions de Azure OpenAI si está disponible
        # o el endpoint de Microsoft Copilot Studio
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": "Eres un asistente de gestión de facturas."},
                {"role": "user", "content": (contexto + "\n\n" + mensaje) if contexto else mensaje},
            ]
        }).encode()
        # Endpoint de demostración — sustituir por endpoint real de la empresa
        url = f"{self.GRAPH_URL}/chats/getCopilotResponse"
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            return data.get("message", {}).get("content", "Sin respuesta")
        except Exception as exc:
            return f"[Error Copilot: {exc}]"


class OllamaClient:
    """
    E-FIX: Cliente para Ollama local (modelos ligeros: phi3:mini, llama3.2:3b, etc.)
    Usa la API REST de Ollama en http://localhost:11434 por defecto.
    """

    def __init__(self, host: str = "http://localhost:11434", modelo: str = "phi3:mini",
                 timeout: int = 30):
        self.host    = host.rstrip("/")
        self.modelo  = modelo
        self.timeout = max(5, int(timeout))

    def _post(self, endpoint: str, payload: dict) -> dict:
        import urllib.request, json
        url  = f"{self.host}{endpoint}"
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(url, data=data,
                                       headers={"Content-Type": "application/json"},
                                       method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def analizar_texto(self, texto: str, instruccion: str = "") -> str:
        prompt = (instruccion + "\n\n" + texto) if instruccion else texto
        resp = self._post("/api/generate", {
            "model": self.modelo, "prompt": prompt, "stream": False
        })
        return resp.get("response", "").strip()

    def sugerir_para_visor(self, texto_factura: str) -> dict:
        import json
        prompt = (
            "Eres un experto en facturas españolas. Analiza este texto OCR y responde SOLO en JSON "
            "(sin markdown) con claves: proveedor, triggers (array max 5), tipo_factura, "
            "campos (objeto con cif_nif/base_imponible/iva/total/numero_factura), "
            "aviso_orientacion (bool si el texto parece desordenado).\n\n"
            f"{texto_factura[:3000]}"
        )
        try:
            resp = self._post("/api/generate", {
                "model": self.modelo, "prompt": prompt, "stream": False
            })
            text = resp.get("response", "").strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:]).split("```")[0]
            return json.loads(text)
        except Exception as exc:
            return {"error": str(exc), "proveedor": "", "triggers": [],
                    "tipo_factura": "FACTURA", "campos": {}, "aviso_orientacion": False}

    def chat(self, historial: list, mensaje: str) -> str:
        # Simplificado: no historial real en Ollama generate
        prompt = "\n".join(
            f"{'User' if m['role']=='user' else 'Assistant'}: {m.get('parts', [m.get('content','')])[0]}"
            for m in historial
        ) + f"\nUser: {mensaje}\nAssistant:"
        resp = self._post("/api/generate", {
            "model": self.modelo, "prompt": prompt, "stream": False
        })
        return resp.get("response", "").strip()

    def ejecutar_instruccion(self, instruccion: str, ocr_text: str,
                              campos_actuales: dict = None) -> dict:
        """E: Ejecuta una instrucción de lenguaje natural sobre el OCR. Retorna JSON de sugerencias."""
        import json
        ctx = ""
        if campos_actuales:
            ctx = f"\nCampos actuales detectados: {json.dumps(campos_actuales, ensure_ascii=False)}"
        prompt = (
            f"Instrucción del usuario: {instruccion}\n"
            f"Texto OCR de la factura:{ctx}\n\n{ocr_text[:3000]}\n\n"
            "Responde SOLO en JSON con claves opcionales: trigger (string), triggers (array), "
            "proveedor (string), cif_nif, base_imponible, iva, total, numero_factura, "
            "tipo_factura, zona_blanca_norm (objeto con x0,y0,x1,y1 en 0-1), razon (string)."
        )
        try:
            resp = self._post("/api/generate", {
                "model": self.modelo, "prompt": prompt, "stream": False
            })
            text = resp.get("response", "").strip()
            if text.startswith("```"):
                text = "\n".join(text.split("\n")[1:]).split("```")[0]
            return json.loads(text)
        except Exception as exc:
            return {"razon": f"Error Ollama: {exc}"}


def get_ia_client(db, motor: str = "gemini"):
    """Factory: devuelve el cliente IA configurado según BD. Soporta gemini, ollama, copilot."""
    cfg = db.get_ia_config(motor) if motor != "ollama" else db.get_ia_config("ollama")
    if motor == "gemini":
        api_key = cfg.get("api_key", "")
        modelo = cfg.get("modelo", "gemini-2.5-flash")
        if not api_key:
            raise ValueError("Configura la API Key de Gemini en Ajustes → IA")
        return GeminiClient(api_key, modelo)
    elif motor == "ollama":
        host    = cfg.get("host",    "http://localhost:11434")
        modelo  = cfg.get("modelo",  "phi3:mini")
        timeout = int(cfg.get("timeout", 30))
        return OllamaClient(host, modelo, timeout)
    elif motor == "copilot":
        tenant = cfg.get("tenant_id", "")
        cid = cfg.get("client_id", "")
        secret = cfg.get("client_secret", "")
        if not (tenant and cid):
            raise ValueError("Configura las credenciales de Copilot en Ajustes → IA")
        return CopilotClient(tenant, cid, secret)
    else:
        raise ValueError(f"Motor IA desconocido: {motor}")
