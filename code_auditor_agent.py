import os
import sys
import json
import time
import subprocess 
import argparse
import warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore", category=FutureWarning)

SCRIPT_NAME = os.path.basename(__file__)

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    from pydantic import BaseModel, Field
except ImportError:
    print(f"❌ [{SCRIPT_NAME}] Error: Faltan dependencias. Corre: pip install google-genai pydantic")
    sys.exit(1)

# ==========================================
# 📐 ESQUEMAS PYDANTIC
# ==========================================
class PuntoCritico(BaseModel):
    archivo: str
    severidad: str
    vulnerabilidad: str
    solucion: str
    explicacion_sencilla: str
    codigo_corregido_completo: str = Field(
        default="",
        description="Si se solicitó un cambio, el contenido COMPLETO y final del archivo ya modificado."
    )

class ReporteAuditoria(BaseModel):
    nombre_microservicio: str
    resumen_arquitectura: str
    puntos_criticos_seguridad: list[PuntoCritico]
    calidad_codigo_score: int
    conclusiones_generales: str

# ==========================================
# 🛠️ FUNCIONES PRINCIPALES
# ==========================================

def extraer_codigo_base(target_path):
    extensiones_validas = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java', '.c', '.cpp', '.cs', '.sh', '.sql', '.md', '.json', '.yml', '.yaml', '.html', '.txt'}
    directorios_ignorados = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', 'dist', 'build'}
    archivos_ignorados = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'go.sum', '.gitignore'}
    
    codigo_empaquetado = []
    ruta_base = Path(target_path)
    
    print(f"   ↳ [{SCRIPT_NAME}]: Extrayendo archivos desde {ruta_base.resolve()}...")

    for archivo in ruta_base.rglob("*"):
        if any(part in directorios_ignorados for part in archivo.parts):
            continue
            
        if archivo.is_file() and archivo.name not in archivos_ignorados and archivo.suffix.lower() in extensiones_validas:
            try:
                contenido = archivo.read_text(encoding='utf-8', errors='ignore')
                ruta_relativa = archivo.relative_to(ruta_base).as_posix() 
                codigo_empaquetado.append({"archivo": ruta_relativa, "contenido": contenido})
            except Exception as e:
                print(f"   ⚠️ Error leyendo {archivo.name}: {str(e)}")
                
    return codigo_empaquetado

def agrupar_en_lotes(codigo_proyecto, max_chars=80000):
    lotes = []
    lote_actual = []
    chars_actuales = 0
    
    for arch in codigo_proyecto:
        tamaño = len(arch['contenido'])
        if chars_actuales + tamaño > max_chars and lote_actual:
            lotes.append(lote_actual)
            lote_actual = []
            chars_actuales = 0
        
        lote_actual.append(arch)
        chars_actuales += tamaño
        
    if lote_actual:
        lotes.append(lote_actual)
        
    return lotes

def procesar_lote_concurrente(client, modelo, lote, index, total_lotes, config, cambios):
    enfoque_usuario = f"\n🎯 CAMBIOS SOLICITADOS:\n{cambios}" if cambios else ""
    contenido_usuario = f"Lote {index} de {total_lotes}:\n{json.dumps(lote, ensure_ascii=False)}{enfoque_usuario}"
    
    max_reintentos = 3
    for intento in range(1, max_reintentos + 1):
        try:
            respuesta = client.models.generate_content(
                model=modelo, 
                contents=contenido_usuario, 
                config=config
            )
            return json.loads(respuesta.text)
            
        except APIError as e:
            msg = str(e.message) if hasattr(e, 'message') else str(e)
            print(f"      ⚠️ [{SCRIPT_NAME}] [Lote {index}] APIError: {msg}") 
            
            if intento < max_reintentos:
                espera = 20 * intento 
                print(f"      ⏳ [{SCRIPT_NAME}] [Lote {index}] Reintentando en {espera}s...")
                time.sleep(espera)
        except Exception as e:
            print(f"      ⚠️ [{SCRIPT_NAME}] [Lote {index}] Error crítico local: {str(e)}")
            break
            
    return None

