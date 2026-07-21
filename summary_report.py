"""Generación del resumen final de una ejecución del orquestador.

Al terminar un batch (secuencial o paralelo), agrega:
  - Los repos procesados con éxito (processed_repos_info)
  - Los repos fallidos (leyendo los *_fallo.json que deja logging_utils.registrar_fallo_json)
  - Duración total de la ejecución

Y escribe dos ficheros en DIR_HTML / DIR_JSON:
  - resumen_ejecucion.html  -> vista humana rápida
  - resumen_ejecucion.json  -> mismo contenido en crudo, para CI/CD u otras herramientas
"""

import os
import json
import glob
import logging
from datetime import datetime
from typing import List, Tuple

from config import DIR_HTML, DIR_JSON


def _leer_fallos_pendientes() -> List[dict]:
    """Lee todos los ficheros *_fallo.json generados durante la ejecución actual."""
    fallos = []
    for ruta in glob.glob(os.path.join(DIR_JSON, "*_fallo.json")):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = json.load(f)
                if isinstance(contenido, list):
                    fallos.extend(contenido)
                else:
                    fallos.append(contenido)
        except Exception as e:
            logging.warning(f"No se pudo leer el fichero de fallo '{ruta}': {e}")
    return fallos


def _construir_resumen(processed_repos_info: List[Tuple[str, str, str]],
                        repos_solicitados: List[str],
                        segundos_totales: float) -> dict:
    fallos = _leer_fallos_pendientes()
    nombres_ok = {nombre for nombre, _, _ in processed_repos_info}
    # Un fallo cuenta como tal solo si su repo no terminó también en processed_repos_info
    fallos_relevantes = [f for f in fallos if f.get("microservicio") not in nombres_ok]

    return {
        "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duracion_segundos": round(segundos_totales, 2),
        "total_solicitados": len(repos_solicitados),
        "total_exitosos": len(processed_repos_info),
        "total_fallidos": len(fallos_relevantes),
        "exitosos": [
            {"microservicio": nombre, "ruta_ejecucion": ruta, "origen": origen}
            for nombre, ruta, origen in processed_repos_info
        ],
        "fallidos": fallos_relevantes,
    }


def _renderizar_html(resumen: dict) -> str:
    filas_ok = "".join(
        f"<tr><td>{e['microservicio']}</td><td>{e['origen']}</td><td>{e['ruta_ejecucion']}</td></tr>"
        for e in resumen["exitosos"]
    ) or "<tr><td colspan='3'>Ninguno</td></tr>"

    filas_fallo = "".join(
        f"<tr><td>{f.get('microservicio', 'N/A')}</td>"
        f"<td>{f.get('etapa_fallida', 'N/A')}</td>"
        f"<td>{f.get('detalles_error', {}).get('mensaje', 'N/A')}</td></tr>"
        for f in resumen["fallidos"]
    ) or "<tr><td colspan='3'>Ninguno</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Resumen de ejecución - Orquestador</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f7f7f9; }}
  h1 {{ color: #222; }}
  .stats {{ display: flex; gap: 1rem; margin-bottom: 1.5rem; }}
  .card {{ background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .card b {{ font-size: 1.4rem; display: block; }}
  table {{ width: 100%; border-collapse: collapse; background: white; margin-bottom: 2rem; }}
  th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; font-size: 0.9rem; }}
  th {{ background: #eee; }}
  .ok {{ color: #1a7f37; }}
  .fail {{ color: #c02020; }}
</style>
</head>
<body>
  <h1>🏁 Resumen de ejecución del orquestador</h1>
  <p>Generado: {resumen['fecha_hora']} &nbsp;|&nbsp; Duración: {resumen['duracion_segundos']} s</p>
  <div class="stats">
    <div class="card">Solicitados<b>{resumen['total_solicitados']}</b></div>
    <div class="card">Exitosos<b class="ok">{resumen['total_exitosos']}</b></div>
    <div class="card">Fallidos<b class="fail">{resumen['total_fallidos']}</b></div>
  </div>

  <h2 class="ok">✅ Repositorios procesados con éxito</h2>
  <table>
    <tr><th>Microservicio</th><th>Origen</th><th>Ruta de ejecución</th></tr>
    {filas_ok}
  </table>

  <h2 class="fail">❌ Repositorios fallidos</h2>
  <table>
    <tr><th>Microservicio</th><th>Etapa fallida</th><th>Mensaje</th></tr>
    {filas_fallo}
  </table>
</body>
</html>
"""


def generar_resumen(processed_repos_info: List[Tuple[str, str, str]],
                     repos_solicitados: List[str],
                     segundos_totales: float) -> str:
    """Genera resumen_ejecucion.html y resumen_ejecucion.json y devuelve la ruta del HTML."""
    resumen = _construir_resumen(processed_repos_info, repos_solicitados, segundos_totales)

    os.makedirs(DIR_HTML, exist_ok=True)
    os.makedirs(DIR_JSON, exist_ok=True)

    ruta_json = os.path.join(DIR_JSON, "resumen_ejecucion.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=4, ensure_ascii=False)

    ruta_html = os.path.join(DIR_HTML, "resumen_ejecucion.html")
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(_renderizar_html(resumen))

    logging.info(f"📊 Resumen de ejecución generado: {ruta_html} (y {ruta_json})")
    return ruta_html
