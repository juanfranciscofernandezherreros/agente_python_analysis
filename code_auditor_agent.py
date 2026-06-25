import os
import sys
import json
import time
import subprocess 
from datetime import datetime
import warnings

# Silenciar las advertencias de versiones antiguas de Python
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError:
    print("❌ [Agente] Error: La librería 'google-genai' es requerida.")
    print("💡 Instálala ejecutando: pip install google-genai")
    sys.exit(1)

def extraer_codigo_base(target_path):
    """Escanea recursivamente el directorio para extraer el contenido de los archivos."""
    extensiones_validas = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', 
        '.java', '.c', '.cpp', '.cs', '.go', '.php', '.rb', 
        '.sh', '.json', '.yml', '.yaml', '.sql', '.dockerfile', 'Dockerfile'
    }
    directorios_ignorados = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', 'dist', 'build'}
    
    codigo_empaquetado = []
    print(f"   ↳ [Agente]: Extrayendo archivos desde {target_path}...")

    for raiz, directorios, archivos in os.walk(target_path):
        directorios[:] = [d for d in directorios if d not in directorios_ignorados]
        for archivo in archivos:
            _, ext = os.path.splitext(archivo)
            if ext.lower() in extensiones_validas or archivo in extensiones_validas:
                ruta_completa = os.path.join(raiz, archivo)
                ruta_relativa = os.path.relpath(ruta_completa, target_path)
                
                try:
                    with open(ruta_completa, 'r', encoding='utf-8', errors='ignore') as f:
                        contenido = f.read()
                    codigo_empaquetado.append({
                        "archivo": ruta_relativa,
                        "contenido": contenido
                    })
                except Exception as e:
                    print(f"   ⚠️ [Agente] Error leyendo {ruta_relativa}: {str(e)}")
                    
    return codigo_empaquetado

def analizar_con_gemini_robusto(codigo_proyecto):
    """Realiza la petición utilizando una lista de modelos como respaldo (Fallback)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ [Agente] Error crítico: No se heredó la variable 'GEMINI_API_KEY'.")
        return None
        
    client = genai.Client(api_key=api_key)
    
    prompt_sistema = (
        "Eres un auditor senior de seguridad de aplicaciones y experto en arquitectura de microservicios. "
        "Analiza el código provisto y genera un informe técnico detallado. "
        "DEBES responder EXCLUSIVAMENTE con un objeto JSON válido que siga esta estructura exacta:\n"
        "{\n"
        "  \"nombre_microservicio\": \"Nombre o inferencia del servicio\",\n"
        "  \"resumen_arquitectura\": \"Descripción de la arquitectura y tecnologías detectadas\",\n"
        "  \"puntos_criticos_seguridad\": [\n"
        "    {\"archivo\": \"ruta/al/archivo\", \"severidad\": \"Alta/Media/Baja\", \"vulnerabilidad\": \"Descripción\", \"solucion\": \"Parche recomendado\"}\n"
        "  ],\n"
        "  \"calidad_codigo_score\": 85,\n"
        "  \"conclusiones_generales\": \"Recomendaciones finales\"\n"
        "}"
    )
    
    config = types.GenerateContentConfig(
        system_instruction=prompt_sistema,
        response_mime_type="application/json",
        temperature=0.2
    )
    
    contenido_usuario = f"Código fuente del repositorio a auditar:\n{json.dumps(codigo_proyecto, ensure_ascii=False)}"
    
    modelos_candidatos = [
        'gemini-2.5-pro',
        'gemini-2.5-flash',
        'gemini-2.0-pro-exp',
        'gemini-2.0-flash',
        'gemini-1.5-pro',
        'gemini-1.5-flash',
        'gemini-1.5-flash-8b'
    ]
    
    max_reintentos_por_modelo = 2

    for modelo in modelos_candidatos:
        print(f"\n   ↳ [Agente]: Intentando auditar con el modelo [{modelo}]...")
        
        for intento in range(1, max_reintentos_por_modelo + 1):
            try:
                respuesta = client.models.generate_content(
                    model=modelo,
                    contents=contenido_usuario,
                    config=config
                )
                print(f"   ✅ [Agente]: ¡Éxito usando {modelo}!")
                return json.loads(respuesta.text)
                
            except APIError as e:
                print(f"   ⚠️ [Intento {intento}/{max_reintentos_por_modelo}] Error API con {modelo}: {e.message}")
                if intento < max_reintentos_por_modelo:
                    print("   ⏳ Esperando 5 segundos antes de reintentar...")
                    time.sleep(5)
            except Exception as e:
                print(f"   ⚠️ Error inesperado evaluando {modelo}: {str(e)}")
                break
                
        print(f"   ⏭️  [Agente]: El modelo [{modelo}] falló. Pasando al siguiente de la lista...")

    print("\n❌ [Agente]: Fallo total. Todos los modelos han fallado o están saturados.")
    return None

def main():
    if len(sys.argv) < 2:
        print("❌ [Agente] Error: No se especificó la ruta objetivo por parámetro.")
        sys.exit(1)
        
    target_path = sys.argv[1]
    
    if not os.path.isdir(target_path):
        print(f"❌ [Agente] Error: La ruta '{target_path}' no es un directorio válido.")
        sys.exit(1)
        
    codigo_proyecto = extraer_codigo_base(target_path)
    if not codigo_proyecto:
        print("❌ [Agente] Error: No hay archivos de código legibles en la ruta.")
        sys.exit(1)
        
    print(f"   ↳ [Agente]: {len(codigo_proyecto)} archivos empaquetados para la auditoría.")
    
    # 1. Analizar
    informe_final = analizar_con_gemini_robusto(codigo_proyecto)
    
    if informe_final:
        # 2. Rescatar variables de entorno inyectadas por el orquestador
        nombre_microservicio = os.environ.get("NOMBRE_MICROSERVICIO", "microservicio_desconocido")
        dir_salida_json = os.environ.get("DIR_SALIDA_JSON", ".")
        
        # 3. Exportar usando la estructura de carpetas correcta
        archivo_salida = os.path.join(dir_salida_json, f"{nombre_microservicio}_auditoria.json")
        
        try:
            with open(archivo_salida, "w", encoding="utf-8") as f:
                json.dump(informe_final, f, indent=4, ensure_ascii=False)
            print(f"✅ [Agente]: Reporte exportado exitosamente en -> {archivo_salida}")
            
            # 4. INVOCAR AL SIGUIENTE AGENTE (Reportero)
            print("🚀 [Agente Auditor]: Transfiriendo ejecución al Agente Reportero...")
            
            # Pasamos las mismas variables al reportero
            entorno_reportero = os.environ.copy()
            entorno_reportero["ARCHIVO_JSON_ORIGEN"] = archivo_salida
            
            subprocess.run([sys.executable, "reporter_agent.py"], env=entorno_reportero, text=True, encoding='utf-8')

        except Exception as e:
            print(f"❌ [Agente] Error guardando JSON o llamando al reportero: {str(e)}")
            sys.exit(1)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()