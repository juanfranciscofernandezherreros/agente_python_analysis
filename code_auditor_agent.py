import os
import sys
import json
import time
import subprocess 
import argparse
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError:
    print("❌ [Agente] Error: Requiere 'google-genai'. Corre: pip install google-genai")
    sys.exit(1)

def extraer_codigo_base(target_path):
    """Escanea el código fuente puro, descartando formatos visuales y lockfiles pesados."""
    extensiones_validas = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java', '.c', '.cpp', '.cs', '.sh', '.sql'}
    directorios_ignorados = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', 'dist', 'build'}
    archivos_ignorados = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'go.sum', '.gitignore'}
    
    codigo_empaquetado = []
    print(f"   ↳ [Agente]: Extrayendo archivos desde {target_path}...")

    for raiz, directorios, archivos in os.walk(target_path):
        directorios[:] = [d for d in directorios if d not in directorios_ignorados]
        for archivo in archivos:
            if archivo in archivos_ignorados: continue
            _, ext = os.path.splitext(archivo)
            if ext.lower() in extensiones_validas:
                ruta_completa = os.path.join(raiz, archivo)
                ruta_relativa = os.path.relpath(ruta_completa, target_path)
                try:
                    with open(ruta_completa, 'r', encoding='utf-8', errors='ignore') as f:
                        codigo_empaquetado.append({"archivo": ruta_relativa, "contenido": f.read()})
                except Exception as e:
                    print(f"   ⚠️ Error leyendo {ruta_relativa}: {str(e)}")
    return codigo_empaquetado

def ejecutar_llamada_api(client, modelo, contenido_usuario, config):
    max_reintentos = 2
    for intento in range(1, max_reintentos + 1):
        try:
            respuesta = client.models.generate_content(model=modelo, contents=contenido_usuario, config=config)
            return json.loads(respuesta.text)
        except APIError as e:
            msg = str(e.message) if hasattr(e, 'message') else str(e)
            if intento < max_reintentos:
                espera = 45 if "quota" in msg.lower() else 5
                print(f"      ⏳ Cuota saturada. Esperando {espera}s...")
                time.sleep(espera)
    return None

def analizar_con_gemini_robusto(codigo_proyecto, cambios=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key: return None
    client = genai.Client(api_key=api_key)
    
    # 🧠 Nuevo Rol Híbrido: Programador + Auditor Técnico
    prompt_sistema = (
        "Eres un ingeniero de software senior y experto en refactorización de código.\n"
        "Tu objetivo es procesar un lote de archivos de un repositorio según este criterio:\n"
        "1. Si el desarrollador HA PROPORCIONADO instrucciones o solicitudes de cambios específicos, "
        "tu prioridad número uno es aplicar exactamente esa modificación, añadir las funciones, rutas o ítems solicitados "
        "en los archivos correspondientes.\n"
        "2. Si el desarrollador NO dejó instrucciones, audita el código buscando vulnerabilidades críticas.\n\n"
        "Para cualquier archivo modificado o parcheado, proporciona el código COMPLETO actualizado.\n"
        "DEBES responder EXCLUSIVAMENTE con un JSON con este formato:\n"
        "{\n"
        "  \"nombre_microservicio\": \"Nombre inferred\",\n"
        "  \"resumen_arquitectura\": \"Breve resumen del bloque\",\n"
        "  \"puntos_criticos_seguridad\": [\n"
        "    {\n"
        "      \"archivo\": \"ruta/relativa/archivo.py\",\n"
        "      \"severidad\": \"Alta/Media/Baja\",\n"
        "      \"vulnerabilidad\": \"Descripción del problema solucionado o cambio hecho\",\n"
        "      \"solucion\": \"Explicación técnica del cambio de código\",\n"
        "      \"explicacion_sencilla\": \"Explicación clara y pedagógica en español para un desarrollador principiante indicando qué añadiste o cambiaste y por qué\",\n"
        "      \"requiere_parche\": true,\n"
        "      \"codigo_corregido_completo\": \"Contenido íntegro del nuevo archivo listo para guardarse\"\n"
        "    }\n"
        "  ],\n"
        "  \"calidad_codigo_score\": 90,\n"
        "  \"conclusiones_generales\": \"Comentarios\"\n"
        "}"
    )
    
    config = types.GenerateContentConfig(system_instruction=prompt_sistema, response_mime_type="application/json", temperature=0.2)

    # 🏎️ Velocidad Máxima: Lotes grandes de 15 archivos
    TAMANIO_LOTE = 15  
    lotes = [codigo_proyecto[i:i + TAMANIO_LOTE] for i in range(0, len(codigo_proyecto), TAMANIO_LOTE)]
    total_lotes = len(lotes)
    
    print(f"\n   📦 [Modo Veloz]: Proyecto dividido en {total_lotes} lotes de ({TAMANIO_LOTE} archivos máx).")
    
    reporte_consolidado = {
        "nombre_microservicio": os.environ.get("NOMBRE_MICROSERVICIO", "Microservicio"),
        "resumen_arquitectura": "", "puntos_criticos_seguridad": [], "calidad_codigo_score": 85, "conclusiones_generales": ""
    }
    
    scores = []
    lotes_ok = 0
    modelo_activo = 'gemini-2.5-flash'

    for index, lote in enumerate(lotes, 1):
        print(f"\n   🚀 [Lote {index}/{total_lotes}]: Enviando {len(lote)} archivos a Gemini...")
        enfoque_usuario = f"\n🎯 CAMBIOS/INSTRUCCIONES SOLICITADAS POR EL DESARROLLADOR:\n{cambios}" if cambios else ""
        contenido_usuario = f"Archivos del proyecto (Lote {index} de {total_lotes}):\n{json.dumps(lote, ensure_ascii=False)}{enfoque_usuario}"
        
        res = ejecutar_llamada_api(client, modelo_activo, contenido_usuario, config)
        if res:
            lotes_ok += 1
            puntos = res.get("puntos_criticos_seguridad", [])
            reporte_consolidado["puntos_criticos_seguridad"].extend(puntos)
            if "calidad_codigo_score" in res: scores.append(float(res["calidad_codigo_score"]))
        
        # ⏱️ Cooldown optimizado a 4.5 segundos para acortar tiempos drásticamente
        if index < total_lotes:
            print("   ⏳ Esperando 4.5 segundos de enfriamiento dinámico por RPM...")
            time.sleep(4.5)

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
        dir_salida = os.environ.get("DIR_SALIDA_JSON", ".")
        archivo_salida = os.path.join(dir_salida, f"{nombre_ms}_auditoria.json")
        
        try:
            with open(archivo_salida, "w", encoding="utf-8") as f:
                json.dump(informe_final, f, indent=4, ensure_ascii=False)
            print(f"✅ [Agente]: Reporte guardado en -> {archivo_salida}")
            
            # Encadenar ejecución con el reportero si existe
            if os.path.exists("reporter_agent.py"):
                entorno_reportero = os.environ.copy()
                entorno_reportero["ARCHIVO_JSON_ORIGEN"] = archivo_salida
                subprocess.run([sys.executable, "reporter_agent.py"], env=entorno_reportero, text=True, encoding='utf-8')
        except Exception:
            sys.exit(1)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()