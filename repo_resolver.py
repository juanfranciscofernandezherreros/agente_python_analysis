"""Utilidades para resolver nombre, rama y ruta destino de un repo/carpeta local."""

import os
import logging
from typing import Optional, Tuple

from config import DIR_MICROSERVICES


def sanitizar_nombre_repo(nombre: str) -> str:
    """Evita que un nombre de repo con '..' o separadores de ruta escape del directorio destino."""
    nombre = nombre.strip().replace("\\", "/").split("/")[-1]
    nombre = nombre.replace("..", "_").strip() or "repo_sin_nombre"
    logging.debug(f"Nombre de repositorio sanitizado a: '{nombre}'")
    return nombre


def resolver_nombre_y_ruta(url_o_ruta_completa: str) -> Tuple[str, str, str, Optional[str]]:
    """Dado 'repo#rama' o una ruta local, devuelve:
    (nombre_repo, url_o_ruta_sin_rama, carpeta_destino, rama)
    """
    if "#" in url_o_ruta_completa:
        url_o_ruta, rama = url_o_ruta_completa.split("#", 1)
        logging.debug(f"URL/Ruta '{url_o_ruta_completa}' contiene rama: '{rama}'")
    else:
        url_o_ruta, rama = url_o_ruta_completa, None
        logging.debug(f"URL/Ruta '{url_o_ruta_completa}' no contiene rama explícita.")

    if url_o_ruta.startswith("http"):
        nombre_repo = sanitizar_nombre_repo(url_o_ruta.split("/")[-1].replace(".git", ""))
        carpeta_destino = os.path.join(DIR_MICROSERVICES, nombre_repo)
        logging.debug(f"Origen remoto: '{url_o_ruta}', Nombre: '{nombre_repo}', Destino: '{carpeta_destino}'")
    else:
        nombre_repo = sanitizar_nombre_repo(os.path.basename(os.path.normpath(url_o_ruta)))
        carpeta_destino = url_o_ruta
        logging.debug(f"Origen local: '{url_o_ruta}', Nombre: '{nombre_repo}', Destino: '{carpeta_destino}'")

    return nombre_repo, url_o_ruta, carpeta_destino, (rama or None)
