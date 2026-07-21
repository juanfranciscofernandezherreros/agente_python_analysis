"""Gestión de la GEMINI_API_KEY: lectura, guardado y configuración forzada."""

import os
import logging
from typing import Optional

from config import ARCHIVO_ENV


def leer_key_de_env() -> Optional[str]:
    """Busca y devuelve la GEMINI_API_KEY dentro del archivo .env."""
    if not os.path.exists(ARCHIVO_ENV):
        logging.debug(f"Archivo .env no encontrado en '{ARCHIVO_ENV}'.")
        return None
    try:
        with open(ARCHIVO_ENV, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith("GEMINI_API_KEY="):
                    key = linea.strip().split("=", 1)[1]
                    logging.debug("API Key encontrada en .env.")
                    return key
    except Exception as e:
        logging.error(f"Error leyendo el archivo .env: {e}")
    return None


def guardar_key_en_env(key: str) -> None:
    """Guarda o actualiza la GEMINI_API_KEY en el archivo .env sin borrar otras variables."""
    lineas = []
    key_actualizada = False

    if os.path.exists(ARCHIVO_ENV):
        with open(ARCHIVO_ENV, "r", encoding="utf-8") as f:
            lineas = f.readlines()

    with open(ARCHIVO_ENV, "w", encoding="utf-8") as f:
        for linea in lineas:
            if linea.strip().startswith("GEMINI_API_KEY="):
                f.write(f"GEMINI_API_KEY={key}\n")
                key_actualizada = True
            else:
                f.write(linea)

        if not key_actualizada:
            f.write(f"GEMINI_API_KEY={key}\n")
    logging.info("API Key guardada/actualizada en el archivo .env.")


def forzar_configuracion_api_key(cli_key: Optional[str] = None, cambiar_key: bool = False) -> None:
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]
        logging.debug("Variable de entorno GOOGLE_API_KEY eliminada para evitar conflictos.")

    if cli_key:
        os.environ["GEMINI_API_KEY"] = cli_key
        logging.info("API Key de Gemini configurada desde la línea de comandos.")
        return

    if not cambiar_key:
        key_guardada = leer_key_de_env()
        if key_guardada:
            os.environ["GEMINI_API_KEY"] = key_guardada
            logging.info("API Key de Gemini cargada desde el archivo .env.")
            return

    logging.info("🔑 CONFIGURACIÓN DE CREDENCIAL GOOGLE GEMINI")
    key = input("👉 Introduce tu Gemini API Key: ").strip()

    if key:
        os.environ["GEMINI_API_KEY"] = key
        guardar_key_en_env(key)
        logging.info("✅ API Key guardada permanentemente en el archivo .env")
    else:
        logging.warning("⚠️ No se introdujo ninguna Key. El programa podría fallar si la IA es requerida.")
