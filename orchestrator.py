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
import concurrent.futures # Nuevo import para concurrencia

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
# SELECCIÓN INTERACTIVA DE ENTRADA
# ============================================================

def seleccionar_con_tkinter() -> Optional[str]:
    """Abre un diálogo visual para seleccionar la carpeta, forzando que aparezca al frente.

    El import de tkinter se hace aquí, de forma perezosa: así el script entero
    sigue funcionando en modo CLI/servidor sin entorno gráfico ni tkinter
    instalado, y solo falla (con mensaje claro) si el usuario elige esta opción.
    """ 
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("\n❌ Error: Falla al cargar la interfaz gráfica (tkinter no disponible).")
        print("💡 Solución: Ejecuta 'sudo apt install python3-tk' en tu terminal para instalar la librería necesaria.")
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()

        print("\n🔍 Abriendo explorador de archivos... (Busca la ventana si no la ves)")
        ruta = filedialog.askdirectory(title="📂 Selecciona la carpeta del microservicio a auditar")

        root.destroy()
        return ruta or None
    except Exception as e:
        print(f"\n❌ Error inesperado abriendo el explorador de archivos: {e}")
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

        if opcion == "3":
            forzar_configuracion_api_key(cambiar_key=True)
            continue

        ruta_final = None

        if opcion == "1":
            ruta = seleccionar_con_tkinter()
            if not ruta:
                print("⏭️ Cancelaste la selección de carpeta.")
                continue
            print(f"\n✅ Carpeta seleccionada: {ruta}")
            ruta_final = ruta

        elif opcion == "2":
            url = input("👉 Introduce la URL del repositorio Git: ").strip()
            if not url:
                print("⏭️ Cancelaste la introducción de la URL.")
                continue
            rama = input("👉 ¿Qué rama deseas clonar? (Enter para la por defecto): ").strip()
            if rama and rama.startswith("-"):
                print("❌ Nombre de rama no válido (no puede empezar por '-'). Operación cancelada.")
                continue
            print(f"\n✅ Repositorio seleccionado: {url}")
            ruta_final = f"{url}#{rama}" if rama else url

        else:
            print("❌ Opción no válida. Inténtalo de nuevo.")
            continue

        if ruta_final:
            while True:
                print("\n----------------------------------------------------")
                print("🛠️  ¿QUÉ DESEAS HACER CON ESTE DIRECTORIO/REPOSITORIO?")
                print("----------------------------------------------------")
                print("1. 🕵️  Auditoría general (Buscar bugs y vulnerabilidades)")
                print("2. ✨ Implementar un cambio o mejora específica")
                print("3. 🔙 Cancelar y elegir otra ruta")

                sub_opcion = input("\n👉 Elige una acción (1, 2 o 3): ").strip()

                if sub_opcion == "1":
                    return [ruta_final], None
                elif sub_opcion == "2":
                    cambios = input("\n📝 Describe qué cambio quieres que haga la IA (ej. 'Añadir logs', 'Optimizar imports'):\n👉 ").strip()
                    return [ruta_final], cambios if cambios else None
                elif sub_opcion == "3":
                    print("🔙 Volviendo al menú principal...")
                    break
                else:
                    print("❌ Opción no válida. Inténtalo de nuevo.")


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
# EJECUCIÓN DE COMANDOS EXTERNOS
# ============================================================

def _run_external_command(cmd: List[str], cwd: str, error_stage: str,
                          nombre_repo: str, repo_url_o_ruta: str,
                          capture_output: bool = True, check: bool = True,
                          text: bool = True, encoding: str = 'utf-8') -> subprocess.CompletedProcess:
    """Wrapper para ejecutar comandos externos, centralizando el manejo de errores y logging."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=capture_output,
                                check=check, text=text, encoding=encoding)
        return result
    except subprocess.CalledProcessError as e:
        logging.error(f"Comando fallido en {error_stage} para {nombre_repo}: {' '.join(cmd)}")
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
            subprocess.run(["git", "clone", url, carpeta_destino], check=True, capture_output=True, text=True, encoding='utf-8')
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
        registrar_fallo_json(nombre_repo, url_o_ruta, "Checkout de Rama", error)
        raise error
    try:
        logging.info(f"Realizando checkout a la rama '{rama}' en '{directorio_git}'...")
        subprocess.run(["git", "checkout", rama], cwd=directorio_git, check=True, capture_output=True, text=True, encoding='utf-8')
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

    if url_o_ruta.startswith("http"):
        if os.path.exists(carpeta_destino):
            respuesta = existing_action.lower() if existing_action else 'n'
            if respuesta == 's':
                logging.info(f"Eliminando directorio existente: {carpeta_destino}")
                shutil.rmtree(carpeta_destino)
                _clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo)
            elif respuesta == 'c': # 'c' para continuar, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente: {carpeta_destino}")
            else: # 'n' para no, no clonar de nuevo
                logging.info(f"Reutilizando directorio existente: {carpeta_destino}")
        else:
            _clonar_repositorio(url_o_ruta, carpeta_destino, nombre_repo)

    if rama:
        directorio_git = carpeta_destino if url_o_ruta.startswith("http") else ruta_trabajo
        _checkout_rama(directorio_git, rama, nombre_repo, url_o_ruta)

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
        return nombre_repo, ruta_trabajo, url_o_ruta
    except subprocess.CalledProcessError as e:
        logging.error(f"El subproceso del agente falló para {nombre_repo}. Código: {e.returncode}")
        logging.error(f"Salida del agente: {e.output}")
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente", e)
        raise # Re-raise para ser capturado por el executor
    except Exception as e:
        logging.error(f"Error inesperado durante el procesamiento del agente para {nombre_repo}: {e}", exc_info=True)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente (Excepción)", e)
        raise

def _check_git_installed() -> None:
    """Verifica si Git está instalado y accesible en el PATH."""
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True, text=True)
        logging.info("✅ Git está instalado.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n❌ Error: Git no está instalado o no está en el PATH.")
        print("   Por favor, instala Git para continuar.")
        sys.exit(1)


# ============================================================
# MAIN
# ============================================================

def main() -> None:
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

    repos_a_procesar = args.repos
    cambios_a_enviar = args.cambios

    if not repos_a_procesar:
        resultado_interactivo = obtener_repositorios_interactivo()
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

    # Lista para almacenar información de los repositorios procesados exitosamente
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
                    # El error ya fue registrado por procesar_repo o _run_external_command
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
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Procesamiento de Repositorio", e) # Registrar el error

    print("\n🏁 PROCESAMIENTO FINALIZADO.")
    print("   ↳ Si pediste cambios (-c/--cambios o menú 'Implementar un cambio'), Gemini ya los")
    print("     generó y escribió directamente en los archivos correspondientes.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️  Ejecución interrumpida por el usuario.")
        sys.exit(1)
