import os
import sys

def generar_microservicio(nombre: str, directorio_base: str) -> None:
    """Genera la estructura básica de un microservicio Java (Spring Boot + Maven + Swagger)."""
    ruta_completa = os.path.join(directorio_base, nombre)
    
    # Estructura de paquetes: src/main/java/com/example/microservicio
    ruta_java = os.path.join(ruta_completa, "src", "main", "java", "com", "example", "microservicio")
    ruta_resources = os.path.join(ruta_completa, "src", "main", "resources")
    
    os.makedirs(ruta_java, exist_ok=True)
    os.makedirs(ruta_resources, exist_ok=True)

    # 1. Crear el pom.xml (Configuración de Maven)
    codigo_pom = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.4</version>
        <relativePath/> <!-- lookup parent from repository -->
    </parent>
    
    <groupId>com.example</groupId>
    <artifactId>{nombre}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>{nombre}</name>
    <description>Microservicio Hello World generado por IA</description>
    
    <properties>
        <java.version>17</java.version>
    </properties>
    
    <dependencies>
        <!-- Spring Boot Web para la API REST -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <!-- SpringDoc OpenAPI para autogenerar Swagger -->
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.4.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""
    with open(os.path.join(ruta_completa, "pom.xml"), "w", encoding="utf-8") as f:
        f.write(codigo_pom)

    # 2. Crear la clase principal de Spring Boot
    codigo_application = """package com.example.microservicio;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""
    with open(os.path.join(ruta_java, "Application.java"), "w", encoding="utf-8") as f:
        f.write(codigo_application)

    # 3. Crear el Controlador REST con anotaciones de Swagger
    codigo_controller = f"""package com.example.microservicio;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
@Tag(name = "Hello API", description = "Endpoints básicos del microservicio")
public class HelloController {{

    @GetMapping("/")
    @Operation(summary = "Devuelve un saludo", description = "Endpoint principal de Hello World")
    public Map<String, String> hello() {{
        return Map.of(
            "mensaje", "Hello World",
            "microservicio", "{nombre}"
        );
    }}

    @GetMapping("/health")
    @Operation(summary = "Health Check", description = "Verifica si el servicio está levantado")
    public Map<String, String> health() {{
        return Map.of("status", "ok");
    }}
}}
"""
    with open(os.path.join(ruta_java, "HelloController.java"), "w", encoding="utf-8") as f:
        f.write(codigo_controller)

    # 4. Configurar application.properties
    codigo_properties = """server.port=8080
# Cambiar la ruta por defecto de Swagger si se desea
springdoc.swagger-ui.path=/swagger-ui.html
springdoc.api-docs.path=/api-docs
"""
    with open(os.path.join(ruta_resources, "application.properties"), "w", encoding="utf-8") as f:
        f.write(codigo_properties)

    # 5. Crear Dockerfile (Multi-stage build para compilar con Maven dentro de Docker)
    codigo_docker = """# Etapa 1: Construcción
FROM maven:3.9.6-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN mvn clean package -DskipTests

# Etapa 2: Ejecución
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
"""
    with open(os.path.join(ruta_completa, "Dockerfile"), "w", encoding="utf-8") as f:
        f.write(codigo_docker)

    # 6. Crear .gitignore
    codigo_gitignore = """target/
!.mvn/wrapper/maven-wrapper.jar
!**/src/main/**/target/
!**/src/test/**/target/
### IntelliJ IDEA ###
.idea
*.iws
*.iml
*.ipr
### Eclipse ###
.apt_generated
.classpath
.factorypath
.project
.settings
.springBeans
.sts4-cache
"""
    with open(os.path.join(ruta_completa, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(codigo_gitignore)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("❌ Uso: python generador_microservicio.py <nombre> <directorio_destino>")
        sys.exit(1)
        
    nombre_ms = sys.argv[1]
    directorio_dest = sys.argv[2]
    
    try:
        generar_microservicio(nombre_ms, directorio_dest)
        print(f"✅ Microservicio Java '{nombre_ms}' generado con éxito.")
        print(f"   ☕ Ejecución local: cd {os.path.join(directorio_dest, nombre_ms)} && mvn spring-boot:run")
        print("   🐳 Ejecución Docker: docker build -t API . && docker run -p 8080:8080 API")
        print("   📖 Swagger UI: http://localhost:8080/swagger-ui.html")
    except Exception as e:
        print(f"❌ Error al generar el microservicio: {e}")
        sys.exit(1)