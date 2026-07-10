import os
import sys
import json
import time
import argparse
import warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

warnings.filterwarnings("ignore", category=FutureWarning)

# Importar funciones auxiliares
from agent_helpers import extraer_codigo_base, agrupar_en_lotes, _cache_es_compatible

# Se incrementa cada vez que cambie la forma del JSON de auditoría (nombres de
# campos, semántica, etc.). Permite invalidar automáticamente la caché en disco
# cuando un informe antiguo ya no es compatible con el código actual.
ESQUEMA_VERSION = 2

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
    codigo_corregido_completo: str = Field(
        default="",
        description=(
            "Si requiere_parche es true, contenido ÍNTEGRO del archivo ya corregido "
            "o del NUEVO archivo creado, listo para sobrescribir o crear el fichero "
            "original tal cual (sin markdown, sin backticks). "
            "Si requiere_parche es false, deja este campo vacío."
        )
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

def _get_system_prompt(cambios: Optional[str]) -> str:
    """Genera el prompt del sistema basado en si se solicitan cambios o una auditoría."""
    if cambios:
        # MODO DESARROLLADOR: El usuario pidió algo (Opción 2 del menú)
        return (
            "Eres un ingeniero de software senior.\n"
            "Tu ÚNICA tarea es aplicar la modificación o refactor que pide el usuario.\n"
            "NO hagas auditorías de seguridad ni busques vulnerabilidades.\n"
            "Para rellenar el JSON de salida usa esta guía exacta:\n"
            "- 'severidad': Usa siempre 'INFO'.\n"
            "- 'vulnerabilidad': Escribe un título corto del cambio (ej. 'Eliminación de comentarios', 'Creación de README').\n"
            "- 'solucion': Describe brevemente qué hiciste.\n"
            "- 'explicacion_sencilla': Escribe 'Se aplicó el cambio solicitado por el usuario'.\n"
            "- 'requiere_parche': Ponlo en true.\n"
            "IMPORTANTE: En 'codigo_corregido_completo' devuelve el ARCHIVO COMPLETO (todo el fichero modificado o creado), "
            "listo para sobrescribir o crear directamente. No incluyas backticks de markdown."
        )
    else:
        # MODO AUDITOR: Búsqueda de bugs (Opción 1 del menú)
        return (
            "Eres un ingeniero de software senior y auditor técnico.\n"
            "Analiza el código buscando EXCLUSIVAMENTE bugs críticos, vulnerabilidades de seguridad y problemas graves de arquitectura.\n"
            "NO reportes problemas de estilo, formato o comentarios (a menos que filtren credenciales).\n"
            "Si encuentras un problema grave, clasifica su severidad (Alta, Media, Baja) y explica el fallo en los campos correspondientes.\n"
            "Si sabes cómo solucionarlo de forma segura, pon 'requiere_parche' en true y en 'codigo_corregido_completo' "
            "devuelve el ARCHIVO COMPLETO ya corregido (sin backticks de markdown)."
        )

def procesar_lote_concurrente(client, modelo, lote, index, total_lotes, config, cambios):
    """Función de trabajador que procesa el lote llamando a la API inmediatamente."""
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
            print(f"      ⚠️ [Lote {index}] APIError: {msg}") 
            
            if intento < max_reintentos:
                espera = 20 * intento 
                print(f"      ⏳ [Lote {index}] Reintentando en {espera}s...")
                time.sleep(espera)
        except Exception as e:
            print(f"      ⚠️ [Lote {index}] Error crítico local: {str(e)}")
            break
            
    return None

def analizar_con_gemini_robusto(codigo_proyecto, cambios=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: 
        print("❌ Error: GEMINI_API_KEY no definida en el entorno.")
        return None
        
    client = genai.Client(api_key=api_key)
    modelo_activo = 'gemini-2.5-flash'
    
    prompt_sistema = _get_system_prompt(cambios)
    
    config = types.GenerateContentConfig(
        system_instruction=prompt_sistema, 
        response_mime_type="application/json", 
        response_schema=ReporteAuditoria, 
        temperature=0.2
    )

    lotes = agrupar_en_lotes(codigo_proyecto, max_chars=80000)
    total_lotes = len(lotes)
    
    print(f"\n   📦 Proyecto dividido dinámicamente en {total_lotes} lotes por límite de contexto.")
    
    reporte_consolidado = {
        "esquema_version": ESQUEMA_VERSION,
        "nombre_microservicio": os.environ.get("NOMBRE_MICROSERVICIO", "Microservicio"),
        "resumen_arquitectura": "Análisis combinado de múltiples componentes.", 
        "puntos_criticos_seguridad": [], 
        "calidad_codigo_score": 85, 
        "conclusiones_generales": ""
    }
    
    scores = []
    lotes_ok = 0
    
    print("\n   🚀 Iniciando envío CONCURRENTE puro (todas las peticiones a la vez)...")
    
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
                print(f"      ✅ [Lote {idx}] Procesamiento completado con éxito.")
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

def _save_final_report(informe_final: dict, archivo_salida: Path) -> None:
    """Guarda el informe final en un archivo JSON."""
    try:
        with open(archivo_salida, "w", encoding="utf-8") as f:
            json.dump(informe_final, f, indent=4, ensure_ascii=False)
        print(f"✅ [Agente]: Nuevo reporte guardado en -> {archivo_salida}")
        print(f"   ↳ La selección/aplicación de cambios la gestiona el orquestador (orchestrator.py).")
    except Exception as e:
        print(f"❌ Error guardando el JSON: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_path", type=str)
    parser.add_argument("-c", "--cambios", type=str, default="")
    args = parser.parse_args()
    
    # 1. Definir rutas antes de gastar recursos
    nombre_ms = os.environ.get("NOMBRE_MICROSERVICIO", Path(args.target_path).name)
    dir_salida = Path(os.environ.get("DIR_SALIDA_JSON", "."))
    dir_salida.mkdir(parents=True, exist_ok=True)
    archivo_salida = dir_salida / f"{nombre_ms}_auditoria.json"
    
    # 2. 🛡️ SISTEMA DE CACHÉ / AHORRO DE TOKENS
    cache_valida = archivo_salida.exists() and _cache_es_compatible(archivo_salida, ESQUEMA_VERSION)
    if archivo_salida.exists() and not cache_valida:
        print(f"   ↳ [Agente]: Auditoría previa de '{nombre_ms}' es de un formato antiguo (incompatible). Se regenerará.")

    if cache_valida and not args.cambios.strip():
        print(f"\n⏩ [Agente]: Auditoría previa encontrada para '{nombre_ms}'.")
        print(f"   ↳ Se saltará el análisis de la API para ahorrar tokens.")
        print(f"   ↳ La selección/aplicación de cambios la gestiona el orquestador (orchestrator.py).")
        sys.exit(0) # Salida exitosa sin gastar cuota
        
    # 3. Si no hay caché o se pidieron modificaciones, procedemos con el análisis pesado
    print(f"\n🔍 [Agente]: Iniciando nueva auditoría/modificación para '{nombre_ms}'...")
    codigo_proyecto = extraer_codigo_base(args.target_path)
    
    if not codigo_proyecto:
        print(f"\n✨ [Agente]: No se encontró código analizable en '{nombre_ms}' con las extensiones soportadas.")
        print("   ↳ Esto es habitual en repos que son solo configuración/infraestructura")
        print("     (manifiestos, Helm charts, YAML de despliegue, etc.) sin código fuente propio.")
        print("   ↳ No se considera un fallo: se guarda un informe vacío y se continúa.")
        informe_vacio = {
            "esquema_version": ESQUEMA_VERSION,
            "nombre_microservicio": nombre_ms,
            "resumen_arquitectura": "No se encontró código fuente con las extensiones soportadas actualmente.",
            "puntos_criticos_seguridad": [],
            "calidad_codigo_score": 0,
            "conclusiones_generales": "Repositorio sin código analizable (posible repo de solo configuración/infraestructura).",
        }
        _save_final_report(informe_vacio, archivo_salida)
        sys.exit(0)
        
    print(f"   ↳ [Agente]: {len(codigo_proyecto)} archivos útiles listos para procesarse.")
    informe_final = analizar_con_gemini_robusto(codigo_proyecto, cambios=args.cambios)
    
    if informe_final:
        _save_final_report(informe_final, archivo_salida)
    else:
        print("❌ [Agente] No se pudo generar ningún reporte válido.")
        sys.exit(1)

if __name__ == "__main__":
    main()