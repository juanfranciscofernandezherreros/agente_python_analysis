import subprocess
import sys
import os
import shutil
import json
import traceback
import platform
import logging
from datetime import datetime
import warnings
import argparse  # Gestiona todas las opciones por línea de comandos

# Silenciar las advertencias de versiones antiguas de Python (ej: Google Auth)
warnings.filterwarnings("ignore", category=FutureWarning)

# --- RUTAS DE DIRECTORIOS Y CONFIGURACIÓN ---
DIR_LOGS = "logs"
DIR_JSON = "json_output"
DIR_HTML = "html_output"
DIR_MICROSERVICES = "microservices"  # Carpeta raíz contenedora
ARCHIVO_KEY_LOCAL = ".gemini_key"    # Archivo local donde se guarda la clave

def preparar_entorno():
    """Crea los directorios de salida y contenedor si no existen, y limpia la pantalla."""
    os.system('cls' if os.name == 'nt' else 'clear')
    for directorio in [DIR_LOGS, DIR_JSON, DIR_HTML, DIR_MICROSERVICES]:
        os.makedirs(directorio, exist_ok=True)

def configurar_logger(nombre_repo):
    """Asigna un archivo de log específico para el microservicio actual."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    
    archivo_log = os.path.join(DIR_LOGS, f"{nombre_repo}.log")
    file_handler = logging.FileHandler(archivo_log, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

def registrar_fallo_json(nombre_repo, repo_url_o_ruta, etapa, excepcion):
    """Guarda el detalle técnico duro en un JSON dedicado para este microservicio."""
    archivo_json = os.path.join(DIR_JSON, f"{nombre_repo}_fallo.json")
    
    if isinstance(excepcion, Exception):
        tb_str = "".join(traceback.format_exception(type(excepcion), excepcion, excepcion.__traceback__))
        tipo_excepcion = type(excepcion).__name__
        mensaje = str(excepcion)
    else:
        tb_str = "N/A"
        tipo_excepcion = "InterrupcionManual"
        mensaje = str(excepcion)
            
    fallo = {
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "microservicio": nombre_repo,
        "ruta_origen": repo_url_o_ruta,
        "etapa_fallida": etapa,
        "detalles_error": {
            "tipo": tipo_excepcion,
            "mensaje": mensaje,
            "traceback": tb_str
        },
        "contexto_ejecucion": {
            "sistema_operativo": f"{platform.system()} {platform.release()}",
            "version_python": sys.version.split()[0],
            "directorio_trabajo": os.getcwd()
        }
    }
    
    try:
        with open(archivo_json, "w", encoding="utf-8") as f:
            json.dump([fallo], f, indent=4, ensure_ascii=False)
        logging.info(f"JSON de error generado: '{archivo_json}'")
    except Exception as e:
        logging.error(f"Fallo crítico al escribir en el JSON: {e}", exc_info=True)

def forzar_configuracion_api_key(cli_key=None, cambiar_key=False):
    """Configura la clave usando argumentos CLI, archivo local o entrada interactiva."""
    if "GOOGLE_API_KEY" in os.environ:
        del os.environ["GOOGLE_API_KEY"]

    # Si se pide explícitamente cambiar la clave por argumento CLI
    if cambiar_key:
        if os.path.exists(ARCHIVO_KEY_LOCAL):
            try:
                os.remove(ARCHIVO_KEY_LOCAL)
                print("🗑️ Clave anterior eliminada localmente.")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar el archivo de clave antiguo: {e}")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    # Si se pasó una clave nueva directamente como argumento CLI (-k)
    if cli_key:
        try:
            with open(ARCHIVO_KEY_LOCAL, "w", encoding="utf-8") as f:
                f.write(cli_key)
            print("💾 Nueva clave pasada por argumento guardada en '.gemini_key'.")
        except Exception as e:
            print(f"⚠️ No se pudo guardar la clave del argumento en el archivo local: {e}")
        os.environ["GEMINI_API_KEY"] = cli_key
        return

    # Si ya existe el archivo local y no se está forzando un cambio, se carga automáticamente
    if os.path.exists(ARCHIVO_KEY_LOCAL):
        with open(ARCHIVO_KEY_LOCAL, "r", encoding="utf-8") as f:
            key_guardada = f.read().strip()
            if key_guardada:
                os.environ["GEMINI_API_KEY"] = key_guardada
                return

    # Si no hay clave por ningún lado, se recurre al prompt tradicional
    print("----------------------------------------------------")
    print("🔑 CONFIGURACIÓN DE CREDENCIAL GOOGLE GEMINI")
    print("----------------------------------------------------")
    key = input("👉 Introduce tu Gemini API Key: ").strip()
    while not key:
        print("❌ La clave no puede estar vacías.")
        key = input("👉 Introduce tu Gemini API Key: ").strip()
        
    try:
        with open(ARCHIVO_KEY_LOCAL, "w", encoding="utf-8") as f:
            f.write(key)
        print("💾 Clave guardada localmente en '.gemini_key'.")
    except Exception as e:
        print(f"⚠️ No se pudo guardar la clave en el archivo local: {e}")

    os.environ["GEMINI_API_KEY"] = key
    print("✅ Clave configurada con éxito.\n")

def obtener_repositorios_interactivo():
    """Muestra el menú interactivo si no se pasaron repositorios por argumento."""
    while True:
        print("----------------------------------------------------")
        print("📥 SELECCIÓN DE ENTRADA Y RAMAS")
        print("----------------------------------------------------")
        print("1. Analizar una carpeta local")
        print("2. Analizar un repositorio remoto (Git URL)")
        print("3. Cambiar / Reemplazar la Gemini API Key actual")
        
        opcion = input("👉 Elige una opción (1, 2 o 3): ").strip()
        while opcion not in ["1", "2", "3"]:
            opcion = input("❌ Opción inválida. Elige 1, 2 o 3: ").strip()
        
        if opcion == "3":
            forzar_configuracion_api_key(cambiar_key=True)
            continue
        
        repos = []
        if opcion == "1":
            ruta = input("👉 Introduce la ruta de la carpeta local: ").strip()
            if ruta:
                rama = input("👉 ¿Qué rama deseas analizar? (Presiona Enter para mantener la rama actual): ").strip()
                if rama:
                    repos.append(f"{ruta}#{rama}")
                else:
                    repos.append(ruta)
            return repos
        else:
            url = input("👉 Introduce la URL del repositorio Git: ").strip()
            if url:
                rama = input("👉 ¿Qué rama (branch) deseas clonar? (Presiona Enter para la por defecto): ").strip()
                if rama:
                    repos.append(f"{url}#{rama}")
                else:
                    repos.append(url)
            return repos

def procesar_repo(url_o_ruta_completa, default_branch=None, existing_action=None):
    rama = default_branch

    # Si viene una rama específica en la cadena con '#' tiene prioridad absoluta
    if "#" in url_o_ruta_completa:
        url_o_ruta, rama = url_o_ruta_completa.split("#", 1)
    else:
        url_o_ruta = url_o_ruta_completa

    if url_o_ruta.startswith("http"):
        nombre_repo = url_o_ruta.split("/")[-1].replace(".git", "")
        carpeta_destino = os.path.join(DIR_MICROSERVICES, nombre_repo)
        ruta_trabajo = os.path.abspath(carpeta_destino)
    else:
        nombre_repo = os.path.basename(os.path.normpath(url_o_ruta))
        carpeta_destino = url_o_ruta
        ruta_trabajo = os.path.abspath(url_o_ruta)

    configurar_logger(nombre_repo)
    logging.info(f"--- INICIANDO PROCESO PARA EL MICROSERVICIO: {nombre_repo} ---")
    logging.info(f"Origen: {url_o_ruta}")
    if rama:
        logging.info(f"Rama objetivo detectada: {rama}")

    # --- GESTIÓN DE CLONACIÓN ---
    if url_o_ruta.startswith("http"):
        if os.path.exists(carpeta_destino):
            logging.warning(f"La carpeta '{carpeta_destino}' ya existe.")
            
            # Si se pasó la acción por argumento CLI (-e), se ejecuta directo sin preguntar
            if existing_action:
                respuesta = existing_action.lower()
            else:
                print(f"\n⚠️  La carpeta del microservicio '{carpeta_destino}' ya existe.")
                print(" [S]í      -> Eliminar y volver a clonar limpio")
                print(" [N]o      -> Usar los archivos locales existentes")
                print(" [C]ancelar -> Omitir este microservicio")
                respuesta = input("👉 Selecciona una opción (S/N/C): ").strip().lower()
                while respuesta not in ['s', 'n', 'c']:
                    respuesta = input("❌ Opción inválida. Elige S, N o C: ").strip().lower()
            
            if respuesta == 's':
                try:
                    logging.info(f"Eliminando directorio '{carpeta_destino}' para clonación limpia...")
                    shutil.rmtree(carpeta_destino)
                    logging.info(f"Clonando {url_o_ruta} en '{carpeta_destino}'...")
                    subprocess.run(["git", "clone", url_o_ruta, carpeta_destino], check=True, capture_output=True, text=True, encoding='utf-8')
                except subprocess.CalledProcessError as e:
                    logging.error(f"Fallo al clonar. Git stderr: {e.stderr.strip()}", exc_info=True)
                    registrar_fallo_json(nombre_repo, url_o_ruta, "Clonación (Re-clonado)", e)
                    raise e
            elif respuesta == 'n':
                logging.info("Utilizando el directorio local existente.")
            else:
                logging.warning(f"Operación cancelada para {nombre_repo}.")
                registrar_fallo_json(nombre_repo, url_o_ruta, "Interrupción", "Operación omitida.")
                return 
        else:
            try:
                logging.info(f"Clonando {url_o_ruta} en '{carpeta_destino}'...")
                subprocess.run(["git", "clone", url_o_ruta, carpeta_destino], check=True, capture_output=True, text=True, encoding='utf-8')
            except subprocess.CalledProcessError as e:
                logging.error(f"Fallo al clonar. Git stderr: {e.stderr.strip()}", exc_info=True)
                registrar_fallo_json(nombre_repo, url_o_ruta, "Clonación Inicial", e)
                raise e

    # --- CAMBIO DE RAMA (CHECKOUT) ---
    if rama:
        try:
            logging.info(f"Cambiando a la rama '{rama}'...")
            directorio_git = carpeta_destino if url_o_ruta.startswith("http") else ruta_trabajo
            
            if url_o_ruta.startswith("http"):
                subprocess.run(["git", "fetch", "--all"], cwd=directorio_git, capture_output=True, text=True, encoding='utf-8')

            subprocess.run(
                ["git", "checkout", rama], 
                cwd=directorio_git, 
                check=True, 
                capture_output=True, 
                text=True, 
                encoding='utf-8'
            )
            logging.info(f"✅ Checkout exitoso a la rama: {rama}")
        except subprocess.CalledProcessError as e:
            logging.error(f"Fallo al hacer checkout a la rama '{rama}'. Git stderr: {e.stderr.strip()}", exc_info=True)
            registrar_fallo_json(nombre_repo, url_o_ruta, f"Git Checkout ({rama})", e)
            raise e

    # --- ENTORNO Y EJECUCIÓN DEL AUDITOR ---
    entorno_subproceso = os.environ.copy()
    entorno_subproceso["PYTHONIOENCODING"] = "utf-8"
    entorno_subproceso["NOMBRE_MICROSERVICIO"] = nombre_repo
    entorno_subproceso["DIR_SALIDA_HTML"] = os.path.abspath(DIR_HTML)
    entorno_subproceso["DIR_SALIDA_JSON"] = os.path.abspath(DIR_JSON)

    try:
        logging.info(f"Lanzando Agente Auditor (code_auditor_agent.py) sobre: {ruta_trabajo}")
        resultado = subprocess.run(
            [sys.executable, "code_auditor_agent.py", ruta_trabajo], 
            env=entorno_subproceso, 
            check=True,
            capture_output=True, 
            text=True,
            encoding='utf-8'
        )
        if resultado.stdout:
            logging.info(f"Salida estándar del Auditor:\n{resultado.stdout.strip()}")
            
        logging.info(f"✅ Pipeline finalizado con ÉXITO para: {nombre_repo}")
        
    except subprocess.CalledProcessError as e:
        error_msg = f"El Agente Auditor falló (Código {e.returncode})."
        if e.stdout and e.stdout.strip():
            error_msg += f"\n\n[STDOUT DEL AGENTE]:\n{e.stdout.strip()}"
        if e.stderr and e.stderr.strip():
            error_msg += f"\n\n[STDERR DEL AGENTE]:\n{e.stderr.strip()}"

        logging.error(error_msg)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Auditoría", e)
        raise e
        
    except Exception as e:
        logging.error(f"Error inesperado durante la auditoría: {e}", exc_info=True)
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Auditoría", e)
        raise e

def main():
    preparar_entorno()

    # --- DEFINICIÓN DE ARGUMENTOS CLI ---
    parser = argparse.ArgumentParser(description="Orquestador de Auditoría con Soporte Total por Argumentos.")
    parser.add_argument("repos", nargs="*", help="Rutas locales o URLs de repositorios remotos Git.")
    parser.add_argument("-k", "--api-key", type=str, help="Asigna directamente una Gemini API Key.")
    parser.add_argument("-b", "--branch", type=str, help="Rama por defecto a aplicar a los repositorios que no tengan una definida.")
    parser.add_argument("-e", "--existing", choices=['s', 'n', 'c'], help="Acción automática si la carpeta ya existe: s (re-clonar), n (usar actual), c (omitir).")
    parser.add_argument("--replace-key", action="store_true", help="Fuerza el borrado de la clave local existente para ingresar una nueva.")
     
    args = parser.parse_args()

    # Configuración de credenciales según flags CLI
    forzar_configuracion_api_key(cli_key=args.api_key, cambiar_key=args.replace_key)

    # Determinar el origen de los repositorios (CLI o Interactivo)
    repos = args.repos if args.repos else obtener_repositorios_interactivo()
    
    if not repos:
        print("❌ No se seleccionó ningún repositorio. Saliendo.")
        sys.exit(0)

    # Bucle de procesamiento aplicando las variables pasadas por argumento
    for repo in repos:
        try:
            procesar_repo(repo, default_branch=args.branch, existing_action=args.existing)
        except Exception as e:
            print(f"\n❌ Error fatal en {repo}. Revisa los archivos en 'logs/' para más detalles.")

    print("\n🏁 TODOS LOS MICROSERVICIOS PROCESADOS. FIN DEL SCRIPT.")

if __name__ == "__main__":
    main()