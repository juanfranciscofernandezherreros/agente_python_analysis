"""
generar_springboot.py
----------------------------------------------------------------------------
Genera un proyecto Spring Boot 3 (Maven) con Lombok y MapStruct ya
configurados, y lo guarda en una carpeta que tú eliges.

Usa la API pública de Spring Initializr (https://start.spring.io) para crear
el esqueleto del proyecto, y luego parchea el pom.xml para:
  - Añadir la dependencia de MapStruct (Initializr no la trae por defecto).
  - Configurar el maven-compiler-plugin con los 'annotationProcessorPaths' en
    el orden correcto (lombok -> lombok-mapstruct-binding -> mapstruct), que
    es el requisito imprescindible para que Lombok y MapStruct no choquen
    entre sí al generar código (getters/setters vs. mappers) en tiempo de
    compilación.

USO INTERACTIVO (recomendado, abre selector de carpeta):
    python generar_springboot.py

USO POR ARGUMENTOS (sin preguntas, ideal para scripts/CI):
    python generar_springboot.py \
        --group-id com.miempresa \
        --artifact-id mi-servicio \
        --package com.miempresa.miservicio \
        --java 21 \
        --dependencias web,data-jpa,validation \
        --output-dir C:/Develop/mi-servicio \
        --sin-confirmar
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ Error: falta la librería 'requests'. Instálala con:")
    print("   pip install requests")
    sys.exit(1)

INITIALIZR_URL = "https://start.spring.io/starter.zip"

# Versiones de MapStruct / binding que se inyectan en el pom.xml.
# Actualízalas si en el futuro sale una versión más reciente.
MAPSTRUCT_VERSION = "1.6.3"
LOMBOK_MAPSTRUCT_BINDING_VERSION = "0.2.0"


# ============================================================
# SELECCIÓN DE CARPETA DESTINO (mismo patrón que orchestrator.py)
# ============================================================

def seleccionar_carpeta_con_tkinter() -> Optional[str]:
    """Abre un diálogo visual para elegir la carpeta destino.

    Import perezoso de tkinter: si no está disponible (servidor sin GUI),
    el script sigue funcionando en modo --output-dir por argumento.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("\n❌ No se pudo abrir el explorador (tkinter no disponible).")
        print("💡 Instala tkinter (p.ej. 'sudo apt install python3-tk') o usa --output-dir.")
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()

        print("\n🔍 Abriendo explorador de carpetas... (Busca la ventana si no la ves)")
        ruta = filedialog.askdirectory(title="📂 Elige la carpeta donde crear el proyecto Spring Boot")

        root.destroy()
        return ruta or None
    except Exception as e:
        print(f"\n❌ Error inesperado abriendo el explorador de archivos: {e}")
        return None


# ============================================================
# RECOGIDA DE DATOS DEL PROYECTO
# ============================================================

def pedir_si_falta(valor: Optional[str], pregunta: str, por_defecto: str) -> str:
    if valor:
        return valor
    entrada = input(f"👉 {pregunta} (Enter para '{por_defecto}'): ").strip()
    return entrada or por_defecto


def construir_parametros_interactivos(args: argparse.Namespace) -> dict:
    print("\n----------------------------------------------------")
    print("🌱 GENERADOR DE PROYECTOS SPRING BOOT 3 (Maven)")
    print("----------------------------------------------------")

    group_id = pedir_si_falta(args.group_id, "GroupId (ej. com.miempresa)", "com.example")
    artifact_id = pedir_si_falta(args.artifact_id, "ArtifactId / nombre del proyecto (ej. mi-servicio)", "demo")
    package_default = f"{group_id}.{artifact_id.replace('-', '')}"
    package_name = pedir_si_falta(args.package, "Package base", package_default)
    java_version = pedir_si_falta(args.java, "Versión de Java (17 / 21)", "17")

    if args.dependencias:
        dependencias = args.dependencias
    else:
        print("\n   Dependencias adicionales disponibles habitualmente: web, data-jpa, validation,")
        print("   security, actuator, postgresql, h2, mysql, devtools, cache, kafka...")
        entrada = input("👉 Dependencias extra separadas por comas (Enter para solo 'web'): ").strip()
        dependencias = entrada if entrada else "web"

    return {
        "group_id": group_id,
        "artifact_id": artifact_id,
        "package_name": package_name,
        "java_version": java_version,
        "dependencias": dependencias,
    }


# ============================================================
# GENERACIÓN DEL PROYECTO (Spring Initializr)
# ============================================================

