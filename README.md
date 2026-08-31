# Scarpy - Autonomous Web Discovery Agent

Scarpy es un agente web avanzado impulsado por Inteligencia Artificial diseñado para la navegación autónoma, la extracción estructurada de datos y la recuperación resiliente ante fallos. Aprovechando el poder de **Playwright** y modelos LLM a través de **Stagehand**, Scarpy es capaz de entender un objetivo natural, explorar un sitio web de forma inteligente y cumplir misiones complejas sin depender de selectores CSS frágiles o scripts estáticos.

## 🌟 Características Principales

- **Agente Autónomo Completo:** Ejecuta un ciclo robusto `GOAL -> PLAN -> OBSERVE -> ACT -> VERIFY`.
- **Motor de Descubrimiento Web (Discovery Engine):** Capacidad para escanear una página partiendo de una URL semilla, descubrir paginación, filtros y enlaces de interés acotados a un dominio objetivo de forma automática.
- **Flujos de Autenticación Seguros:** Detecta formularios de login y aplica credenciales inyectadas de forma segura desde variables de entorno, sin filtrar secretos en logs ni bases de datos.
- **Self-Healing (Auto-recuperación):** Si la estructura del DOM de una página objetivo cambia y una estrategia conocida falla, el agente utiliza IA para descubrir nuevos selectores y actualiza su registro en base de datos.
- **Memoria Persistente:** Almacena resultados, estrategias aprendidas de recuperación y telemetría de eventos de forma persistente utilizando SQLAlchemy (SQLite/PostgreSQL).
- **Protección de Producción:** Previene fugas masivas de memoria/browsers (Zombie processes), cuenta con mitigación proactiva contra SSRF (Server-Side Request Forgery) permitiendo solo navegación HTTP/HTTPS segura y evita falsos positivos en las acciones gracias a verificaciones heurísticas estrictas.
- **API REST (FastAPI):** Proporciona una interfaz RESTful moderna y asíncrona para orquestar las tareas, consultarlas y streamear eventos en tiempo real.
- **Dashboard Web:** Incluye una interfaz web fácil e intuitiva para gestionar y monitorizar las operaciones de extracción en vivo.

## 🏗️ Arquitectura del Sistema

Scarpy se compone de múltiples módulos desacoplados:

1. **Capa de Control (FastAPI):** Endpoint REST que recibe trabajos y encola la ejecución sin bloquear la solicitud HTTP.
2. **Capa de Inteligencia (Stagehand / LLM):** Proporciona la interpretación semántica y razonamiento sobre el DOM dinámico cuando el sistema lo requiere.
3. **Capa del Navegador (Playwright):** Controla instancias de Chromium de manera aislada, implementando control de tiempos y protección anti-bloqueos.
4. **Agent Loop:** Núcleo orquestador que gestiona la memoria, genera estrategias en la base de datos de registro (Registry) e intenta recuperarse de fallas.

## 🚀 Requisitos

- **Python:** 3.11 o superior.
- **Node.js** (Opcional, si Playwright/Stagehand requiere contexto de Node en ciertas distribuciones).
- **Docker & Docker Compose** (Para el despliegue en producción).

## 🛠️ Instalación para Desarrollo Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/0x0055500l/Scarpy.git
   cd Scarpy
   ```

2. **Crear y activar un entorno virtual:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Instalar las dependencias:**
   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Instalar los binarios de Playwright:**
   ```bash
   playwright install chromium
   ```

5. **Configurar el entorno:**
   Copia el archivo de ejemplo de variables de entorno y ajusta las claves (como tu `OPENAI_API_KEY`):
   ```bash
   cp .env.example .env
   ```

6. **Iniciar el Servidor (FastAPI):**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Accede al Dashboard Web y a la API visitando `http://localhost:8000/`. La documentación Swagger está disponible en `http://localhost:8000/docs`.

## 🐳 Despliegue con Docker (Producción)

Scarpy está preparado para desplegarse fácilmente en un entorno contenerizado, previniendo el escalamiento de privilegios y utilizando un entorno base limpio (Ubuntu Jammy).

```bash
docker-compose up -d --build
```
El agente y la API quedarán disponibles internamente y expuestos en el puerto `8000`.

## 🧪 Pruebas y Fiabilidad (Testing)

El sistema incluye una extensa suite de pruebas de confiabilidad con simulaciones de errores en red, cambios bruscos de DOM, timeouts simulados y validaciones de inyección.

Para ejecutar todas las pruebas automatizadas (unitarias y de integración):

```bash
pytest tests/ -v
```

*Nota:* Durante los tests se levanta un servidor mock temporal automatizado y se ejecutan las navegaciones de forma controlada garantizando 100% de aislamiento.

## 🛡️ Auditoría de Seguridad & Robustez

Scarpy ha superado rigurosos controles de ingeniería de software (Principal Engineering Audits), lo que incluye:
- Cierre estricto de procesos Chromium huérfanos incluso bajo escenarios de `asyncio.CancelledError`.
- Desinfección rigurosa de URIs, mitigando vectores SSRF.
- Sistema lógico de "Self-Healing" que jamás entra en loops infinitos.
- Control detallado sobre los costos del LLM minimizando las observaciones redundantes.

---
**Scarpy** - Creado para dominar la web dinámica de forma inteligente y segura.
