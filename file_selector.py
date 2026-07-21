"""Selección visual de carpetas mediante un diálogo Tkinter."""

import os
import logging
from typing import Optional

from config import DIR_MICROSERVICES


def seleccionar_con_tkinter() -> Optional[str]:
    """Abre un diálogo visual forzando que empiece en la carpeta de microservicios."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        logging.error("❌ Error: Falla al cargar la interfaz gráfica (tkinter no disponible). Asegúrate de que tkinter esté instalado.")
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.focus_force()

        logging.info("🔍 Abriendo explorador de archivos para selección de carpeta...")

        # Forzamos a Tkinter a abrir siempre dentro de tu carpeta de proyectos
        ruta_inicial = os.path.abspath(DIR_MICROSERVICES)
        os.makedirs(ruta_inicial, exist_ok=True)

        ruta = filedialog.askdirectory(
            title="📂 ENTRA AQUÍ Y SELECCIONA EL MICROSERVICIO",
            initialdir=ruta_inicial  # <--- ESTO EVITA QUE SELECCIONE LA RAÍZ
        )

        root.destroy()
        if ruta:
            logging.info(f"Carpeta seleccionada vía Tkinter: {ruta}")
        else:
            logging.info("Selección de carpeta cancelada por el usuario.")
        return ruta or None
    except Exception as e:
        logging.error(f"❌ Error inesperado abriendo el explorador de archivos: {e}", exc_info=True)
        return None
