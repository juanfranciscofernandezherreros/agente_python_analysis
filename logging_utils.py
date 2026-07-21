"""Preparación del entorno de trabajo, configuración de logging y registro de fallos."""

import os
import sys
import json
import logging
import traceback
import subprocess
from datetime import datetime

from config import DIR_LOGS, DIR_JSON, DIR_HTML, DIR_MICROSERVICES


def preparar_entorno(limpiar_pantalla: bool = True) -> None:
    """Crea los directorios de salida y contenedor si no existen.

    La limpieza de pantalla solo se hace si estamos en una terminal
    interactiva (evita borrar logs útiles cuando se ejecuta en CI/servidor
    con salida redirigida a un fichero).
    """
    if limpiar_pantalla and sys.stdout.isatty():
        os.system('cls' if os.name == 'nt' else 'clear')
    for directorio in [DIR_LOGS, DIR_JSON, DIR_HTML, DIR_MICROSERVICES]:
        os.makedirs(directorio, exist_ok=True)
    logging.info(f"Directorios de trabajo creados/verificados: {', '.join([DIR_LOGS, DIR_JSON, DIR_HTML, DIR_MICROSERVICES])}")


def configurar_logger(nombre_repo: str) -> None:
    """Asigna un archivo de log específico para el microservicio actual y lo pinta en consola.

    Cierra correctamente los handlers previos antes de quitarlos para no
    dejar descriptores de fichero abiertos (importante sobre todo en Windows,
    donde un handler sin cerrar bloquea el fichero .log).
    """
    logger = logging.getLogger()
    # Ensure logger is not re-configured if already set for this repo
    if any(isinstance(h, logging.FileHandler) and h.baseFilename.endswith(f"{nombre_repo}.log") for h in logger.handlers):
        return

    logger.setLevel(logging.INFO)
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    archivo_log = os.path.join(DIR_LOGS, f"{nombre_repo}.log")

    file_handler = logging.FileHandler(archivo_log, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logging.info(f"Logger configurado para '{nombre_repo}'. Los logs se guardarán en '{archivo_log}'.")


def registrar_fallo_json(nombre_repo: str, repo_url_o_ruta: str, etapa: str, excepcion) -> None:
    """Registra cualquier fallo del pipeline (clonado, checkout, ejecución del agente...) en un JSON."""
    archivo_json = os.path.join(DIR_JSON, f"{nombre_repo}_fallo.json")
    if isinstance(excepcion, Exception):
        tb_str = "".join(traceback.format_exception(type(excepcion), excepcion, excepcion.__traceback__))
        tipo_excepcion = type(excepcion).__name__
        mensaje = str(excepcion)
        # Si es un error de subprocess, añadimos stderr/stdout capturado (más útil que el traceback de Python)
        if isinstance(excepcion, subprocess.CalledProcessError):
            detalle_proc = excepcion.stderr or excepcion.stdout or ""
            if detalle_proc:
                mensaje = f"{mensaje} | Detalle: {detalle_proc.strip()}"
    else:
        tb_str = "N/A"
        tipo_excepcion = "InterrupcionManual"
        mensaje = str(excepcion)

    fallo = {
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "microservicio": nombre_repo,
        "ruta_origen": repo_url_o_ruta,
        "etapa_fallida": etapa,
        "detalles_error": {"tipo": tipo_excepcion, "mensaje": mensaje, "traceback": tb_str}
    }
    try:
        with open(archivo_json, "w", encoding="utf-8") as f:
            json.dump([fallo], f, indent=4, ensure_ascii=False)
        logging.error(f"Fallo registrado en JSON para '{nombre_repo}' en etapa '{etapa}'. Ver: {archivo_json}")
    except Exception as e:
        logging.critical(f"Fallo crítico al escribir el JSON de error para '{nombre_repo}': {e}", exc_info=True)
