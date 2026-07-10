import subprocess
import sys
import os
import shutil
import json
import traceback
import logging
import ast
from datetime import datetime
import warnings
import argparse
import tkinter as tk
from tkinter import filedialog

warnings.filterwarnings("ignore", category=FutureWarning)

DIR_LOGS = "logs"
DIR_JSON = "json_output"
DIR_HTML = "html_output"
DIR_MICROSERVICES = "microservices"
ARCHIVO_ENV = ".env"

def preparar_entorno():
    """Crea los directorios de salida y contenedor si no existen, y limpia la pantalla."""
    os.system('cls' if os.name == 'nt' else 'clear')
    for directorio in [DIR_LOGS, DIR_JSON, DIR_HTML, DIR_MICROSERVICES]:
        os.makedirs(directorio, exist_ok=True)

def configurar_logger(nombre_repo):
    """Asigna un archivo de log específico para el microservicio actual y lo pinta en consola."""
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
        "detalles_error": {"tipo": tipo_excepcion, "mensaje": mensaje, "traceback": tb_str}
    }
    try:
        with open(archivo_json, "w", encoding="utf-8") as f:
            json.dump([fallo], f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Fallo crítico al escribir en el JSON: {e}", exc_info=True)

def leer_key_de_env():
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

def guardar_key_en_env(key):
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

def forzar_configuracion_api_key(cli_key=None, cambiar_key=False):
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

def seleccionar_con_tkinter():
    """Abre un diálogo visual para seleccionar la carpeta, forzando que aparezca al frente."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()
        
        print("\n🔍 Abriendo explorador de archivos... (Busca la ventana si no la ves)")
        ruta = filedialog.askdirectory(title="📂 Selecciona la carpeta del microservicio a auditar")
        
        root.destroy()
        return ruta
    except ImportError:
        print("\n❌ Error: Falla al cargar la interfaz gráfica.")
        print("💡 Solución: Ejecuta 'sudo apt install python3-tk' en tu terminal para instalar la librería necesaria.")
        return None

def obtener_repositorios_interactivo():
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

def validar_sintaxis_python(codigo_texto, nombre_archivo):
    """🛡️ Escudo Anti-Bugs: Evita aplicar parches que tengan errores sintácticos."""
    if nombre_archivo.endswith('.py'):
        try:
            ast.parse(codigo_texto)
            return True
        except SyntaxError as e:
            print(f"   ❌ [Escudo Anti-Bugs]: La propuesta de la IA rompe la sintaxis de Python.")
            print(f"      Detalle del error: Linea {e.lineno} -> {e.msg}")
            return False
    return True

def gestionar_cambios_git(ruta_repo, archivos_modificados):
    """Crea una rama, hace commit y sube los cambios automáticamente a origin."""
    if not archivos_modificados:
        return

    print("\n====================================================")
    print("🚀 GESTIÓN DE VERSIÓN (GIT AUTOMÁTICO)")
    print("====================================================")
    respuesta = input("👉 ¿Deseas subir estos cambios a una nueva rama remota ahora? (S/N): ").strip().lower()

    if respuesta != 's':
        print("⏭️ Omisión de subida a Git. Los cambios siguen listos en tu entorno local.")
        return

    nombre_rama = input("👉 Nombre de la nueva rama (Enter para usar nombre generado por IA): ").strip()
    if not nombre_rama:
        nombre_rama = f"fix/ia-auditoria-{datetime.now().strftime('%Y%m%d-%H%M')}"
        print(f"   Usando nombre por defecto: {nombre_rama}")

    mensaje_commit = input("👉 Mensaje del commit (Enter para usar mensaje estándar): ").strip()
    if not mensaje_commit:
        mensaje_commit = "Refactor: Aplicación de parches generados por IA (Auditoría automática)"
        print(f"   Usando mensaje por defecto: '{mensaje_commit}'")

    try:
        print(f"\n   ⚙️  Creando rama '{nombre_rama}'...")
        subprocess.run(["git", "checkout", "-b", nombre_rama], cwd=ruta_repo, check=True, capture_output=True, text=True)

        print("   ⚙️  Añadiendo archivos al stage (git add)...")
        for archivo in archivos_modificados:
            subprocess.run(["git", "add", archivo], cwd=ruta_repo, check=True, capture_output=True, text=True)

        print("   ⚙️  Registrando commit...")
        subprocess.run(["git", "commit", "-m", mensaje_commit], cwd=ruta_repo, check=True, capture_output=True, text=True)

        print(f"   ⏳ Subiendo cambios a origin/{nombre_rama} (Esto puede tardar unos segundos)...")
        subprocess.run(["git", "push", "-u", "origin", nombre_rama], cwd=ruta_repo, check=True, capture_output=True, text=True)
        
        print(f"   ✅ ¡Éxito! Cambios subidos correctamente.")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error crítico al ejecutar comandos Git en {ruta_repo}")
        print(f"   Detalle del error: {e.stderr.strip() if e.stderr else e.stdout.strip()}")
        logging.error(f"Fallo en Git ({e.cmd}): {e.stderr if e.stderr else e.stdout}")

def aplicar_mejoras_interactivas(nombre_repo, ruta_base_proyecto):
    """Lee el reporte, exporta un JSON con los cambios disponibles y permite aplicarlos selectivamente."""
    archivo_auditoria = os.path.join(DIR_JSON, f"{nombre_repo}_auditoria.json")
    if not os.path.exists(archivo_auditoria): return

    try:
        with open(archivo_auditoria, "r", encoding="utf-8") as f:
            reporte = json.load(f)
        
        puntos_criticos = reporte.get("puntos_criticos_seguridad", [])
        puntos_con_parche = [p for p in puntos_criticos if p.get("codigo_corregido_completo")]

        if not puntos_con_parche:
            print("\n✨ El asistente no propuso modificaciones de código automáticas.")
            return

        # 1. Crear y exportar la lista de cambios disponibles a un nuevo JSON
        resumen_exportacion = []
        for idx, propuesta in enumerate(puntos_con_parche, 1):
            resumen_exportacion.append({
                "id_cambio": idx,
                "archivo": propuesta.get("archivo"),
                "proposito": propuesta.get('vulnerabilidad') or 'Modificación solicitada',
                "explicacion": propuesta.get('explicacion_sencilla', 'Sin detalles adicionales.')
            })
            
        archivo_exportacion = os.path.join(DIR_JSON, f"{nombre_repo}_cambios_disponibles.json")
        with open(archivo_exportacion, "w", encoding="utf-8") as f_export:
            json.dump(resumen_exportacion, f_export, indent=4, ensure_ascii=False)
            
        print(f"\n💾 Archivo de cambios disponibles exportado a: {archivo_exportacion}")

        # 2. Imprimir el menú de opciones
        print("\n====================================================")
        print("🛠️  RESULTADOS DE LA AUDITORÍA: CAMBIOS DISPONIBLES")
        print("====================================================")

        for item in resumen_exportacion:
            print(f"[{item['id_cambio']}] 📄 Archivo: {item['archivo']}")
            print(f"    ⚠️  Propósito: {item['proposito']}")
            print(f"    🎓 Explicación: {item['explicacion']}")
            print("-" * 50)

        # 3. Pedir al usuario que seleccione qué aplicar
        print("\n👉 Introduce los números de los cambios a aplicar, separados por comas (ej. 1, 3).")
        print("👉 O escribe 'T' para aplicarlos Todos. (Presiona Enter para cancelar).")
        seleccion = input("Selección: ").strip().lower()

        if not seleccion:
            print("⏭️ Aplicación de cambios cancelada por el usuario.")
            return

        indices_a_aplicar = []
        if seleccion == 't' or seleccion == 'todos':
            indices_a_aplicar = list(range(1, len(puntos_con_parche) + 1))
        else:
            try:
                partes = seleccion.split(',')
                for p in partes:
                    num = int(p.strip())
                    if 1 <= num <= len(puntos_con_parche):
                        indices_a_aplicar.append(num)
            except ValueError:
                print("❌ Error en el formato. Usa números separados por comas. Operación cancelada.")
                return

        if not indices_a_aplicar:
            print("⏭️ No se seleccionó ningún cambio válido dentro del rango.")
            return

        # 4. Aplicar los cambios seleccionados
        print("\n⚙️  APLICANDO CAMBIOS SELECCIONADOS...")
        archivos_modificados_exito = [] 
        
        for idx in indices_a_aplicar:
            propuesta = puntos_con_parche[idx - 1] 
            archivo_relativo = propuesta.get("archivo")
            ruta_archivo_real = os.path.join(ruta_base_proyecto, archivo_relativo)
            codigo_ia = propuesta["codigo_corregido_completo"]
            
            print(f"\nProcesando [{idx}]: {archivo_relativo}...")
            
            # Escudo Anti-Bugs
            if not validar_sintaxis_python(codigo_ia, archivo_relativo):
                print("   ⏭️ Cambio omitido automáticamente para proteger tu repositorio (Error Sintáctico).")
                continue
                
            if os.path.exists(ruta_archivo_real):
                shutil.copy2(ruta_archivo_real, f"{ruta_archivo_real}.bak")
                try:
                    with open(ruta_archivo_real, "w", encoding="utf-8") as f_out:
                        f_out.write(codigo_ia)
                    print(f"   ✅ ¡Archivo modificado con éxito! (Copia .bak guardada)")
                    archivos_modificados_exito.append(archivo_relativo) 
                except Exception as e:
                    print(f"   ❌ Error escribiendo cambios: {e}")
            else:
                print(f"   ❌ El archivo no existe en el disco local: {ruta_archivo_real}")

        # 5. Lanzar proceso Git si hubo modificaciones exitosas
        if archivos_modificados_exito:
            gestionar_cambios_git(ruta_base_proyecto, archivos_modificados_exito)

    except Exception as e:
        print(f"⚠️ Error procesando la interactividad: {e}")

def procesar_repo(url_o_ruta_completa, default_branch=None, existing_action=None, cambios=None):
    rama = default_branch
    if "#" in url_o_ruta_completa: url_o_ruta, rama = url_o_ruta_completa.split("#", 1)
    else: url_o_ruta = url_o_ruta_completa

    if url_o_ruta.startswith("http"):
        nombre_repo = url_o_ruta.split("/")[-1].replace(".git", "")
        carpeta_destino = os.path.join(DIR_MICROSERVICES, nombre_repo)
        ruta_trabajo = os.path.abspath(carpeta_destino)
    else:
        nombre_repo = os.path.basename(os.path.normpath(url_o_ruta))
        carpeta_destino = url_o_ruta
        ruta_trabajo = os.path.abspath(url_o_ruta)

    configurar_logger(nombre_repo)
    logging.info(f"--- INICIANDO PROCESO PARA EL REPOSITORIO: {nombre_repo} ---")
    
    if url_o_ruta.startswith("http"):
        if os.path.exists(carpeta_destino):
            respuesta = existing_action.lower() if existing_action else 'n'
            if respuesta == 's':
                shutil.rmtree(carpeta_destino)
                subprocess.run(["git", "clone", url_o_ruta, carpeta_destino], check=True, capture_output=True, text=True, encoding='utf-8')
        else:
            subprocess.run(["git", "clone", url_o_ruta, carpeta_destino], check=True, capture_output=True, text=True, encoding='utf-8')

    if rama:
        directorio_git = carpeta_destino if url_o_ruta.startswith("http") else ruta_trabajo
        subprocess.run(["git", "checkout", rama], cwd=directorio_git, check=True, capture_output=True, text=True, encoding='utf-8')

    entorno_subproceso = os.environ.copy()
    entorno_subproceso["NOMBRE_MICROSERVICIO"] = nombre_repo
    entorno_subproceso["DIR_SALIDA_JSON"] = os.path.abspath(DIR_JSON)
    entorno_subproceso["PYTHONUNBUFFERED"] = "1"
    entorno_subproceso["PYTHONIOENCODING"] = "utf-8" 

    try:
        comando = [sys.executable, "code_auditor_agent.py", ruta_trabajo]
        if cambios: comando.extend(["--cambios", cambios])
        
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
                logging.info(linea.strip('\n'))
                
            proc.wait()
            
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, comando)

    except subprocess.CalledProcessError as e:
        registrar_fallo_json(nombre_repo, url_o_ruta, "Ejecución de Agente", e)
        
        print(f"\n❌ El subproceso falló con el código de salida: {e.returncode}", file=sys.stderr)
        print("💡 Revisa los logs de la consola o el archivo .log para ver dónde ocurrió el error.", file=sys.stderr)
        
        raise e

def main():
    preparar_entorno()
    parser = argparse.ArgumentParser()
    parser.add_argument("repos", nargs="*")
    parser.add_argument("-k", "--api-key", type=str)
    parser.add_argument("-b", "--branch", type=str)
    parser.add_argument("-e", "--existing", choices=['s', 'n', 'c'])
    parser.add_argument("-c", "--cambios", type=str)
    args = parser.parse_args()

    forzar_configuracion_api_key(cli_key=args.api_key)
    
    repos = args.repos
    cambios_a_enviar = args.cambios
    
    if not repos:
        resultado = obtener_repositorios_interactivo()
        if not resultado: sys.exit(0)
        
        repos, cambios_interactivos = resultado
        if cambios_interactivos:
            cambios_a_enviar = cambios_interactivos

    elif args.repos and not args.cambios:
        print("\n----------------------------------------------------")
        opcion_cambios = input("👉 ¿Qué cambios quieres implementar o auditar? (Enter para omitir): ").strip()
        if opcion_cambios: cambios_a_enviar = opcion_cambios

    for repo in repos:
        try:
            ruta_limpia = repo.split("#")[0]
            if ruta_limpia.startswith("http"):
                nombre_repo = ruta_limpia.split("/")[-1].replace(".git", "")
                ruta_ejecucion = os.path.abspath(os.path.join(DIR_MICROSERVICES, nombre_repo))
            else:
                nombre_repo = os.path.basename(os.path.normpath(ruta_limpia))
                ruta_ejecucion = os.path.abspath(ruta_limpia)

            procesar_repo(repo, default_branch=args.branch, existing_action=args.existing, cambios=cambios_a_enviar)
            aplicar_mejoras_interactivas(nombre_repo, ruta_ejecucion)
        except Exception:
            print(f"\n❌ Error fatal en {repo}. Revisa carpetas de logs/")

    print("\n🏁 PROCESAMIENTO FINALIZADO.")

if __name__ == "__main__":
    main()