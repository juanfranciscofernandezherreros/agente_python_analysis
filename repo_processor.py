"""Procesamiento end-to-end de un repositorio/carpeta: clonado, checkout y ejecución del agente IA."""

import os
import sys
import shutil
import logging
import subprocess
from typing import Optional, Tuple

from config import DIR_JSON
from logging_utils import configurar_logger, registrar_fallo_json
from repo_resolver import resolver_nombre_y_ruta
from git_operations import _clonar_repositorio, _checkout_rama


def procesar_repo(url_o_ruta_completa: str, default_branch: Optional[str] = None,
                   existing_action: Optional[str] = None, cambios: Optional[str] = None) -> Tuple[str, str, str]:
    nombre_repo, url_o_ruta, carpeta_destino, rama_en_url = resolver_nombre_y_ruta(url_o_ruta_completa)
    rama = rama_en_url or default_branch
    ruta_trabajo = os.path.abspath(carpeta_destino)

    configurar_logger(nombre_repo)
    logging.info(f"--- INICIANDO PROCESO PARA EL REPOSITORIO: {nombre_repo} ---")
    logging.info(f"Ruta de origen: {url_o_ruta_completa}")
    logging.info(f"Carpeta de trabajo: {ruta_trabajo}")
    if rama:
        logging.info(f"Rama objetivo: {rama}")

    if url_o_ruta.startswith("http"):
        logging.info(f"Origen detectado: Repositorio remoto '{url_o_ruta}'.")
        if os.path.exists(carpeta_destino):
            respuesta = existing_action.lower() if existing_action else 'n'
            logging.info(f"Directorio '{carpeta_destino}' ya existe. Acción configurada: '{respuesta}'.")
            if respuesta == 's':
                logging.info(f"Eliminando directorio existente para sobrescribir: {carpeta_destino}")
                shutil.rmtree(carpeta_destino)
                _clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo)
            elif respuesta == 'c':  # 'c' para continuar, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente sin clonar de nuevo: {carpeta_destino}")
            else:  # 'n' para no, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente: {carpeta_destino}")
        else:
            _clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo)
    else:
        logging.info(f"Origen detectado: Carpeta local '{url_o_ruta}'.")
        if not os.path.exists(ruta_trabajo):
            error_msg = f"La carpeta local '{ruta_trabajo}' no existe."
            logging.error(error_msg)
            registrar_fallo_json(nombre_repo, url_o_ruta, "Verificación de Carpeta Local", ValueError(error_msg))
            raise ValueError(error_msg)

    if rama:
        directorio_git = carpeta_destino if url_o_ruta.startswith("http") else ruta_trabajo
        _checkout_rama(directorio_git, rama, nombre_repo, url_o_ruta)

    entorno_subproceso = os.environ.copy()
    entorno_subproceso["NOMBRE_MICROSERVICIO"] = nombre_repo
    entorno_subproceso["DIR_SALIDA_JSON"] = os.path.abspath(DIR_JSON)
    entorno_subproceso["PYTHONUNBUFFERED"] = "1"
    entorno_subproceso["PYTHONIOENCODING"] = "utf-8"
    logging.debug(f"Variables de entorno para subproceso: NOMBRE_MICROSERVICIO={nombre_repo}, DIR_SALIDA_JSON={entorno_subproceso['DIR_SALIDA_JSON']}")

    try:
        # Si el usuario eligió aplicar el JSON manualmente
        if cambios == "APLICAR_JSON_INTERACTIVO":
            ruta_json = os.path.join(DIR_JSON, f"{nombre_repo}_auditoria.json")
            if not os.path.exists(ruta_json):
                error_msg = f"No se encontró el archivo JSON de auditoría para '{nombre_repo}' en '{ruta_json}'. No se pueden aplicar los cambios."
                logging.error(error_msg)
                registrar_fallo_json(nombre_repo, url_o_ruta, "Aplicar JSON Interactivo", FileNotFoundError(error_msg))
                raise FileNotFoundError(error_msg)

            comando = [sys.executable, "aplicar_json.py", "--proyecto", ruta_trabajo, "--json", ruta_json]

            logging.info(f"Ejecutando aplicador interactivo de JSON para '{nombre_repo}'. Comando: {' '.join(comando)}")
            # Usamos subprocess.run normal para que el input() no se congele en segundo plano
            result = subprocess.run(comando, env=entorno_subproceso, check=False)  # check=False para que el orquestador no falle si el usuario cancela en aplicar_json.py

            if result.returncode != 0:
                logging.warning(f"El aplicador interactivo de JSON para '{nombre_repo}' terminó con código {result.returncode}. Puede que el usuario haya cancelado o hubo un error.")
            else:
                logging.info(f"Aplicador interactivo de JSON para '{nombre_repo}' finalizado.")

            logging.info(f"--- PROCESO PARA {nombre_repo} FINALIZADO CON ÉXITO ---")
            return nombre_repo, ruta_trabajo, url_o_ruta

        # Ejecución del agente IA
        comando = [sys.executable, "code_auditor_agent.py", ruta_trabajo]
        if cambios:
            comando.extend(["--cambios", cambios])
            logging.info(f"Instrucciones de cambios para la IA: '{cambios}'")

        logging.info(f"Ejecutando agente de auditoría/refactorización para '{nombre_repo}'. Comando: {' '.join(comando)}")
        with subprocess.Popen(
            comando,
            env=entorno_subproceso,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        ) as proc:

            for linea in proc.stdout:
                logging.info(f"[AGENTE] {linea.strip()}")

            proc.wait()

            if proc.returncode != 0:
                error_output = f"Agente terminó con código {proc.returncode}"
                logging.error(f"El agente para '{nombre_repo}' falló. Salida: {error_output}")
                raise subprocess.CalledProcessError(proc.returncode, comando, output=error_output)

        logging.info(f"--- PROCESO PARA {nombre_repo} FINALIZADO CON ÉXITO ---")
        return nombre_repo, ruta_trabajo, url_o_ruta
    except subprocess.CalledProcessError as e:
        logging.error(f"El subproceso del agente falló para {nombre_repo}. Código: {e.returncode}. Detalles: {e.output}")
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente", e)
        raise  # Re-raise para ser capturado por el executor
    except Exception as e:
        logging.error(f"Error inesperado durante el procesamiento del agente para {nombre_repo}: {e}", exc_info=True)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente (Excepción)", e)
        raise
