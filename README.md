# Orquestador de Auditoría y Refactorización de Microservicios con IA

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?style=flat-square&logo=python)
![Google Gemini](https://img.shields.io/badge/Google%20Gemini-API-orange.svg?style=flat-square&logo=google)
![Git](https://img.shields.io/badge/Git-Control-red.svg?style=flat-square&logo=git)
![Spring Boot](https://img.shields.io/badge/Spring%20Boot-Java-green.svg?style=flat-square&logo=spring)

Herramienta potente y flexible diseñada para automatizar la auditoría de código, la detección de vulnerabilidades y la refactorización de microservicios utilizando la inteligencia artificial de Google Gemini. Este orquestador permite analizar proyectos existentes, aplicar mejoras sugeridas por la IA e incluso generar la estructura básica de nuevos microservicios.

## 🌟 Características Principales

*   **Análisis de Código con IA:** Utiliza Google Gemini para una auditoría profunda del código, identificando vulnerabilidades, malas prácticas y oportunidades de mejora.
*   **Refactorización y Aplicación Directa:** Capacidad para que la IA genere y aplique directamente los cambios sugeridos en los archivos del proyecto.
*   **Generación de Microservicios:** Crea la estructura básica de microservicios Java (Spring Boot, Maven, Swagger) listos para desarrollar.
*   **Soporte Multi-origen:** Analiza repositorios Git remotos (clonado automático) o carpetas locales.
*   **Modos de Operación:** Interactivo (menús guiados) y por línea de comandos (para automatización).
*   **Procesamiento Concurrente:** Soporte para auditar múltiples repositorios en paralelo, optimizando el tiempo.
*   **Informes Detallados:** Genera informes JSON con puntos críticos de seguridad, soluciones y explicaciones sencillas.
*   **Gestión de API Key:** Configuración sencilla y persistente de la Google Gemini API Key.
*   **Aplicación Interactiva de Cambios:** Permite revisar y aplicar selectivamente los cambios propuestos en un informe JSON.

## 🏗️ Arquitectura del Proyecto

El orquestador se compone de varios módulos que trabajan en conjunto:

*   **`orchestrator.py`**: El componente central que gestiona el flujo de trabajo. Se encarga de la interacción con el usuario, la configuración del entorno, el clonado/manejo de repositorios y la invocación de los agentes.
*   **`code_auditor_agent.py`**: El corazón de la inteligencia. Este script se comunica con la API de Google Gemini, le envía el código del proyecto en lotes y procesa las respuestas de la IA para generar informes de auditoría o aplicar refactorizaciones.
*   **`aplicar_json.py`**: Un script auxiliar que permite al usuario revisar de forma interactiva un informe JSON generado previamente y decidir qué cambios aplicar a los archivos del proyecto.
*   **`reporter_agent.py`**: Módulo encargado de leer los informes JSON de auditoría y presentar un resumen legible en la consola, destacando los puntos críticos encontrados.
*   **`generador_microservicio.py`**: Un script independiente que facilita la creación rápida de la estructura base de un microservicio Java (Spring Boot, Maven, Swagger).

## ⚙️ Prerrequisitos

Antes de ejecutar el orquestador, asegúrate de tener instalado lo siguiente:

*   **Python 3.8+**: El lenguaje principal del proyecto.
*   **Git**: Necesario para clonar repositorios remotos.
*   **Maven** (opcional): Requerido si planeas generar y construir microservicios Java.
*   **Docker** (opcional): Para construir y ejecutar los microservicios generados en contenedores.
*   **Google Gemini API Key**: Imprescindible para las funcionalidades de IA.

## 🚀 Instalación

1.  **Clonar el repositorio (si aplica):**
    ```bash
    git clone <URL_DE_TU_REPOSITORIO>
    cd <nombre_del_repositorio>
    ```

2.  **Instalar dependencias de Python:**
    ```bash
    pip install google-generativeai pydantic
    ```
    *Nota: `tkinter` suele venir preinstalado con Python o se instala vía el gestor de paquetes de tu sistema operativo (ej. `sudo apt-get install python3-tk` en Debian/Ubuntu).* 

## 🔑 Configuración de la Google Gemini API Key

La API Key es esencial para que la IA funcione. Puedes configurarla de varias maneras:

1.  **Modo Interactivo (Recomendado):** Ejecuta `python orchestrator.py` y selecciona la opción `3. Cambiar / Reemplazar la Gemini API Key actual`. El orquestador la guardará en un archivo `.env`.
2.  **Archivo `.env`:** Crea un archivo llamado `.env` en la raíz del proyecto con el siguiente contenido:
    ```
    GEMINI_API_KEY=TU_API_KEY_AQUI
    ```
3.  **Línea de Comandos:** Pasa la clave directamente al ejecutar el orquestador:
    ```bash
    python orchestrator.py --api-key TU_API_KEY_AQUI
    ```

## 📝 Uso

### 1. Ejecutar el Orquestador en Modo Interactivo

Esta es la forma más sencilla de empezar. Te guiará a través de las opciones:

```bash
python orchestrator.py
```

### 2. Auditoría de Código (Carpeta Local o Repositorio Git)

Para analizar un proyecto existente y generar un informe de auditoría:

*   **Auditar una carpeta local:**
    ```bash
    python orchestrator.py /ruta/a/tu/proyecto/local
    ```
*   **Auditar un repositorio Git remoto:**
    ```bash
    python orchestrator.py https://github.com/usuario/repo.git
    ```
*   **Especificar una rama (para Git):**
    ```bash
    python orchestrator.py https://github.com/usuario/repo.git#nombre-de-rama
    # O con el argumento --branch
    python orchestrator.py https://github.com/usuario/repo.git --branch develop
    ```

### 3. Implementar Cambios o Mejoras Específicas (Refactorización)

Para pedir a la IA que realice una refactorización o añada una funcionalidad específica:

```bash
python orchestrator.py /ruta/a/tu/proyecto -c "Optimizar los imports en todos los archivos Python y añadir logs de errores en funciones críticas."
```

La IA intentará aplicar estos cambios directamente en los archivos del proyecto. Se recomienda revisar los cambios manualmente después.

### 4. Aplicar Cambios desde un Informe JSON Existente (Interactivo)

Si ya tienes un informe JSON generado por una auditoría previa y quieres aplicar sus soluciones de forma selectiva:

1.  Ejecuta el orquestador en modo interactivo (`python orchestrator.py`).
2.  Selecciona la opción `3. Aplicar cambios desde un JSON existente (Interactivo)`.
3.  El orquestador te guiará para elegir el archivo JSON y te preguntará por cada cambio si deseas aplicarlo.

### 5. Generar un Nuevo Microservicio Java

Utiliza el script `generador_microservicio.py` para crear la estructura base de un microservicio Spring Boot:

```bash
python generador_microservicio.py MiNuevoMicroservicio ./mis_proyectos
```

Esto creará una carpeta `mis_proyectos/MiNuevoMicroservicio` con un proyecto Spring Boot, Maven, Swagger, y un Dockerfile básico.

**Comandos útiles después de generar un microservicio:**

*   **Ejecutar localmente (Maven):**
    ```bash
    cd ./mis_proyectos/MiNuevoMicroservicio
    mvn spring-boot:run
    ```
*   **Construir y ejecutar con Docker:**
    ```bash
    cd ./mis_proyectos/MiNuevoMicroservicio
    docker build -t mi-api-microservicio .
    docker run -p 8080:8080 mi-api-microservicio
    ```
*   **Acceder a Swagger UI:** `http://localhost:8080/swagger-ui.html`

### 6. Opciones Adicionales de Línea de Comandos

*   `-b`, `--branch <rama>`: Especifica la rama Git a clonar/checkout.
*   `-e`, `--existing <s|n|c>`: Acción para repositorios Git ya existentes (`s`=sobrescribir, `n`=no clonar de nuevo, `c`=continuar sin clonar).
*   `-j`, `--jobs <num>`: Número de repositorios a procesar en paralelo (por defecto: 1).
*   `--no-clear`: Evita limpiar la pantalla al iniciar el orquestador.

## 📊 Salida de Resultados

*   **Informes JSON:** Los resultados de las auditorías se guardan en la carpeta `json_output/` con nombres como `<nombre_microservicio>_auditoria.json`.
*   **Logs:** Todos los eventos y errores se registran en archivos `.log` dentro de la carpeta `logs/`.
*   **Cambios Directos:** Si se solicita una refactorización, la IA modificará directamente los archivos del proyecto.

---