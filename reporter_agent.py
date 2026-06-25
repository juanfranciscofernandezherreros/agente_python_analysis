import os
import sys
import json
from datetime import datetime
import warnings

# Silenciar las advertencias de versiones antiguas de Python
warnings.filterwarnings("ignore", category=FutureWarning)

def generar_plantilla_html(datos, nombre_microservicio):
    """Genera un reporte HTML responsivo utilizando Bootstrap 5."""
    
    # Extraemos los datos con valores por defecto
    resumen = datos.get("resumen_arquitectura", "No hay resumen disponible.")
    score = datos.get("calidad_codigo_score", "N/A")
    conclusiones = datos.get("conclusiones_generales", "Sin conclusiones finales.")
    puntos_criticos = datos.get("puntos_criticos_seguridad", [])

    # Determinamos el color del score (Clases de Bootstrap)
    bg_score_class = "bg-success" if isinstance(score, int) and score >= 80 else ("bg-warning text-dark" if isinstance(score, int) and score >= 60 else "bg-danger")

    # Construimos las filas de la tabla de vulnerabilidades
    filas_tabla = ""
    if puntos_criticos:
        for punto in puntos_criticos:
            severidad = punto.get("severidad", "Desconocida")
            # Clases de badges de Bootstrap según la severidad
            badge_class = "bg-danger" if severidad.lower() == "alta" else ("bg-warning text-dark" if severidad.lower() == "media" else "bg-info text-dark")
            
            filas_tabla += f"""
            <tr>
                <td class="text-break"><code class="text-pink">{punto.get("archivo", "N/A")}</code></td>
                <td class="text-center align-middle"><span class="badge {badge_class} rounded-pill px-3 py-2">{severidad.upper()}</span></td>
                <td>{punto.get("vulnerabilidad", "N/A")}</td>
                <td>{punto.get("solucion", "N/A")}</td>
            </tr>
            """
    else:
        filas_tabla = """
        <tr>
            <td colspan='4' class='text-center text-muted py-4'>
                <i class="bi bi-shield-check fs-2 text-success d-block mb-2"></i>
                No se detectaron puntos críticos de seguridad. ¡Excelente! 🎉
            </td>
        </tr>
        """

    # HTML Base inyectando Bootstrap 5 vía CDN
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Auditoría - {nombre_microservicio}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        body {{ background-color: #f4f6f9; }}
        .text-pink {{ color: #d63384; }}
        .score-card {{
            min-width: 120px;
            text-align: center;
        }}
    </style>
</head>
<body class="py-5">

    <div class="container">
        
        <div class="card shadow-sm border-0 border-start border-primary border-5 mb-4">
            <div class="card-body d-flex flex-column flex-md-row justify-content-between align-items-md-center p-4">
                <div>
                    <h1 class="display-6 fw-bold text-primary mb-1">
                        <i class="bi bi-shield-lock me-2"></i>Reporte de Auditoría de Código
                    </h1>
                    <p class="text-muted mb-1 fs-5"><strong>Microservicio:</strong> {nombre_microservicio}</p>
                    <p class="text-muted mb-0 small"><i class="bi bi-clock me-1"></i>Fecha de escaneo: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                </div>
                
                <div class="score-card mt-3 mt-md-0 ms-md-4 p-3 rounded-3 shadow-sm text-white {bg_score_class}">
                    <div class="display-5 fw-bold mb-0">{score}</div>
                    <div class="text-uppercase small fw-semibold" style="letter-spacing: 1px; opacity: 0.9;">Score Calidad</div>
                </div>
            </div>
        </div>

        <div class="card shadow-sm border-0 mb-4">
            <div class="card-header bg-white py-3">
                <h3 class="h5 mb-0 text-secondary"><i class="bi bi-diagram-3 me-2"></i>Resumen de Arquitectura</h3>
            </div>
            <div class="card-body">
                <p class="card-text text-secondary lh-lg">{resumen}</p>
            </div>
        </div>

        <div class="card shadow-sm border-0 mb-4">
            <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center">
                <h3 class="h5 mb-0 text-danger"><i class="bi bi-exclamation-triangle me-2"></i>Puntos Críticos de Seguridad</h3>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-hover table-striped align-middle mb-0">
                        <thead class="table-light text-secondary">
                            <tr>
                                <th scope="col" class="ps-4">Archivo Afectado</th>
                                <th scope="col" class="text-center">Severidad</th>
                                <th scope="col">Vulnerabilidad</th>
                                <th scope="col" class="pe-4">Solución Recomendada</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filas_tabla}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="card shadow-sm border-0 mb-4">
            <div class="card-header bg-white py-3">
                <h3 class="h5 mb-0 text-success"><i class="bi bi-lightbulb me-2"></i>Conclusiones y Recomendaciones</h3>
            </div>
            <div class="card-body">
                <p class="card-text text-secondary lh-lg">{conclusiones}</p>
            </div>
        </div>

        <footer class="text-center text-muted mt-5 mb-3">
            <small>Generado automáticamente por el Pipeline de Auditoría de IA &middot; Bootstrap 5</small>
        </footer>

    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" integrity="sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL" crossorigin="anonymous"></script>
</body>
</html>
    """
    return html

def main():
    # 1. Recuperar variables de entorno inyectadas por el Orquestador/Auditor
    archivo_json = os.environ.get("ARCHIVO_JSON_ORIGEN")
    dir_salida_html = os.environ.get("DIR_SALIDA_HTML", "html_output")
    nombre_microservicio = os.environ.get("NOMBRE_MICROSERVICIO", "microservicio_desconocido")

    print(f"   ↳ [Reportero]: Iniciando generación de reporte para '{nombre_microservicio}'...")

    if not archivo_json or not os.path.exists(archivo_json):
        print(f"❌ [Reportero] Error: No se encontró el archivo JSON origen en la ruta: {archivo_json}")
        sys.exit(1)

    # 2. Leer el JSON generado por Gemini
    try:
        with open(archivo_json, "r", encoding="utf-8") as f:
            datos_auditoria = json.load(f)
    except Exception as e:
        print(f"❌ [Reportero] Error al leer o parsear el JSON de origen: {str(e)}")
        sys.exit(1)

    # 3. Generar el HTML
    try:
        contenido_html = generar_plantilla_html(datos_auditoria, nombre_microservicio)
    except Exception as e:
        print(f"❌ [Reportero] Error crítico al estructurar el HTML: {str(e)}")
        sys.exit(1)

    # 4. Guardar en la carpeta html_output/
    os.makedirs(dir_salida_html, exist_ok=True)
    
    ruta_html = os.path.join(dir_salida_html, f"{nombre_microservicio}_reporte.html")

    try:
        with open(ruta_html, "w", encoding="utf-8") as f:
            f.write(contenido_html)
        print(f"   ✅ [Reportero]: ¡Reporte visual generado con éxito en -> {ruta_html}")
    except Exception as e:
        print(f"❌ [Reportero] Error al guardar el archivo HTML: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()