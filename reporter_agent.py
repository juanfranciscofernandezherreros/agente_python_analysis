import os
import sys
import json
from pathlib import Path


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

    # Mostrar el resumen de la auditoría / cambios generados en la terminal
    print("\n" + "=" * 60)
    print(" 📋 RESULTADOS DE LA AUDITORÍA / CAMBIOS")
    print("=" * 60)

    for idx, punto in enumerate(puntos, 1):
        archivo = punto.get('archivo', 'Desconocido')
        vuln = punto.get('vulnerabilidad', 'Sin descripción')
        sev = punto.get('severidad', 'N/A')
        tiene_codigo = bool(punto.get('codigo_corregido_completo'))

        icono = "🔴" if sev.lower() == "alta" else "🟠" if sev.lower() == "media" else "🟢"
        estado = "✍️ código generado y escrito en disco" if tiene_codigo else "ℹ️ solo observación"

        print(f" [{idx}] {icono} {sev.upper()} | Archivo: {archivo} | {estado}")
        print(f"     ↳ {vuln}")
        print("-" * 60)

    print(f"\n✅ [Reportero] {len(puntos)} punto(s) reportado(s). Revisa el detalle completo en: {archivo_json}")


if __name__ == "__main__":
    main()
