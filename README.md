# Orquestador de Auditoría de Código con Google Gemini

Este script automatiza la preparación, clonación y actualización de repositorios de código (microservicios) para su posterior análisis utilizando un agente auditor integrado (`code_auditor_agent.py`) potenciado por la IA de Google Gemini.

## 🚀 Características

* **Gestión de API Key Persistente:** Solicita la clave de Gemini la primera vez y la guarda localmente en un archivo oculto (`.gemini_key`) para no tener que volver a escribirla.
* **Menú de Configuración:** Permite restablecer o cambiar la clave directamente desde el menú interactivo.
* **Clonación Organizada:** Descarga los repositorios remotos dentro de una subcarpeta específica con el nombre del proyecto bajo el directorio raíz `microservices/`.
* **Soporte de Ramas (Branches):** Permite especificar qué rama clonar o auditar usando la nomenclatura `repo#rama`.
* **Doble Modo de Ejecución:** Funciona mediante un menú interactivo guiado o directamente mediante comandos de consola (argumentos CLI).

---

## 🛠️ Prerrequisitos

Antes de ejecutar el orquestador, asegúrate de contar con lo siguiente en tu entorno (Linux):

* **Python 3.x** instalado.
* **Git** configurado en la terminal.
* El script del auditor (`code_auditor_agent.py`) ubicado en la misma carpeta raíz que este orquestador.

---

## 💻 Modos de Uso

### 1. Ejecución con Argumentos (Modo CLI)
Puedes saltarte los menús de selección de proyectos pasando las rutas locales o URLs de Git directamente como argumentos en la terminal. El script detectará los argumentos y procesará la lista de inmediato.

* **Auditar un repositorio remoto en su rama por defecto:**
  ```bash
python orchestrator.py https://gitlab.six-group.net/six/rftemir/rft/components/backend/rft-observability/rft-observability-item33-creator.git -k "xxxxx" -b main -e s