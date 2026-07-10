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

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    from pydantic import BaseModel, Field
except ImportError:
    print("❌ [Agente] Error: Faltan dependencias. Corre: pip install google-genai pydantic")
    sys.exit(1)

# ==========================================
# 📐 ESQUEMAS PYDANTIC (STRUCTURED OUTPUTS)
# ==========================================
class PuntoCritico(BaseModel):
    archivo: str
    severidad: str
    vulnerabilidad: str
    solucion: str
    explicacion_sencilla: str
    requiere_parche: bool
    parche_diff: str = Field(description="Proporciona SOLO el diff o las líneas exactas a cambiar. NO envíes el código completo.")

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
    """Escanea el código fuente usando pathlib, descartando carpetas y archivos basura."""
    extensiones_validas = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java', '.c', '.cpp', '.cs', '.sh', '.sql'}
    directorios_ignorados = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', 'dist', 'build'}
    archivos_ignorados = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'go.sum', '.gitignore'}
    
    codigo_empaquetado = []
    ruta_base = Path(target_path)
    
    print(f"   ↳ [Agente]: Extrayendo archivos desde {ruta_base.resolve()}...")

    for archivo in ruta_base.rglob("*"):
        # Ignorar si alguna parte de la ruta contiene un directorio bloqueado
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
    """Agrupa archivos en lotes basándose en el límite de caracteres (~20k tokens por lote)."""
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
    """Función que procesa un solo lote para ser ejecutada en un ThreadPool."""
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
            if intento < max_reintentos:
                espera = (2 ** intento) * 5  # Backoff exponencial: 10s, 20s...
                if "quota" in msg.lower() or "429" in msg:
                    espera = 45
                print(f"      ⏳ [Lote {index}] Cuota saturada/Error. Reintentando en {espera}s...")
                time.sleep(espera)
        except Exception as e:
            print(f"      ⚠️ [Lote {index}] Error crítico: {str(e)}")
            break
            
    return None

def analizar_con_gemini_robusto(codigo_proyecto, cambios=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: 
        print("❌ Error: GEMINI_API_KEY no definida en el entorno.")
        return None
        
    client = genai.Client(api_key=api_key)
    modelo_activo = 'gemini-2.5-flash'
    
    prompt_sistema = (
        "Eres un ingeniero de software senior y auditor técnico.\n"
        "1. Si el desarrollador solicita cambios, aplica esa modificación exacta en los archivos correspondientes.\n"
        "2. Si no hay instrucciones, busca bugs y vulnerabilidades críticas.\n"
        "IMPORTANTE: NO devuelvas archivos completos. Devuelve SOLO el DIFF o las líneas exactas que deben modificarse."
    )
    
    # Aseguramos el JSON perfecto mediante Pydantic
    config = types.GenerateContentConfig(
        system_instruction=prompt_sistema, 
        response_mime_type="application/json", 
        response_schema=ReporteAuditoria, 
        temperature=0.2
    )

    # 🏎️ Agrupación inteligente por tamaño
    lotes = agrupar_en_lotes(codigo_proyecto, max_chars=80000)
    total_lotes = len(lotes)
    
    print(f"\n   📦 Proyecto dividido dinámicamente en {total_lotes} lotes por límite de contexto.")
    
    reporte_consolidado = {
        "nombre_microservicio": os.environ.get("NOMBRE_MICROSERVICIO", "Microservicio"),
        "resumen_arquitectura": "Análisis combinado de múltiples componentes.", 
        "puntos_criticos_seguridad": [], 
        "calidad_codigo_score": 85, 
        "conclusiones_generales": ""
    }
    
    scores = []
    lotes_ok = 0

    # 🚀 Concurrencia real con ThreadPoolExecutor
    print("\n   🚀 Iniciando análisis concurrente...")
    with ThreadPoolExecutor(max_workers=3) as executor: # Ajusta max_workers según tu cuota (Rate Limit) de la API
        futuros = {
            executor.submit(procesar_lote_concurrente, client, modelo_activo, lote, idx, total_lotes, config, cambios): idx 
            for idx, lote in enumerate(lotes, 1)
        }
        
        for futuro in as_completed(futuros):
            idx = futuros[futuro]
            res = futuro.result()
            
            if res:
                print(f"      ✅ [Lote {idx}] Analizado con éxito.")
                lotes_ok += 1
                puntos = res.get("puntos_criticos_seguridad", [])
                reporte_consolidado["puntos_criticos_seguridad"].extend(puntos)
                if "calidad_codigo_score" in res: 
                    scores.append(float(res["calidad_codigo_score"]))
            else:
                print(f"      ❌ [Lote {idx}] Falló tras todos los reintentos.")

    if lotes_ok > 0:
        if scores: reporte_consolidado["calidad_codigo_score"] = int(sum(scores) / len(scores))
        return reporte_consolidado
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_path", type=str)
    parser.add_argument("-c", "--cambios", type=str, default="")
    args = parser.parse_args()
    
    codigo_proyecto = extraer_codigo_base(args.target_path)
    if not codigo_proyecto: sys.exit(1)
        
    print(f"   ↳ [Agente]: {len(codigo_proyecto)} archivos útiles listos para procesarse.")
    informe_final = analizar_con_gemini_robusto(codigo_proyecto, cambios=args.cambios)
    
    if informe_final:
        nombre_ms = os.environ.get("NOMBRE_MICROSERVICIO", "microservicio_desconocido")
        dir_salida = Path(os.environ.get("DIR_SALIDA_JSON", "."))
        dir_salida.mkdir(parents=True, exist_ok=True)
        archivo_salida = dir_salida / f"{nombre_ms}_auditoria.json"
        
        try:
            with open(archivo_salida, "w", encoding="utf-8") as f:
                json.dump(informe_final, f, indent=4, ensure_ascii=False)
            print(f"✅ [Agente]: Reporte guardado en -> {archivo_salida}")
            
            # Encadenar ejecución con el reportero si existe
            if Path("reporter_agent.py").exists():
                entorno_reportero = os.environ.copy()
                entorno_reportero["ARCHIVO_JSON_ORIGEN"] = str(archivo_salida)
                subprocess.run([sys.executable, "reporter_agent.py"], env=entorno_reportero, text=True, encoding='utf-8')
        except Exception as e:
            print(f"❌ Error guardando el JSON: {e}")
            sys.exit(1)
    else:
        print("❌ [Agente] No se pudo generar ningún reporte válido.")
        sys.exit(1)

if __name__ == "__main__":
    main()