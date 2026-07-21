"""Ejecución de comandos externos y operaciones Git (clonado, checkout, verificación)."""

import sys
import time
import logging
import subprocess
from typing import List

from config import MAX_REINTENTOS_GIT
from logging_utils import registrar_fallo_json


def _run_external_command(cmd: List[str], cwd: str, error_stage: str,
                           nombre_repo: str, repo_url_o_ruta: str,
                           capture_output: bool = True, check: bool = True,
                           text: bool = True, encoding: str = 'utf-8') -> subprocess.CompletedProcess:
    """Wrapper para ejecutar comandos externos, centralizando el manejo de errores y logging."""
    cmd_str = ' '.join(cmd)
    logging.debug(f"Ejecutando comando: '{cmd_str}' en directorio '{cwd}' para '{nombre_repo}'.")
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=capture_output,
                                 check=check, text=text, encoding=encoding)
        logging.debug(f"Comando exitoso: '{cmd_str}'")
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Comando fallido en '{error_stage}' para '{nombre_repo}': '{cmd_str}'")
        logging.error(f"STDOUT: {e.stdout.strip()}")
        logging.error(f"STDERR: {e.stderr.strip()}")
        registrar_fallo_json(nombre_repo, repo_url_o_ruta, error_stage, e)
        raise  # Re-raise para propagar el error


def _clonar_repositorio(url: str, carpeta_destino: str, nombre_repo: str) -> None:
    """Clona con reintentos (fallos de red son habituales) y registra el fallo si se agotan."""
    ultimo_error = None
    for intento in range(1, MAX_REINTENTOS_GIT + 1):
        try:
            logging.info(f"Clonando repositorio '{url}' en '{carpeta_destino}' (Intento {intento}/{MAX_REINTENTOS_GIT})...")
            _run_external_command(["git", "clone", url, carpeta_destino], cwd=".", error_stage="Clonado del Repositorio", nombre_repo=nombre_repo, repo_url_o_ruta=url)
            logging.info(f"Clonado de '{url}' exitoso.")
            return
        except subprocess.CalledProcessError as e:
            ultimo_error = e
            logging.warning(f"Fallo al clonar '{url}' (intento {intento}/{MAX_REINTENTOS_GIT}). Error: {e.stderr.strip()}")
            if intento < MAX_REINTENTOS_GIT:
                logging.warning("Reintentando en 3s...")
                time.sleep(3)

    registrar_fallo_json(nombre_repo, url, "Clonado del Repositorio", ultimo_error)
    raise ultimo_error


def _checkout_rama(directorio_git: str, rama: str, nombre_repo: str, url_o_ruta: str) -> None:
    if rama.startswith("-"):
        error = ValueError(f"Nombre de rama no válido: '{rama}'")
        logging.error(f"Fallo al realizar checkout: {error}")
        registrar_fallo_json(nombre_repo, url_o_ruta, "Checkout de Rama", error)
        raise error
    try:
        logging.info(f"Realizando checkout a la rama '{rama}' en '{directorio_git}'...")
        _run_external_command(["git", "checkout", rama], cwd=directorio_git, error_stage="Checkout de Rama", nombre_repo=nombre_repo, repo_url_o_ruta=url_o_ruta)
        logging.info(f"Checkout a la rama '{rama}' exitoso.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Fallo al realizar checkout a la rama '{rama}': {e.stderr.strip()}")
        registrar_fallo_json(nombre_repo, url_o_ruta, "Checkout de Rama", e)
        raise


def check_git_installed() -> None:
    """Verifica si Git está instalado y accesible en el PATH."""
    try:
        _run_external_command(["git", "--version"], cwd=".", error_stage="Verificación de Git", nombre_repo="N/A", repo_url_o_ruta="N/A", capture_output=False)
        logging.info("✅ Git está instalado y accesible.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.critical("❌ Error: Git no está instalado o no está en el PATH.")
        logging.critical("   Por favor, instala Git para continuar. Saliendo.")
        sys.exit(1)