def generar_proyecto_zip(params: dict, boot_version: Optional[str]) -> bytes:
    """Pide a start.spring.io el .zip del proyecto ya con lombok incluido."""
    dependencias = {d.strip() for d in params["dependencias"].split(",") if d.strip()}
    dependencias.add("lombok")  # Lombok siempre incluido: lo pediste explícitamente.

    query = {
        "type": "maven-project",
        "language": "java",
        "packaging": "jar",
        "javaVersion": params["java_version"],
        "groupId": params["group_id"],
        "artifactId": params["artifact_id"],
        "name": params["artifact_id"],
        "description": f"Proyecto {params['artifact_id']} generado con Spring Initializr",
        "packageName": params["package_name"],
        "dependencies": ",".join(sorted(dependencias)),
    }
    if boot_version:
        query["bootVersion"] = boot_version

    print(f"\n🌐 Solicitando proyecto a Spring Initializr...")
    print(f"   ↳ Dependencias: {', '.join(sorted(dependencias))} (+ MapStruct, añadido manualmente después)")

    respuesta = requests.get(INITIALIZR_URL, params=query, timeout=30)

    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Spring Initializr devolvió el código {respuesta.status_code}: {respuesta.text[:300]}"
        )

    return respuesta.content


def descomprimir_proyecto(contenido_zip: bytes, carpeta_destino: Path) -> Path:
    """Descomprime el zip. Si el zip trae una única carpeta raíz, aplana el resultado."""
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    zip_temporal = carpeta_destino / "_springboot_temp.zip"
    zip_temporal.write_bytes(contenido_zip)

    with zipfile.ZipFile(zip_temporal, "r") as zf:
        zf.extractall(carpeta_destino)

    zip_temporal.unlink()
    return carpeta_destino


# ============================================================
# PARCHEO DEL pom.xml: MAPSTRUCT + ORDEN DE ANNOTATION PROCESSORS
# ============================================================

def _insertar_antes_de(texto: str, marcador: str, bloque: str, descripcion: str) -> str:
    if marcador not in texto:
        print(f"   ⚠️ No se encontró '{marcador.strip()}' en el pom.xml. Omitiendo: {descripcion}.")
        return texto
    return texto.replace(marcador, bloque + marcador, 1)


