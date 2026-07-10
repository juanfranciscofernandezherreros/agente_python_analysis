import os
import sys
import json
from pathlib import Path

def limpiar_codigo_markdown(texto_crudo):
    """Elimina las etiquetas Markdown (```python ... ```) que la IA suele añadir."""
    if not texto_crudo:
        return ""
        
    lineas = texto_crudo.strip().split('\n')
    if lineas[0].startswith('```'):
        lineas = lineas[1:]
    if lineas and lineas[-1].startswith('```'):
        lineas = lineas[:-1]
        
    return '\n'.join(lineas).strip()

def main():
    archivo_json = os.environ.get("ARCHIVO_JSON_ORIGEN")
    
    if not archivo_json or not Path(archivo_json).exists():
        print("❌ [Reportero] Error: No se encontró el archivo JSON de origen.")
        sys.exit(1)
        
    with open(archivo_json, 'r', encoding='utf-8') as f:
        try:
            datos = json.load(f)
        except json.JSONDecodeError:
            print("❌ [Reportero] Error: El archivo JSON no tiene un formato válido.")
            sys.exit(1)
            
    puntos = datos.get("puntos_criticos_seguridad", [])
    if not puntos:
        print("✅ [Reportero] La auditoría finalizó limpiamente. No se encontraron vulnerabilidades.")
        sys.exit(0)
    
    # 1. MOSTRAR EL MENÚ INTERACTIVO EN LA TERMINAL
    print("\n" + "="*60)
    print(" 📋 RESULTADOS DE LA AUDITORÍA ENCONTRADOS")
    print("="*60)
    
    for idx, punto in enumerate(puntos, 1):
        archivo = punto.get('archivo', 'Desconocido')
        vuln = punto.get('vulnerabilidad', 'Sin descripción')
        sev = punto.get('severidad', 'N/A')
        
        # Asignar un color visual básico según severidad (ideal para la terminal)
        icono = "🔴" if sev.lower() == "alta" else "🟠" if sev.lower() == "media" else "🟢"
        
        print(f" [{idx}] {icono} {sev.upper()} | Archivo: {archivo}")
        print(f"     ↳ {vuln}")
        print("-" * 60)

    # 2. CAPTURAR LA SELECCIÓN DEL USUARIO
    print("\n👉 ¿Qué modificaciones deseas extraer como parches?")
    respuesta = input("   Escribe los números (ej. 1, 3), 'todos', o pulsa Enter para salir: ").strip().lower()
    
    seleccionados = []
    if respuesta == 'todos':
        seleccionados = puntos
    elif respuesta:
        try:
            # Convierte la entrada "1, 3" en una lista de índices válidos
            indices = [int(x.strip()) for x in respuesta.split(',') if x.strip().isdigit()]
            seleccionados = [puntos[i-1] for i in indices if 1 <= i <= len(puntos)]
        except Exception:
            print("⚠️ [Reportero] Selección no válida. Saliendo sin extraer parches...")
            sys.exit(1)

    if not seleccionados:
        print("ℹ️ [Reportero] No se seleccionó ningún parche. Operación finalizada.")
        sys.exit(0)

    # 3. EXTRAER SOLO LOS PARCHES SELECCIONADOS
    dir_parches = Path("parches_propuestos")
    dir_parches.mkdir(exist_ok=True)
    modificaciones_extraidas = 0
    
    print("\n   ⚙️  Extrayendo código...")
    
    # Recorremos la lista original para mantener la numeración real de los archivos
    for idx_original, punto in enumerate(puntos, 1):
        if punto not in seleccionados:
            continue
            
        archivo_destino = punto.get("archivo", f"archivo_desconocido_{idx_original}")
        codigo_parche = punto.get("codigo_corregido_completo") or punto.get("parche_diff")
        
        if codigo_parche:
            ruta_original = Path(archivo_destino)
            codigo_limpio = limpiar_codigo_markdown(codigo_parche)
            
            if codigo_limpio:
                nombre_parche = f"{ruta_original.stem}_parche_{idx_original}{ruta_original.suffix}"
                ruta_parche_final = dir_parches / nombre_parche
                
                with open(ruta_parche_final, "w", encoding="utf-8") as f:
                    f.write(codigo_limpio)
                
                print(f"   ✅ Guardado: {nombre_parche}")
                modificaciones_extraidas += 1
            else:
                print(f"   ⚠️ El punto [{idx_original}] no contenía código extraíble válido.")
        else:
            print(f"   ℹ️ El punto [{idx_original}] es solo una advertencia, no tiene parche de código.")

    if modificaciones_extraidas > 0:
        print(f"\n✅ [Reportero] Proceso completado. {modificaciones_extraidas} parches listos en la carpeta '{dir_parches}/'.")
    else:
        print("\n⚠️ [Reportero] Ninguno de los elementos seleccionados contenía un parche de código aplicable.")

if __name__ == "__main__":
    main()