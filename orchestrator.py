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


# ============================================================
# GESTIÓN DE LA API KEY
# ============================================================

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


# ============================================================
# SELECCIÓN INTERACTIVA DE ENTRADA
# ============================================================

def seleccionar_con_tkinter() -> Optional[str]:
    """Abre un diálogo visual forzando que empiece en la carpeta de microservicios."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        import os
    except ImportError:
        logging.error("❌ Error: Falla al cargar la interfaz gráfica (tkinter no disponible). Asegúrate de que tkinter esté instalado.")
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()

        logging.info("🔍 Abriendo explorador de archivos para selección de carpeta...")
        
        # Forzamos a Tkinter a abrir siempre dentro de tu carpeta de proyectos
        ruta_inicial = os.path.abspath(DIR_MICROSERVICES)
        os.makedirs(ruta_inicial, exist_ok=True)

        ruta = filedialog.askdirectory(
            title="📂 ENTRA AQUÍ Y SELECCIONA EL MICROSERVICIO",
            initialdir=ruta_inicial  # <--- ESTO EVITA QUE SELECCIONE LA RAÍZ
        )

        root.destroy()
        if ruta:
            logging.info(f"Carpeta seleccionada vía Tkinter: {ruta}")
        else:
            logging.info("Selección de carpeta cancelada por el usuario.")
        return ruta or None
    except Exception as e:
        logging.error(f"❌ Error inesperado abriendo el explorador de archivos: {e}", exc_info=True)
        return None

def obtener_repositorios_interactivo() -> Optional[Tuple[List[str], Optional[str]]]:
    while True:
        print("\n----------------------------------------------------")
        print("📥 SELECCIÓN DE ENTRADA (MODO VISUAL) 🚀")
        print("----------------------------------------------------")
        print("1. Analizar una carpeta local (Abre ventana Tkinter) 📂")
        print("2. Analizar un repositorio remoto (Git URL) 🌐")
        print("3. Cambiar / Reemplazar la Gemini API Key actual 🔑")

        opcion = input("\n👉 Elige una opción (1, 2 o 3): ").strip()
        logging.debug(f"Usuario seleccionó opción principal: {opcion}")

        if opcion == "3":
            forzar_configuracion_api_key(cambiar_key=True)
            continue

        ruta_final = None

        if opcion == "1":
            ruta = seleccionar_con_tkinter()
            if not ruta:
                logging.info("⏭️ Cancelaste la selección de carpeta.")
                continue
            logging.info(f"✅ Carpeta seleccionada: {ruta}")
            ruta_final = ruta

        elif opcion == "2":
            url = input("👉 Introduce la URL del repositorio Git: ").strip()
            if not url:
                logging.info("⏭️ Cancelaste la introducción de la URL del repositorio.")
                continue
            rama = input("👉 ¿Qué rama deseas clonar? (Enter para la por defecto): ").strip()
            if rama and rama.startswith("-"):
                logging.error("❌ Nombre de rama no válido (no puede empezar por '-'). Operación cancelada.")
                continue
            logging.info(f"✅ Repositorio Git seleccionado: {url}")
            ruta_final = f"{url}#{rama}" if rama else url

        else:
            logging.warning("❌ Opción no válida. Inténtalo de nuevo.")
            continue

        if ruta_final:
            while True:
                print("\n----------------------------------------------------")
                print("🛠️  ¿QUÉ DESEAS HACER CON ESTE DIRECTORIO/REPOSITORIO?")
                print("----------------------------------------------------")
                print("1. 🕵️  Auditoría general (Buscar bugs y vulnerabilidades)")
                print("2. ✨ Implementar un cambio o mejora específica")
                print("3. 📥 Aplicar cambios desde un JSON existente (Interactivo)")
                print("4. 🔙 Cancelar y elegir otra ruta")

                sub_opcion = input("\n👉 Elige una acción (1, 2, 3 o 4): ").strip()
                logging.debug(f"Usuario seleccionó sub-opción: {sub_opcion}")

                if sub_opcion == "1":
                    return [ruta_final], None
                elif sub_opcion == "2":
                    cambios = input("\n📝 Describe qué cambio quieres que haga la IA (ej. 'Añadir logs', 'Optimizar imports'):\n👉 ").strip()
                    logging.info(f"Cambio solicitado por el usuario: '{cambios}'")
                    return [ruta_final], cambios if cambios else None
                elif sub_opcion == "3":
                    logging.info("Modo 'Aplicar cambios desde JSON existente' seleccionado.")
                    return [ruta_final], "APLICAR_JSON_INTERACTIVO"
                elif sub_opcion == "4":
                    logging.info("🔙 Volviendo al menú principal por solicitud del usuario.")
                    break
                else:
                    logging.warning("❌ Opción no válida. Inténtalo de nuevo.")


# ============================================================
# RESOLUCIÓN DE NOMBRE/RUTA DE REPO (compartido)
# ============================================================

def sanitizar_nombre_repo(nombre: str) -> str:
    """Evita que un nombre de repo con '..' o separadores de ruta escape del directorio destino."""
    nombre = nombre.strip().replace("\\", "/").split("/")[-1]
    nombre = nombre.replace("..", "_").strip() or "repo_sin_nombre"
    logging.debug(f"Nombre de repositorio sanitizado a: '{nombre}'")
    return nombre


def resolver_nombre_y_ruta(url_o_ruta_completa: str) -> Tuple[str, str, str, Optional[str]]:
    """Dado 'repo#rama' o una ruta local, devuelve:
    (nombre_repo, url_o_ruta_sin_rama, carpeta_destino, rama)
    """
    if "#" in url_o_ruta_completa:
        url_o_ruta, rama = url_o_ruta_completa.split("#", 1)
        logging.debug(f"URL/Ruta '{url_o_ruta_completa}' contiene rama: '{rama}'")
    else:
        url_o_ruta, rama = url_o_ruta_completa, None
        logging.debug(f"URL/Ruta '{url_o_ruta_completa}' no contiene rama explícita.")

    if url_o_ruta.startswith("http"):
        nombre_repo = sanitizar_nombre_repo(url_o_ruta.split("/")[-1].replace(".git", ""))
        carpeta_destino = os.path.join(DIR_MICROSERVICES, nombre_repo)
        logging.debug(f"Origen remoto: '{url_o_ruta}', Nombre: '{nombre_repo}', Destino: '{carpeta_destino}'")
    else:
        nombre_repo = sanitizar_nombre_repo(os.path.basename(os.path.normpath(url_o_ruta)))
        carpeta_destino = url_o_ruta
        logging.debug(f"Origen local: '{url_o_ruta}', Nombre: '{nombre_repo}', Destino: '{carpeta_destino}'")

    return nombre_repo, url_o_ruta, carpeta_destino, (rama or None)


# ============================================================
# EJECUCIÓN DE COMANDOS EXTERNOS
# ============================================================

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
        raise # Re-raise para propagar el error


# ============================================================
# OPERACIONES GIT DE ENTRADA (clonado/checkout) CON TRAZABILIDAD DE FALLOS
# ============================================================

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
            elif respuesta == 'c': # 'c' para continuar, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente sin clonar de nuevo: {carpeta_destino}")
            else: # 'n' para no, no clonar de nuevo
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
        # NUEVA LÓGICA: Si el usuario eligió aplicar el JSON manualmente
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
            result = subprocess.run(comando, env=entorno_subproceso, check=False) # check=False para que el orquestador no falle si el usuario cancela en aplicar_json.py
            
            if result.returncode != 0:
                logging.warning(f"El aplicador interactivo de JSON para '{nombre_repo}' terminó con código {result.returncode}. Puede que el usuario haya cancelado o hubo un error.")
            else:
                logging.info(f"Aplicador interactivo de JSON para '{nombre_repo}' finalizado.")
            
            logging.info(f"--- PROCESO PARA {nombre_repo} FINALIZADO CON ÉXITO ---")
            return nombre_repo, ruta_trabajo, url_o_ruta

        # LÓGICA ANTERIOR: Ejecución del agente IA
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
        raise # Re-raise para ser capturado por el executor
    except Exception as e:
        logging.error(f"Error inesperado durante el procesamiento del agente para {nombre_repo}: {e}", exc_info=True)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente (Excepción)", e)
        raise

def _check_git_installed() -> None:
    """Verifica si Git está instalado y accesible en el PATH."""
    try:
        _run_external_command(["git", "--version"], cwd=".", error_stage="Verificación de Git", nombre_repo="N/A", repo_url_o_ruta="N/A", capture_output=False)
        logging.info("✅ Git está instalado y accesible.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.critical("❌ Error: Git no está instalado o no está en el PATH.")
        logging.critical("   Por favor, instala Git para continuar. Saliendo.")
        sys.exit(1)


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logging.info("Iniciando orquestador principal...")

    _check_git_installed() # Verificar Git al inicio

    parser = argparse.ArgumentParser(description="Orquestador de auditoría y refactorización de microservicios.")
    parser.add_argument("repos", nargs="*", help="URLs de repositorios Git o rutas de carpetas locales a procesar.")
    parser.add_argument("-k", "--api-key", type=str, help="Gemini API Key (sobrescribe .env).")
    parser.add_argument("-b", "--branch", type=str, help="Rama Git a clonar/checkout (por defecto si no se especifica en la URL).")
    parser.add_argument("-e", "--existing", choices=['s', 'n', 'c'],
                        help="Acción para repositorios existentes: 's' (sobrescribir), 'n' (no clonar de nuevo), 'c' (continuar sin clonar).")
    parser.add_argument("-c", "--cambios", type=str, help="Instrucciones de cambios específicos para la IA.")
    parser.add_argument("--no-clear", action="store_true", help="No limpiar la pantalla al iniciar.")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="Número de repositorios a procesar en paralelo (por defecto: 1).") # Nuevo argumento para concurrencia
    args = parser.parse_args()

    preparar_entorno(limpiar_pantalla=not args.no_clear)
    forzar_configuracion_api_key(cli_key=args.api_key)
    if not os.environ.get("GEMINI_API_KEY"):
        logging.error("No se ha configurado la Gemini API Key. Las operaciones de IA no podrán realizarse. Saliendo.")
        sys.exit(1)
    logging.info("Gemini API Key configurada y validada.")


    repos_a_procesar = args.repos
    cambios_a_enviar = args.cambios

    if not repos_a_procesar:
        logging.info("Modo interactivo activado. Esperando selección del usuario.")
        resultado_interactivo = obtener_repositorios_interactivo()
        if not resultado_interactivo:
            logging.info("Selección de repositorio cancelada por el usuario. Saliendo.")
            sys.exit(0)

        repos_a_procesar, cambios_interactivos = resultado_interactivo
        if cambios_interactivos:
            cambios_a_enviar = cambios_interactivos

    elif args.repos and not args.cambios:
        print("\n----------------------------------------------------")
        opcion_cambios = input("👉 ¿Qué cambios quieres implementar o auditar? (Enter para omitir): ").strip()
        if opcion_cambios:
            cambios_a_enviar = opcion_cambios
            logging.info(f"Cambios solicitados por CLI interactivo: '{cambios_a_enviar}'")
        else:
            logging.info("No se especificaron cambios adicionales para la auditoría.")

    # Lista para almacenar información de los repositorios procesados exitosamente
    processed_repos_info = [] # List of (nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama)

    if args.jobs > 1 and len(repos_a_procesar) > 1:
        logging.info(f"⚙️  Procesando {len(repos_a_procesar)} repositorios en paralelo con {args.jobs} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            future_to_repo = {executor.submit(procesar_repo, repo, args.branch, args.existing, cambios_a_enviar): repo for repo in repos_a_procesar}
            for future in concurrent.futures.as_completed(future_to_repo):
                repo_url_o_ruta_completa_original = future_to_repo[future]
                nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo_url_o_ruta_completa_original) # Para logging de errores
                try:
                    nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = future.result()
                    processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
                    logging.info(f"✅ [Paralelo] Repositorio '{nombre_repo}' procesado con éxito.")
                except KeyboardInterrupt:
                    logging.warning(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo_url_o_ruta_completa_original}'.")
                    registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                    executor.shutdown(wait=False, cancel_futures=True) # Detener otras tareas
                    break # Salir del bucle
                except Exception as e:
                    # El error ya fue registrado por procesar_repo o _run_external_command
                    logging.error(f"\n❌ [Paralelo] Error fatal procesando '{repo_url_o_ruta_completa_original}': {e}")
                    logging.error(f"   Revisa la carpeta de logs/ y {DIR_JSON}/{nombre_repo_temp}_fallo.json para más detalles.")
    else:
        logging.info(f"⚙️  Procesando {len(repos_a_procesar)} repositorios en modo secuencial.")
        for repo in repos_a_procesar:
            nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo) # Para logging de errores
            try:
                nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = procesar_repo(repo, default_branch=args.branch, existing_action=args.existing, cambios=cambios_a_enviar)
                processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
            except KeyboardInterrupt:
                logging.warning(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo}'.")
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                break
            except Exception as e:
                logging.error(f"\n❌ Error fatal en {repo}: {e}")
                logging.error(f"   Revisa la carpeta de logs/ y {DIR_JSON}/{nombre_repo_temp}_fallo.json para más detalles.")
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Procesamiento de Repositorio", e) # Registrar el error

    logging.info("\n🏁 PROCESAMIENTO FINALIZADO.")
    if cambios_a_enviar and cambios_a_enviar != "APLICAR_JSON_INTERACTIVO":
        logging.info("   ↳ Si pediste cambios (-c/--cambios o menú 'Implementar un cambio'), Gemini ya los")
        logging.info("     generó y escribió directamente en los archivos correspondientes.")
    elif cambios_a_enviar == "APLICAR_JSON_INTERACTIVO":
        logging.info("   ↳ Se intentaron aplicar cambios desde un JSON existente de forma interactiva.")
    else:
        logging.info("   ↳ Se realizó una auditoría general. Revisa los archivos JSON generados en la carpeta 'json_output'.")

    logging.info(f"Total de repositorios procesados exitosamente: {len(processed_repos_info)} de {len(repos_a_procesar)}.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("\n⏹️  Ejecución interrumpida por el usuario.")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Error crítico no manejado en el orquestador: {e}", exc_info=True)
        sys.exit(1)