# -*- coding: utf-8 -*-
"""
Gestión completa de fichajes desde el propio programa.
Permite:
  - Registrar entrada/salida desde el software (sin terminal físico)
  - Sincronizar empleados con el terminal ZKTeco (lectura + escritura)
  - Vista diaria y mensual de fichajes
  - Detección de retrasos y ausencias
  - Cálculo de horas trabajadas

Reutiliza: laboral.db_laboral.LaboralDB, laboral.fichajes.zkteco
"""
from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple

from core.logging_config import get_logger

log = get_logger("laboral.fichaje_directo")

_HORA_ENTRADA_NORMAL = "09:00"   # configurable vía BD config_ui
_JORNADA_HORAS       = 8         # horas de jornada completa


def _ahora_str() -> Tuple[str, str]:
    """Devuelve (fecha_iso, hora_hhmm) actuales."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M")


# ── Registro de fichaje desde programa ────────────────────────────────────────

def fichar_entrada(db_laboral, empleado_id: int,
                   hora: str = None, fecha: str = None) -> dict:
    """
    Registra la entrada de un empleado.
    Si ya existe fichaje de hoy sin salida, lo devuelve sin duplicar.
    """
    fecha_hoy, hora_now = _ahora_str()
    fecha = fecha or fecha_hoy
    hora  = hora  or hora_now

    # Comprobar si ya hay fichaje de entrada hoy
    fichajes = db_laboral.obtener_fichajes(
        empleado_id=empleado_id, fecha_desde=fecha, fecha_hasta=fecha)
    fichaje_hoy = next((f for f in fichajes), None)

    if fichaje_hoy and fichaje_hoy.get("hora_entrada"):
        log.info("Empleado %d ya tiene entrada registrada hoy: %s",
                 empleado_id, fichaje_hoy["hora_entrada"])
        return {"ok": False, "msg": "Ya existe entrada para hoy",
                "fichaje": fichaje_hoy}

    # Detectar retraso
    hora_normal = db_laboral._db.get_config_ui(
        "hora_entrada_normal", _HORA_ENTRADA_NORMAL)
    retraso = hora > hora_normal

    fid = db_laboral.insertar_fichaje({
        "empleado_id":  empleado_id,
        "fecha":        fecha,
        "hora_entrada": hora,
        "tipo":         "normal",
        "origen":       "manual",
        "observaciones": f"{'RETRASO' if retraso else ''}"
    })
    log.info("Entrada registrada: emp=%d fecha=%s hora=%s%s",
             empleado_id, fecha, hora, " [RETRASO]" if retraso else "")
    return {"ok": True, "fichaje_id": fid, "retraso": retraso,
            "hora": hora, "fecha": fecha}


def fichar_salida(db_laboral, empleado_id: int,
                  hora: str = None, fecha: str = None) -> dict:
    """
    Registra la salida de un empleado actualizando el fichaje de entrada del día.
    """
    fecha_hoy, hora_now = _ahora_str()
    fecha = fecha or fecha_hoy
    hora  = hora  or hora_now

    fichajes = db_laboral.obtener_fichajes(
        empleado_id=empleado_id, fecha_desde=fecha, fecha_hasta=fecha)
    fichaje = next((f for f in fichajes if f.get("hora_entrada")), None)

    if not fichaje:
        log.warning("No hay entrada registrada para emp=%d fecha=%s", empleado_id, fecha)
        return {"ok": False, "msg": "No hay entrada registrada hoy"}

    if fichaje.get("hora_salida"):
        log.info("Salida ya registrada: %s", fichaje["hora_salida"])
        return {"ok": False, "msg": "Salida ya registrada", "fichaje": fichaje}

    # Calcular minutos trabajados
    minutos = 0
    try:
        h1 = datetime.strptime(fichaje["hora_entrada"], "%H:%M")
        h2 = datetime.strptime(hora, "%H:%M")
        minutos = max(0, int((h2 - h1).total_seconds() / 60))
    except Exception:
        pass

    jornada_min = _JORNADA_HORAS * 60
    incompleta  = minutos < jornada_min * 0.9  # < 90% de la jornada

    db_laboral.cursor.execute("""
        UPDATE laboral_fichajes
        SET hora_salida=?, minutos_trabajados=?,
            observaciones=COALESCE(observaciones||' ','') || ?
        WHERE id=?
    """, (hora, minutos,
          "JORNADA_INCOMPLETA" if incompleta else "",
          fichaje["id"]))
    db_laboral.conn.commit()

    log.info("Salida registrada: emp=%d fecha=%s hora=%s minutos=%d",
             empleado_id, fecha, hora, minutos)
    return {"ok": True, "fichaje_id": fichaje["id"],
            "minutos": minutos, "hora": hora,
            "jornada_incompleta": incompleta}


# ── Sincronización de empleados con ZKTeco ────────────────────────────────────

def sincronizar_empleados_zkteco(db_laboral,
                                  ip: str, puerto: int = 4370) -> dict:
    """
    Descarga la lista de empleados del terminal ZKTeco y la compara
    con la BD. Detecta empleados en el terminal que no están en BD y viceversa.
    Requiere: pip install pyzk
    """
    try:
        from zk import ZK
    except ImportError:
        return {"error": "pyzk no instalado. Instalar con: pip install pyzk"}

    resultado = {"en_terminal": 0, "en_bd": 0, "nuevos_bd": 0,
                 "no_en_terminal": 0, "detalles": []}
    try:
        zk = ZK(ip, port=puerto, timeout=10)
        conn = zk.connect()
        usuarios_zk = conn.get_users()
        conn.disconnect()

        empleados_bd = {
            f"{e['nombre']} {e['apellidos']}".upper(): e
            for e in db_laboral.obtener_empleados()
        }
        resultado["en_terminal"] = len(usuarios_zk)
        resultado["en_bd"]       = len(empleados_bd)

        for uz in usuarios_zk:
            nombre_zk = (uz.name or "").upper().strip()
            if nombre_zk not in empleados_bd:
                # Empleado en terminal pero no en BD → sugerir alta
                resultado["detalles"].append({
                    "accion": "no_en_bd",
                    "nombre": uz.name,
                    "uid_zk": uz.uid,
                })
                resultado["nuevos_bd"] += 1
            else:
                resultado["detalles"].append({
                    "accion": "sincronizado",
                    "nombre": uz.name,
                    "uid_zk": uz.uid,
                    "emp_id": empleados_bd[nombre_zk]["id"],
                })

        # Empleados en BD que no están en terminal
        nombres_zk_set = {(uz.name or "").upper() for uz in usuarios_zk}
        for nombre_bd, emp in empleados_bd.items():
            if nombre_bd not in nombres_zk_set and emp.get("estado") == "activo":
                resultado["detalles"].append({
                    "accion": "no_en_terminal",
                    "nombre": nombre_bd,
                    "emp_id": emp["id"],
                })
                resultado["no_en_terminal"] += 1

        log.info("Sync ZKTeco: %d en terminal, %d en BD, %d nuevos, %d sin terminal",
                 resultado["en_terminal"], resultado["en_bd"],
                 resultado["nuevos_bd"], resultado["no_en_terminal"])
        return resultado
    except Exception as e:
        log.error("Error sincronizando con ZKTeco: %s", e)
        return {"error": str(e)}


def alta_empleado_en_zkteco(db_laboral, empleado_id: int,
                              ip: str, puerto: int = 4370) -> dict:
    """Da de alta un empleado de la BD en el terminal ZKTeco."""
    try:
        from zk import ZK, const
    except ImportError:
        return {"error": "pyzk no instalado"}

    emp = db_laboral.obtener_empleado(empleado_id)
    if not emp:
        return {"error": "Empleado no encontrado"}

    nombre = f"{emp.get('nombre','')} {emp.get('apellidos','')}".strip()[:24]
    try:
        zk   = ZK(ip, port=puerto, timeout=10)
        conn = zk.connect()
        usuarios = conn.get_users()
        uid_max  = max((u.uid for u in usuarios), default=0) + 1
        conn.set_user(uid=uid_max, name=nombre, privilege=const.USER_DEFAULT,
                      user_id=str(empleado_id))
        conn.disconnect()
        log.info("Empleado dado de alta en ZKTeco: %s (uid=%d)", nombre, uid_max)
        return {"ok": True, "uid": uid_max, "nombre": nombre}
    except Exception as e:
        log.error("Error dando de alta en ZKTeco: %s", e)
        return {"error": str(e)}


# ── Análisis de fichajes: retrasos, ausencias, horas ─────────────────────────

def analizar_mes(db_laboral, empleado_id: int,
                 anio: int, mes: int) -> dict:
    """
    Análisis completo de un mes para un empleado.
    Detecta: días trabajados, horas, retrasos, ausencias, incompletas.
    """
    from calendar import monthrange
    _, dias_mes = monthrange(anio, mes)
    fecha_desde = f"{anio}-{mes:02d}-01"
    fecha_hasta = f"{anio}-{mes:02d}-{dias_mes}"

    fichajes = db_laboral.obtener_fichajes(
        empleado_id=empleado_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    # Calcular días laborables (lunes-viernes) del mes
    dias_laborables = sum(
        1 for d in range(1, dias_mes + 1)
        if date(anio, mes, d).weekday() < 5
    )

    fichajes_por_dia = {f["fecha"]: f for f in fichajes}
    retrasos = 0
    ausencias = 0
    incompletas = 0
    total_minutos = 0
    hora_normal = db_laboral._db.get_config_ui(
        "hora_entrada_normal", _HORA_ENTRADA_NORMAL)

    for d in range(1, dias_mes + 1):
        fecha_d = f"{anio}-{mes:02d}-{d:02d}"
        if date(anio, mes, d).weekday() >= 5:
            continue  # fin de semana
        f = fichajes_por_dia.get(fecha_d)
        if not f:
            ausencias += 1
        else:
            if f.get("hora_entrada") and f["hora_entrada"] > hora_normal:
                retrasos += 1
            mins = f.get("minutos_trabajados") or 0
            total_minutos += mins
            if mins > 0 and mins < _JORNADA_HORAS * 60 * 0.9:
                incompletas += 1

    emp = db_laboral.obtener_empleado(empleado_id)
    return {
        "empleado":        f"{emp.get('nombre','')} {emp.get('apellidos','')}",
        "periodo":         f"{mes:02d}/{anio}",
        "dias_laborables": dias_laborables,
        "dias_trabajados": len(fichajes_por_dia),
        "ausencias":       ausencias,
        "retrasos":        retrasos,
        "jornadas_incompletas": incompletas,
        "horas_trabajadas": round(total_minutos / 60, 2),
        "horas_esperadas":  dias_laborables * _JORNADA_HORAS,
        "diferencia_horas": round(total_minutos / 60 - dias_laborables * _JORNADA_HORAS, 2),
        "detalle":          fichajes,
    }


def vista_diaria(db_laboral, fecha: str = None) -> List[dict]:
    """
    Devuelve el estado de fichaje de todos los empleados activos para una fecha.
    Útil para la vista "hoy" del panel de fichajes.
    """
    fecha = fecha or date.today().isoformat()
    empleados = db_laboral.obtener_empleados(solo_activos=True)
    fichajes  = db_laboral.obtener_fichajes(fecha_desde=fecha, fecha_hasta=fecha)
    fich_map  = {f["empleado_id"]: f for f in fichajes}

    resultado = []
    for emp in empleados:
        f = fich_map.get(emp["id"])
        resultado.append({
            "empleado_id":   emp["id"],
            "nombre":        f"{emp['nombre']} {emp['apellidos']}",
            "entrada":       f.get("hora_entrada", "") if f else "",
            "salida":        f.get("hora_salida", "")  if f else "",
            "minutos":       f.get("minutos_trabajados", 0) if f else 0,
            "estado":        ("ausente" if not f else
                             "trabajando" if not f.get("hora_salida") else "completado"),
        })
    return resultado
