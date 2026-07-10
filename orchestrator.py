import subprocess
import sys
import os
import shutil
import json
import traceback
import logging
import time
from datetime import datetime
from typing import Optional, List, Tuple
import warnings
import argparse
import concurrent.futures

warnings.filterwarnings("ignore", category=FutureWarning)

# Importar módulos refactorizados
import orchestrator_ui
import orchestrator_git
import orchestrator_patching

DIR_LOGS = "logs"
DIR_JSON = "json_output"
DIR_HTML = "html_output"
DIR_MICROSERVICES = "microservices"
ARCHIVO_ENV = ".env"
MAX_REINTENTOS_GIT = 2


# ============================================================
# ENTORNO / LOGGING
# ============================================================

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


def configurar_logger(nombre_repo: str) -> None:
    """Asigna un archivo de log específico para el microservicio actual y lo pinta en consola.

    Cierra correctamente los handlers previos antes de quitarlos para no
    dejar descriptores de fichero abiertos (importante sobre todo en Windows,
    donde un handler sin cerrar bloquea el fichero .log).
    """
    logger = logging.getLogger()
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
    except Exception as e:
        logging.error(f"Fallo crítico al escribir en el JSON: {e}", exc_info=True)


# ============================================================
# GESTIÓN DE LA API KEY
# ============================================================

def leer_key_de_env() -> Optional[str]:
    """Busca y devuelve la GEMINI_API_KEY dentro del archivo .env."""
    if not os.path.exists(ARCHIVO_ENV):
        return None
    try:
        with open(ARCHIVO_ENV, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip().startswith("GEMINI_API_KEY="):
                    return linea.strip().split("=", 1)[1]
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


def forzar_configuracion_api_key(cli_key: Optional[str] = None, cambiar_key: bool = False) -> None:
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]

    if cli_key:
        os.environ["GEMINI_API_KEY"] = cli_key
        return

    if not cambiar_key:
        key_guardada = leer_key_de_env()
        if key_guardada:
            os.environ["GEMINI_API_KEY"] = key_guardada
            return

    print("\n🔑 CONFIGURACIÓN DE CREDENCIAL GOOGLE GEMINI")
    key = input("👉 Introduce tu Gemini API Key: ").strip()

    if key:
        os.environ["GEMINI_API_KEY"] = key
        guardar_key_en_env(key)
        print("✅ API Key guardada permanentemente en el archivo .env")
    else:
        print("⚠️ No se introdujo ninguna Key. El programa podría fallar si la IA es requerida.")


# ============================================================
# RESOLUCIÓN DE NOMBRE/RUTA DE REPO (compartido)
# ============================================================

def sanitizar_nombre_repo(nombre: str) -> str:
    """Evita que un nombre de repo con '..' o separadores de ruta escape del directorio destino."""
    nombre = nombre.strip().replace("\\", "/").split("/")[-1]
    nombre = nombre.replace("..", "_").strip() or "repo_sin_nombre"
    return nombre


def resolver_nombre_y_ruta(url_o_ruta_completa: str) -> Tuple[str, str, str, Optional[str]]:
    """Dado 'repo#rama' o una ruta local, devuelve:
    (nombre_repo, url_o_ruta_sin_rama, carpeta_destino, rama)
    """
    if "#" in url_o_ruta_completa:
        url_o_ruta, rama = url_o_ruta_completa.split("#", 1)
    else:
        url_o_ruta, rama = url_o_ruta_completa, None

    if url_o_ruta.startswith("http"):
        nombre_repo = sanitizar_nombre_repo(url_o_ruta.split("/")[-1].replace(".git", ""))
        carpeta_destino = os.path.join(DIR_MICROSERVICES, nombre_repo)
    else:
        nombre_repo = sanitizar_nombre_repo(os.path.basename(os.path.normpath(url_o_ruta)))
        carpeta_destino = url_o_ruta

    return nombre_repo, url_o_ruta, carpeta_destino, (rama or None)


# ============================================================
# PROCESAMIENTO DE REPOSITORIOS
# ============================================================

