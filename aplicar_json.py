import json
import os

def limpiar_markdown(texto: str) -> str:
    """Limpia las comillas invertidas (```python) que suele poner Gemini."""
    if not texto: return ""
    lineas = texto.strip().split("\n")
    if lineas and lineas[0].startswith("```"): lineas = lineas[1:]
    if lineas and lineas[-1].startswith("```"): lineas = lineas[:-1]
    return "\n".join(lineas).strip()

def seleccionar_archivo_y_carpeta():
    """Usa Tkinter para que el usuario seleccione visualmente qué aplicar y dónde."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        print("\n1️⃣ Abriendo explorador... Selecciona el archivo JSON de la auditoría.")
        ruta_json = filedialog.askopenfilename(
            title="1. Selecciona el archivo JSON", 
            filetypes=[("Archivos JSON", "*.json")]
        )
        
        if not ruta_json:
            return None, None

        print("2️⃣ Abriendo explorador... Selecciona la carpeta del proyecto a modificar.")
        ruta_proyecto = filedialog.askdirectory(
            title="2. Selecciona la carpeta destino (La misma del Paso 1 del orquestador)"
        )
        
        root.destroy()
        return ruta_json, ruta_proyecto
    except ImportError:
        print("❌ Error: La librería gráfica Tkinter no está disponible.")
        return None, None

def main():
    ruta_json, ruta_proyecto = seleccionar_archivo_y_carpeta()
    
    if not ruta_json or not ruta_proyecto:
        print("⏭️ Operación cancelada por el usuario.")
        return

    print(f"\n📄 JSON cargado: {os.path.basename(ruta_json)}")
    print(f"📂 Carpeta destino: {ruta_proyecto}")

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
            # Limpiamos barras invertidas por si venimos de Windows/Linux cruzado
            archivo_limpio = archivo.replace("\\", "/").lstrip("/")
            
            # Si Gemini incluyó la carpeta raíz en el nombre, la quitamos
            nombre_carpeta = os.path.basename(ruta_proyecto)
            if archivo_limpio.startswith(f"{nombre_carpeta}/"):
                archivo_limpio = archivo_limpio[len(nombre_carpeta)+1:]

            ruta_absoluta = os.path.join(ruta_proyecto, archivo_limpio)
            
            try:
                # Creamos las subcarpetas si no existen
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