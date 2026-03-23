# -*- coding: utf-8 -*-
"""
alertas/motor.py — Motor de alertas V14.
Comprueba alertas activas y envía notificaciones por email.
"""
from __future__ import annotations
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict

from core.logging_config import get_logger
log = get_logger("alertas")


def comprobar_y_disparar(factura: dict, db) -> List[Dict]:
    """
    Comprueba alertas para una factura recién procesada.
    Devuelve lista de alertas disparadas.
    """
    disparadas = db.verificar_alertas_factura(factura)
    smtp = db.get_smtp_config()
    for d in disparadas:
        alerta = d["alerta"]
        detalle = d["detalle"]
        emails = [e.strip() for e in alerta.get("emails", "").split(",") if e.strip()]
        email_a = ""
        if emails and smtp.get("host"):
            try:
                enviar_email_alerta(smtp, emails, alerta["nombre"], detalle, adjunto_pdf=factura.get("ruta_pdf_procesado", ""))
                email_a = ", ".join(emails)
            except Exception as exc:
                log.warning("Error enviando email alerta: %s", exc)
        db.registrar_alerta_disparada(
            alerta["id"], detalle,
            factura_ref=str(factura.get("numero_factura", "")),
            email_a=email_a
        )
        log.info("Alerta disparada: %s — %s", alerta["nombre"], detalle)
    return disparadas


def enviar_email_alerta(smtp_cfg: dict, destinatarios: List[str],
                         nombre_alerta: str, detalle: str,
                         adjunto_pdf: str = None) -> None:
    """Envía email de alerta via SMTP configurado. adjunto_pdf: ruta al PDF estampado."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"⚠ Alerta Gestor Facturas: {nombre_alerta}"
    msg["From"] = smtp_cfg.get("from_email", smtp_cfg.get("usuario", ""))
    msg["To"] = ", ".join(destinatarios)

    html = f"""
    <html><body>
    <h2 style="color:#C05621;">⚠ Alerta: {nombre_alerta}</h2>
    <p>{detalle}</p>
    <hr><small>Gestor Facturas Pro — {datetime.now().strftime('%d/%m/%Y %H:%M')}</small>
    </body></html>
    """
    msg.attach(MIMEText(detalle, "plain"))
    msg.attach(MIMEText(html, "html"))
    if adjunto_pdf:
        try:
            from email.mime.application import MIMEApplication
            import os as _os
            with open(adjunto_pdf, "rb") as _f:
                _part = MIMEApplication(_f.read(), Name=_os.path.basename(adjunto_pdf))
                _part["Content-Disposition"] = f'attachment; filename="{_os.path.basename(adjunto_pdf)}"'
                msg.attach(_part)
        except Exception as _e:
            log.warning("No se pudo adjuntar PDF: %s", _e)

    host = smtp_cfg["host"]
    port = int(smtp_cfg.get("port", 587))
    use_ssl = bool(smtp_cfg.get("ssl", 1))
    usuario = smtp_cfg.get("usuario", "")
    password = smtp_cfg.get("password", "")

    if use_ssl and port == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx) as s:
            if usuario:
                s.login(usuario, password)
            s.sendmail(msg["From"], destinatarios, msg.as_string())
    else:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            if use_ssl:
                s.starttls()
            if usuario:
                s.login(usuario, password)
            s.sendmail(msg["From"], destinatarios, msg.as_string())


def probar_smtp(smtp_cfg: dict, email_prueba: str) -> str:
    """Envía email de prueba. Devuelve '' si OK, mensaje de error si falla."""
    try:
        enviar_email_alerta(smtp_cfg, [email_prueba],
                            "Prueba de configuración",
                            "Este es un email de prueba del sistema de alertas.")
        return ""
    except Exception as exc:
        return str(exc)