def procesar_repo(url_o_ruta_completa: str, default_branch: Optional[str] = None,
                   existing_action: Optional[str] = None, cambios: Optional[str] = None) -> Tuple[str, str, str]:
    nombre_repo, url_o_ruta, carpeta_destino, rama_en_url = resolver_nombre_y_ruta(url_o_ruta_completa)
    rama = rama_en_url or default_branch
    ruta_trabajo = os.path.abspath(carpeta_destino)

    configurar_logger(nombre_repo)
    logging.info(f"--- INICIANDO PROCESO PARA EL REPOSITORIO: {nombre_repo} ---")
    logging.info(f"Ruta de origen: {url_o_ruta_completa}")
    logging.info(f"Carpeta de trabajo: {ruta_trabajo}")

    if url_o_ruta.startswith("http"):
        if os.path.exists(carpeta_destino):
            respuesta = existing_action.lower() if existing_action else 'n'
            if respuesta == 's':
                logging.info(f"Eliminando directorio existente: {carpeta_destino}")
                shutil.rmtree(carpeta_destino)
                orchestrator_git._clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo, MAX_REINTENTOS_GIT, registrar_fallo_json)
            elif respuesta == 'c': # 'c' para continuar, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente: {carpeta_destino}")
            else: # 'n' para no, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente: {carpeta_destino}")
        else:
            orchestrator_git._clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo, MAX_REINTENTOS_GIT, registrar_fallo_json)

    if rama:
        directorio_git = carpeta_destino if url_o_ruta.startswith("http") else ruta_trabajo
        orchestrator_git._checkout_rama(directorio_git, rama, nombre_repo, url_o_ruta, registrar_fallo_json)

    entorno_subproceso = os.environ.copy()
    entorno_subproceso["NOMBRE_MICROSERVICIO"] = nombre_repo
    entorno_subproceso["DIR_SALIDA_JSON"] = os.path.abspath(DIR_JSON)
    entorno_subproceso["PYTHONUNBUFFERED"] = "1"
    entorno_subproceso["PYTHONIOENCODING"] = "utf-8"

    try:
        comando = [sys.executable, "code_auditor_agent.py", ruta_trabajo]
        if cambios:
            comando.extend(["--cambios", cambios])

        logging.info(f"Ejecutando agente: {' '.join(comando)}")
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
                raise subprocess.CalledProcessError(proc.returncode, comando, output=f"Agente terminó con código {proc.returncode}")

        logging.info(f"--- PROCESO PARA {nombre_repo} FINALIZADO CON ÉXITO ---")
        return nombre_repo, ruta_trabajo, url_o_ruta # Retorna url_o_ruta para aplicar parches
    except subprocess.CalledProcessError as e:
        logging.error(f"El subproceso del agente falló para {nombre_repo}. Código: {e.returncode}")
        logging.error(f"Salida del agente: {e.output}")
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente", e)
        raise # Re-raise para ser capturado por el executor
    except Exception as e:
        logging.error(f"Error inesperado durante el procesamiento del agente para {nombre_repo}: {e}", exc_info=True)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente (Excepción)", e)
        raise


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    orchestrator_git._check_git_installed() # Verificar Git al inicio

    parser = argparse.ArgumentParser(description="Orquestador de auditoría y refactorización de microservicios.")
    parser.add_argument("repos", nargs="*", help="URLs de repositorios Git o rutas de carpetas locales a procesar.")
    parser.add_argument("-k", "--api-key", type=str, help="Gemini API Key (sobrescribe .env).")
    parser.add_argument("-b", "--branch", type=str, help="Rama Git a clonar/checkout (por defecto si no se especifica en la URL).")
    parser.add_argument("-e", "--existing", choices=['s', 'n', 'c'],
                        help="Acción para repositorios existentes: 's' (sobrescribir), 'n' (no clonar de nuevo), 'c' (continuar sin clonar).")
    parser.add_argument("-c", "--cambios", type=str, help="Instrucciones de cambios específicos para la IA.")
    parser.add_argument("--no-clear", action="store_true", help="No limpiar la pantalla al iniciar.")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="Número de repositorios a procesar en paralelo (por defecto: 1).")
    args = parser.parse_args()

    preparar_entorno(limpiar_pantalla=not args.no_clear)
    forzar_configuracion_api_key(cli_key=args.api_key)

    repos_a_procesar = args.repos
    cambios_a_enviar = args.cambios

    if not repos_a_procesar:
        resultado_interactivo = orchestrator_ui.obtener_repositorios_interactivo(forzar_configuracion_api_key)
        if not resultado_interactivo:
            sys.exit(0)

        repos_a_procesar, cambios_interactivos = resultado_interactivo
        if cambios_interactivos:
            cambios_a_enviar = cambios_interactivos

    elif args.repos and not args.cambios:
        print("\n----------------------------------------------------")
        opcion_cambios = input("👉 ¿Qué cambios quieres implementar o auditar? (Enter para omitir): ").strip()
        if opcion_cambios:
            cambios_a_enviar = opcion_cambios

    processed_repos_info = [] # List of (nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama)

    if args.jobs > 1 and len(repos_a_procesar) > 1:
        print(f"\n⚙️  Procesando {len(repos_a_procesar)} repositorios en paralelo con {args.jobs} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            future_to_repo = {executor.submit(procesar_repo, repo, args.branch, args.existing, cambios_a_enviar): repo for repo in repos_a_procesar}
            for future in concurrent.futures.as_completed(future_to_repo):
                repo_url_o_ruta_completa_original = future_to_repo[future]
                nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo_url_o_ruta_completa_original) # Para logging de errores
                try:
                    nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = future.result()
                    processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
                    print(f"✅ [Paralelo] Repositorio '{nombre_repo}' procesado con éxito.")
                except KeyboardInterrupt:
                    print(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo_url_o_ruta_completa_original}'.")
                    registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                    executor.shutdown(wait=False, cancel_futures=True) # Detener otras tareas
                    break # Salir del bucle
                except Exception as e:
                    print(f"\n❌ [Paralelo] Error fatal procesando '{repo_url_o_ruta_completa_original}': {e}")
                    print(f"   Revisa la carpeta de logs/ y {DIR_JSON}/{nombre_repo_temp}_fallo.json")
    else:
        for repo in repos_a_procesar:
            nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo) # Para logging de errores
            try:
                nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = procesar_repo(repo, default_branch=args.branch, existing_action=args.existing, cambios=cambios_a_enviar)
                processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
            except KeyboardInterrupt:
                print(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo}'.")
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                break
            except Exception as e:
                print(f"\n❌ Error fatal en {repo}: {e}")
                print(f"   Revisa la carpeta de logs/ y {DIR_JSON}/{nombre_repo_temp}_fallo.json")

    # Fase de post-procesamiento: Aplicar mejoras interactivas secuencialmente
    print("\n====================================================")
    print("✨ APLICACIÓN INTERACTIVA DE MEJORAS (POST-PROCESO)")
    print("====================================================")
    for nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama in processed_repos_info:
        try:
            orchestrator_patching.aplicar_mejoras_interactivas(
                nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama, DIR_JSON,
                orchestrator_ui._exportar_cambios_disponibles,
                orchestrator_ui._pedir_seleccion_usuario,
                orchestrator_git.gestionar_cambios_git,
                registrar_fallo_json
            )
        except KeyboardInterrupt:
            print(f"\n⏹️  Cancelado por el usuario mientras se aplicaban mejoras a '{nombre_repo}'.")
            registrar_fallo_json(nombre_repo, url_o_ruta_sin_rama, "Interrupción Manual (Aplicar Mejoras)", "Cancelado por el usuario (Ctrl+C)")
            break
        except Exception as e:
            print(f"\n❌ Error fatal aplicando mejoras a {nombre_repo}: {e}")
            print(f"   Revisa la carpeta de logs/ y {DIR_JSON}/{nombre_repo}_fallo.json")
            registrar_fallo_json(nombre_repo, url_o_ruta_sin_rama, "Aplicación de Mejoras", e)

    print("\n🏁 PROCESAMIENTO FINALIZADO.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️  Ejecución interrumpida por el usuario.")
        sys.exit(1)