def analizar_con_gemini_robusto(codigo_proyecto, cambios=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: 
        print(f"❌ [{SCRIPT_NAME}] Error: GEMINI_API_KEY no definida en el entorno.")
        return None
        
    client = genai.Client(api_key=api_key)
    modelo_activo = 'gemini-2.5-flash'
    
    # 🔥 AQUÍ ESTÁ LA MAGIA QUE FUERZA A LA IA A TRABAJAR DE VERDAD
    prompt_sistema = (
        "Eres un ingeniero de software senior experto.\n"
        "1. MODO EDICIÓN/CAMBIOS: Si el usuario te pide modificar algo de forma ambigua (ej: 'actualiza el README'), "
        "TIENES PROHIBIDO devolver el texto original. Debes leer el código fuente de los demás archivos proporcionados, "
        "entender la arquitectura del proyecto, y redactar/generar el archivo solicitado desde CERO (ej: un README completo "
        "con Descripción, Instalación, Uso y Arquitectura).\n"
        "2. Como tu salida usa un esquema estricto (PuntoCritico), simplemente rellena 'severidad' y 'vulnerabilidad' con el texto 'Mejora implementada'.\n"
        "3. EN CUALQUIER CASO, devuelve en 'codigo_corregido_completo' el contenido ÍNTEGRO, final y mejorado del archivo, listo para sobrescribirse."
    )
    
    config = types.GenerateContentConfig(
        system_instruction=prompt_sistema, 
        response_mime_type="application/json", 
        response_schema=ReporteAuditoria, 
        temperature=0.4 # Subimos un poco la temperatura para que tenga más creatividad al escribir
    )

    lotes = agrupar_en_lotes(codigo_proyecto, max_chars=80000)
    total_lotes = len(lotes)
    
    print(f"\n   📦 [{SCRIPT_NAME}] Proyecto dividido dinámicamente en {total_lotes} lotes por límite de contexto.")
    
    reporte_consolidado = {
        "nombre_microservicio": os.environ.get("NOMBRE_MICROSERVICIO", "Microservicio"),
        "resumen_arquitectura": "Análisis combinado de múltiples componentes.", 
        "puntos_criticos_seguridad": [], 
        "calidad_codigo_score": 85, 
        "conclusiones_generales": ""
    }
    
    scores = []
    lotes_ok = 0
    
    print(f"\n   🚀 [{SCRIPT_NAME}] Iniciando envío CONCURRENTE puro (todas las peticiones a la vez)...")
    
    max_hilos = total_lotes if total_lotes > 0 else 1
    
    with ThreadPoolExecutor(max_workers=max_hilos) as executor:
        futuros = {
            executor.submit(procesar_lote_concurrente, client, modelo_activo, lote, index, total_lotes, config, cambios): index
            for index, lote in enumerate(lotes, 1)
        }
        
        for futuro in as_completed(futuros):
            idx = futuros[futuro]
            res = futuro.result()
            
            if res:
                print(f"      ✅ [{SCRIPT_NAME}] [Lote {idx}] Procesamiento completado con éxito.")
                lotes_ok += 1
                puntos = res.get("puntos_criticos_seguridad", [])
                reporte_consolidado["puntos_criticos_seguridad"].extend(puntos)
                if "calidad_codigo_score" in res: 
                    scores.append(float(res["calidad_codigo_score"]))
            else:
                print(f"      ❌ [{SCRIPT_NAME}] [Lote {idx}] Falló tras todos los reintentos.")

    if lotes_ok > 0:
        if scores: reporte_consolidado["calidad_codigo_score"] = int(sum(scores) / len(scores))
        return reporte_consolidado
    return None

def _limpiar_markdown(texto: str) -> str:
    if not texto: return ""
    lineas = texto.strip().split("\n")
    if lineas and lineas[0].startswith("```"): lineas = lineas[1:]
    if lineas and lineas[-1].startswith("```"): lineas = lineas[:-1]
    return "\n".join(lineas).strip()

def aplicar_cambios_generados(target_path: str, informe: dict) -> int:
    ruta_base_abs = os.path.abspath(target_path)
    archivos_escritos = 0

    for punto in informe.get("puntos_criticos_seguridad", []):
        codigo_nuevo = punto.get("codigo_corregido_completo", "")
        archivo_relativo = punto.get("archivo", "")
        
        if not codigo_nuevo.strip() or not archivo_relativo.strip():
            continue

        archivo_relativo = archivo_relativo.replace("\\", "/").lstrip("/")
        nombre_carpeta = os.path.basename(ruta_base_abs)
        if archivo_relativo.startswith(f"{nombre_carpeta}/"):
            archivo_relativo = archivo_relativo[len(nombre_carpeta)+1:]

        ruta_destino_abs = os.path.abspath(os.path.join(ruta_base_abs, archivo_relativo))
        
        if not ruta_destino_abs.startswith(ruta_base_abs):
            print(f"   ❌ [{SCRIPT_NAME}] Ruta fuera del proyecto, omitida: {archivo_relativo}")
            continue

        try:
            os.makedirs(os.path.dirname(ruta_destino_abs), exist_ok=True)
            codigo_final = _limpiar_markdown(codigo_nuevo)
            
            # ========================================================
            # 🔥 CHIVATO GIGANTE PARA VER QUÉ COÑO ESTÁ PASANDO 🔥
            # ========================================================
            print("\n" + "!" * 60)
            print("🛑 [DEBUG] INTENTO DE ESCRITURA CAPTURADO")
            print(f"👉 RUTA DESTINO: {ruta_destino_abs}")
            print("👉 CONTENIDO A ESCRIBIR (Primeros 300 caracteres):")
            print(codigo_final[:300] + "\n... [recortado para no llenar la pantalla] ...")
            print("!" * 60 + "\n")
            # ========================================================

            with open(ruta_destino_abs, "w", encoding="utf-8") as f:
                f.write(codigo_final)
            print(f"   ✅ [{SCRIPT_NAME}]: Cambio escrito DIRECTAMENTE en -> {ruta_destino_abs}")
            archivos_escritos += 1
        except Exception as e:
            print(f"   ❌ [{SCRIPT_NAME}] Error escribiendo {archivo_relativo}: {e}")

    return archivos_escritos

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_path", type=str)
    parser.add_argument("-c", "--cambios", type=str, default="")
    args = parser.parse_args()
    
    nombre_ms = os.environ.get("NOMBRE_MICROSERVICIO", Path(args.target_path).name)
    dir_salida = Path(os.environ.get("DIR_SALIDA_JSON", "."))
    dir_salida.mkdir(parents=True, exist_ok=True)
    archivo_salida = dir_salida / f"{nombre_ms}_auditoria.json"
    
    es_modo_edicion = bool(args.cambios.strip())
    
    # 🛡️ SISTEMA DE CACHÉ (Solo funciona si NO estás pidiendo cambios)
    if archivo_salida.exists() and not es_modo_edicion:
        print(f"\n⏩ [{SCRIPT_NAME}]: Auditoría previa encontrada para '{nombre_ms}'.")
        if Path("reporter_agent.py").exists():
            entorno_reportero = os.environ.copy()
            entorno_reportero["ARCHIVO_JSON_ORIGEN"] = str(archivo_salida)
            subprocess.run([sys.executable, "reporter_agent.py"], env=entorno_reportero, text=True, encoding='utf-8')
        sys.exit(0)
        
    print(f"\n🔍 [{SCRIPT_NAME}]: Iniciando proceso para '{nombre_ms}'...")
    codigo_proyecto = extraer_codigo_base(args.target_path)
    
    if not codigo_proyecto: 
        print(f"❌ [{SCRIPT_NAME}] No se encontró código válido para analizar.")
        sys.exit(1)
        
    print(f"   ↳ [{SCRIPT_NAME}]: {len(codigo_proyecto)} archivos extraídos y analizados.")
    informe_final = analizar_con_gemini_robusto(codigo_proyecto, cambios=args.cambios)
    
    if informe_final:
        try:
            # ⛔ MODO EDICIÓN DIRECTA: SIN JSONS
            if es_modo_edicion:
                escritos = aplicar_cambios_generados(args.target_path, informe_final)
                if escritos:
                    print(f"✨ [{SCRIPT_NAME}]: {escritos} archivo(s) modificados directamente.")
                else:
                    print(f"ℹ️ [{SCRIPT_NAME}]: Gemini no devolvió código para escribir.")
            
            # 🕵️‍♂️ MODO AUDITORÍA: Genera JSON y Reporte
            else:
                with open(archivo_salida, "w", encoding="utf-8") as f:
                    json.dump(informe_final, f, indent=4, ensure_ascii=False)
                print(f"✅ [{SCRIPT_NAME}]: Reporte JSON guardado en -> {archivo_salida}")

                if Path("reporter_agent.py").exists():
                    entorno_reportero = os.environ.copy()
                    entorno_reportero["ARCHIVO_JSON_ORIGEN"] = str(archivo_salida)
                    subprocess.run([sys.executable, "reporter_agent.py"], env=entorno_reportero, text=True, encoding='utf-8')
                    
        except Exception as e:
            print(f"❌ [{SCRIPT_NAME}] Error finalizando el proceso: {e}")
            sys.exit(1)
    else:
        print(f"❌ [{SCRIPT_NAME}] Falló el análisis de Gemini.")
        sys.exit(1)

if __name__ == "__main__":
    main()