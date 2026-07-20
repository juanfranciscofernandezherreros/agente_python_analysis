import json
import os
import argparse

def limpiar_markdown(texto: str) -> str:
    """Limpia las comillas invertidas que suele poner Gemini."""
    if not texto: return ""
    lineas = texto.strip().split("\n")
    if lineas and lineas[0].startswith("```"): lineas = lineas[1:]
    if lineas and lineas[-1].startswith("```"): lineas = lineas[:-1]
    return "\n".join(lineas).strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proyecto", type=str, required=True, help="Carpeta destino del proyecto")
    parser.add_argument("--json", type=str, required=True, help="Archivo JSON con los cambios")
    args = parser.parse_args()

    ruta_proyecto = args.proyecto
    ruta_json = args.json

    if not os.path.exists(ruta_json):
        print(f"\n❌ No se encuentra el archivo JSON: {ruta_json}")
        print("⚠️ Asegúrate de haber ejecutado una 'Auditoría general' primero para generar este reporte.")
        return

    print(f"\n📄 JSON cargado automáticamente: {os.path.basename(ruta_json)}")
    print(f"📂 Carpeta destino confirmada: {ruta_proyecto}")

    with open(ruta_json, "r", encoding="utf-8") as f:
        datos = json.load(f)

    puntos = datos.get("puntos_criticos_seguridad", [])
    if not puntos:
        print("ℹ️ No hay puntos críticos en el JSON.")
        return

    print("\n🛠️ MODO DE IMPLEMENTACIÓN SELECTIVA")
    archivos_modificados = 0

    for idx, punto in enumerate(puntos, 1):
        archivo = punto.get("archivo", "")
        codigo_nuevo = punto.get("codigo_corregido_completo", "")
        vuln = punto.get("vulnerabilidad", "Sin descripción")
        sev = punto.get("severidad", "N/A").upper()

        if not archivo or not codigo_nuevo.strip():
            continue

        print("-" * 60)
        print(f"[{idx}/{len(puntos)}] 📝 ARCHIVO: {archivo}")
        print(f" ⚠️  SEVERIDAD: {sev}")
        print(f" 🔍 MOTIVO: {vuln}")
        print("-" * 60)
        
        respuesta = input("👉 ¿Quieres sobrescribir este archivo? (s/n): ").strip().lower()

        if respuesta == 's':
            archivo_limpio = archivo.replace("\\", "/").lstrip("/")
            nombre_carpeta = os.path.basename(ruta_proyecto)
            
            if archivo_limpio.startswith(f"{nombre_carpeta}/"):
                archivo_limpio = archivo_limpio[len(nombre_carpeta)+1:]

            ruta_absoluta = os.path.join(ruta_proyecto, archivo_limpio)
            
            try:
                os.makedirs(os.path.dirname(ruta_absoluta), exist_ok=True)
                codigo_limpio = limpiar_markdown(codigo_nuevo)
                with open(ruta_absoluta, "w", encoding="utf-8") as f_out:
                    f_out.write(codigo_limpio)
                print(f"  ✅ ¡Aplicado! {archivo_limpio} actualizado.")
                archivos_modificados += 1
            except Exception as e:
                print(f"  ❌ Error al escribir {archivo_limpio}: {e}")
        else:
            print("  ⏭️ Cambio omitido.")

    print(f"\n🏁 Proceso finalizado. {archivos_modificados} archivo(s) modificado(s).")

if __name__ == "__main__":
    main()