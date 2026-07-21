"""Orquestador principal: expone únicamente el menú de opciones y el punto de entrada.

Toda la lógica auxiliar (logging, gestión de la API key, selección de carpetas,
resolución de rutas, operaciones Git y procesamiento de repositorios) vive en
módulos separados que se importan aquí:

    - config.py            -> constantes compartidas
    - logging_utils.py     -> preparar_entorno, configurar_logger, registrar_fallo_json
    - api_key_manager.py   -> gestión de la GEMINI_API_KEY
    - file_selector.py     -> diálogo Tkinter para elegir carpeta
    - repo_resolver.py     -> resolver_nombre_y_ruta / sanitizar_nombre_repo
    - git_operations.py    -> clonado, checkout y verificación de Git
    - repo_processor.py    -> procesar_repo (pipeline completo por repositorio)
"""

import os
import sys
import logging
import argparse
import concurrent.futures

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from logging_utils import preparar_entorno, registrar_fallo_json
from api_key_manager import forzar_configuracion_api_key
from file_selector import seleccionar_con_tkinter
from repo_resolver import resolver_nombre_y_ruta
from git_operations import check_git_installed
from repo_processor import procesar_repo


# ============================================================
# MENÚ DE OPCIONES (MODO INTERACTIVO)
# ============================================================

def obtener_repositorios_interactivo():
    """Menú interactivo: elegir origen (carpeta local / repo remoto / cambiar API key)
    y a continuación la acción a realizar (auditoría, cambio, aplicar JSON)."""
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
# MAIN
# ============================================================

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logging.info("Iniciando orquestador principal...")

    check_git_installed()

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

    processed_repos_info = []  # List of (nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama)

    if args.jobs > 1 and len(repos_a_procesar) > 1:
        logging.info(f"⚙️  Procesando {len(repos_a_procesar)} repositorios en paralelo con {args.jobs} workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            future_to_repo = {executor.submit(procesar_repo, repo, args.branch, args.existing, cambios_a_enviar): repo for repo in repos_a_procesar}
            for future in concurrent.futures.as_completed(future_to_repo):
                repo_url_o_ruta_completa_original = future_to_repo[future]
                nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo_url_o_ruta_completa_original)
                try:
                    nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = future.result()
                    processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
                    logging.info(f"✅ [Paralelo] Repositorio '{nombre_repo}' procesado con éxito.")
                except KeyboardInterrupt:
                    logging.warning(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo_url_o_ruta_completa_original}'.")
                    registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as e:
                    logging.error(f"\n❌ [Paralelo] Error fatal procesando '{repo_url_o_ruta_completa_original}': {e}")
                    logging.error(f"   Revisa la carpeta de logs/ y json_output/{nombre_repo_temp}_fallo.json para más detalles.")
    else:
        logging.info(f"⚙️  Procesando {len(repos_a_procesar)} repositorios en modo secuencial.")
        for repo in repos_a_procesar:
            nombre_repo_temp, url_o_ruta_temp, _, _ = resolver_nombre_y_ruta(repo)
            try:
                nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama = procesar_repo(repo, default_branch=args.branch, existing_action=args.existing, cambios=cambios_a_enviar)
                processed_repos_info.append((nombre_repo, ruta_ejecucion, url_o_ruta_sin_rama))
            except KeyboardInterrupt:
                logging.warning(f"\n⏹️  Cancelado por el usuario mientras se procesaba '{repo}'.")
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Interrupción Manual", "Cancelado por el usuario (Ctrl+C)")
                break
            except Exception as e:
                logging.error(f"\n❌ Error fatal en {repo}: {e}")
                logging.error(f"   Revisa la carpeta de logs/ y json_output/{nombre_repo_temp}_fallo.json para más detalles.")
                registrar_fallo_json(nombre_repo_temp, url_o_ruta_temp, "Procesamiento de Repositorio", e)

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