def parchear_pom_con_mapstruct(pom_path: Path) -> None:
    """Añade la dependencia de MapStruct y configura el maven-compiler-plugin
    con los annotationProcessorPaths en el orden correcto:
    lombok -> lombok-mapstruct-binding -> mapstruct.
    """
    if not pom_path.exists():
        print(f"   ❌ No se encontró {pom_path}; no se puede añadir MapStruct automáticamente.")
        return

    texto = pom_path.read_text(encoding="utf-8")

    # 1) Propiedades de versión (si ya existe <properties>, insertamos dentro)
    propiedades_bloque = (
        f"\t\t<mapstruct.version>{MAPSTRUCT_VERSION}</mapstruct.version>\n"
        f"\t\t<lombok-mapstruct-binding.version>{LOMBOK_MAPSTRUCT_BINDING_VERSION}</lombok-mapstruct-binding.version>\n"
    )
    if "<properties>" in texto:
        texto = texto.replace("<properties>", "<properties>\n" + propiedades_bloque, 1)
    else:
        # No debería pasar en un pom de Initializr, pero por si acaso.
        bloque_properties = f"\t<properties>\n{propiedades_bloque}\t</properties>\n"
        texto = _insertar_antes_de(texto, "</project>", bloque_properties, "bloque <properties>")

    # 2) Dependencia de MapStruct
    dependencia_mapstruct = (
        "\t\t<dependency>\n"
        "\t\t\t<groupId>org.mapstruct</groupId>\n"
        "\t\t\t<artifactId>mapstruct</artifactId>\n"
        "\t\t\t<version>${mapstruct.version}</version>\n"
        "\t\t</dependency>\n"
    )
    texto = _insertar_antes_de(texto, "</dependencies>", dependencia_mapstruct, "dependencia de MapStruct")

    # 3) maven-compiler-plugin con annotationProcessorPaths en el orden correcto
    plugin_compilador = (
        "\t\t\t<plugin>\n"
        "\t\t\t\t<groupId>org.apache.maven.plugins</groupId>\n"
        "\t\t\t\t<artifactId>maven-compiler-plugin</artifactId>\n"
        "\t\t\t\t<configuration>\n"
        "\t\t\t\t\t<annotationProcessorPaths>\n"
        "\t\t\t\t\t\t<path>\n"
        "\t\t\t\t\t\t\t<groupId>org.projectlombok</groupId>\n"
        "\t\t\t\t\t\t\t<artifactId>lombok</artifactId>\n"
        "\t\t\t\t\t\t\t<version>${lombok.version}</version>\n"
        "\t\t\t\t\t\t</path>\n"
        "\t\t\t\t\t\t<path>\n"
        "\t\t\t\t\t\t\t<groupId>org.projectlombok</groupId>\n"
        "\t\t\t\t\t\t\t<artifactId>lombok-mapstruct-binding</artifactId>\n"
        "\t\t\t\t\t\t\t<version>${lombok-mapstruct-binding.version}</version>\n"
        "\t\t\t\t\t\t</path>\n"
        "\t\t\t\t\t\t<path>\n"
        "\t\t\t\t\t\t\t<groupId>org.mapstruct</groupId>\n"
        "\t\t\t\t\t\t\t<artifactId>mapstruct-processor</artifactId>\n"
        "\t\t\t\t\t\t\t<version>${mapstruct.version}</version>\n"
        "\t\t\t\t\t\t</path>\n"
        "\t\t\t\t\t</annotationProcessorPaths>\n"
        "\t\t\t\t</configuration>\n"
        "\t\t\t</plugin>\n"
    )
    texto = _insertar_antes_de(texto, "</plugins>", plugin_compilador, "configuración del compilador (Lombok + MapStruct)")

    pom_path.write_text(texto, encoding="utf-8")
    print("   ✅ pom.xml parcheado: dependencia de MapStruct + annotationProcessorPaths configurados.")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera un proyecto Spring Boot 3 (Maven) con Lombok y MapStruct."
    )
    parser.add_argument("--group-id", help="GroupId Maven (ej. com.miempresa)")
    parser.add_argument("--artifact-id", help="ArtifactId / nombre del proyecto")
    parser.add_argument("--package", help="Package base (por defecto se deriva de group-id + artifact-id)")
    parser.add_argument("--java", help="Versión de Java (17, 21...)")
    parser.add_argument("--dependencias", help="Dependencias extra de Initializr separadas por comas (no incluyas 'lombok', se añade siempre)")
    parser.add_argument("--boot-version", help="Versión concreta de Spring Boot (Enter/omitir = la recomendada por Initializr)")
    parser.add_argument("--output-dir", help="Carpeta destino. Si no se indica, se abre un selector visual.")
    parser.add_argument("--sin-confirmar", action="store_true", help="No pedir confirmación antes de generar (útil en scripts).")
    args = parser.parse_args()

    params = construir_parametros_interactivos(args)

    carpeta_destino_str = args.output_dir
    if not carpeta_destino_str:
        carpeta_destino_str = seleccionar_carpeta_con_tkinter()

    if not carpeta_destino_str:
        print("\n⏭️ No se seleccionó ninguna carpeta destino. Operación cancelada.")
        sys.exit(1)

    carpeta_proyecto = Path(carpeta_destino_str) / params["artifact_id"]

    print("\n----------------------------------------------------")
    print("📋 RESUMEN DEL PROYECTO A GENERAR")
    print("----------------------------------------------------")
    print(f"   GroupId:      {params['group_id']}")
    print(f"   ArtifactId:   {params['artifact_id']}")
    print(f"   Package:      {params['package_name']}")
    print(f"   Java:         {params['java_version']}")
    print(f"   Dependencias: {params['dependencias']} + lombok + mapstruct (manual)")
    print(f"   Carpeta:      {carpeta_proyecto}")
    print("----------------------------------------------------")

    if not args.sin_confirmar:
        confirmar = input("\n👉 ¿Generar el proyecto con estos datos? (S/N): ").strip().lower()
        if confirmar != "s":
            print("⏭️ Operación cancelada por el usuario.")
            sys.exit(0)

    if carpeta_proyecto.exists() and any(carpeta_proyecto.iterdir()):
        print(f"\n⚠️ La carpeta '{carpeta_proyecto}' ya existe y no está vacía.")
        confirmar_sobrescribir = input("👉 ¿Continuar y fusionar/sobrescribir su contenido? (S/N): ").strip().lower()
        if confirmar_sobrescribir != "s":
            print("⏭️ Operación cancelada por el usuario.")
            sys.exit(0)

    try:
        contenido_zip = generar_proyecto_zip(params, args.boot_version)
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error de red al contactar Spring Initializr: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n❌ {e}")
        sys.exit(1)

    print(f"\n📦 Descomprimiendo proyecto en: {carpeta_proyecto}")
    descomprimir_proyecto(contenido_zip, carpeta_proyecto)

    print("\n🛠️  Añadiendo MapStruct al pom.xml...")
    parchear_pom_con_mapstruct(carpeta_proyecto / "pom.xml")

    print("\n✅ ¡Proyecto generado con éxito!")
    print(f"   📂 Ubicación: {carpeta_proyecto.resolve()}")
    print("\n   Próximos pasos sugeridos:")
    print(f"     cd \"{carpeta_proyecto}\"")
    print("     mvn clean install")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️  Ejecución interrumpida por el usuario.")
        sys.exit(1)