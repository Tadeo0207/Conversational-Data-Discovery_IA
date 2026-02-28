# 🚀 Conversational Data Discovery: Plataforma de Análisis de Datos Empresarial

Bienvenido al registro integral del proyecto "Conversational Data Discovery", una aplicación web corporativa construida con **Python** y **Streamlit** que funciona como un Data Scientist virtual impulsado por los modelos LLM de Google Gemini.

Esta herramienta permite a usuarios sin conocimientos de programación cargar enormes volúmenes de datos (Excels, CSVs o Conexiones SQL Directas) y conversar con ellos, limpiarlos automáticamente, generar gráficos interactivos, y exportar reportes ejecutivos en PDF del calibre de las Big Four (KPMG, Deloitte, PwC, EY).

---

## 🏗️ Arquitectura y Tecnologías Clave

El sistema fue levantado desde cero priorizando la seguridad (ejecución de código aislado), la estética corporativa y el procesamiento concurrente de archivos.

- **Frontend & App Framework:** `Streamlit` (Interfaz web reactiva)
- **Motor de Inteligencia Artificial:** `google-genai` (Gemini 2.5 y 1.5 Flash para generación de código y texto)
- **Procesamiento de Datos:** `pandas`, `numpy`
- **Visualización:** `plotly.express`, `matplotlib`, `seaborn` (Gráficos interactivos y renderizados estáticos para PDF)
- **Exportación a PDF:** `fpdf2` (Tipografía nativa UTF-8 `DejaVuSans` para soporte completo de acentos y eñes)
- **Base de Datos & Persistencia:** `sqlite3` integrada (Módulo `db.py`)
- **Ingesta de Datos Avanzada:** `sqlalchemy` (Para conexiones remotas a PostgreSQL, MySQL, etc.)

---

## ✨ Módulos y Funcionalidades Desarrolladas (De Inicio a Fin)

El proyecto evolucionó a través de 11 grandes versiones (V1 a V11), culminando en el siguiente estado funcional:

### 1. 📁 Ingesta Multi-Modal (Archivos y SQL)
En el panel lateral izquierdo, el usuario puede arrastrar y soltar archivos.
- **Soporte Multi-Archivo:** Originalmente solo se permitía un CSV a la vez. El sistema fue reescrito para empaquetar múltiples Excel/CSVs simultáneamente, guardándolos en el servidor (`/uploads`) y renderizando cada uno en su propia "pestaña de visualización de datos" (`st.tabs`).
- **Conexión Directa a SQL:** En lugar de exportar Excels de un sistema de gestión, el usuario puede pegar la URI (credenciales) de una base de datos PostgreSQL/MySQL. La herramienta extrae el esquema automáticamente, permitiendo chatear con la base de datos entera sin descargarla.

### 2. 🧠 Chatbot de Análisis a Medida (DataAgent)
El corazón del proyecto reside en `analytics_agent.py`. Cuando el usuario escribe preguntas complejas ("¿Cuál fue el mes de mayores ventas?"), ocurren dos escenarios:
- **Flujo Estándar:** La IA de Gemini escribe un bloque estricto de **código Python/Pandas** basado en los datos subidos.
- **Auditoría de Seguridad (AST):** El sistema escanea el código devuelto usando la librería `ast` para bloquear intentos de hackeo (funciones prohibidas como `os.system` o `eval`).
- **Ejecución Local:** Si es seguro, se ejecuta localmente. Si falla, el traceback del error se devuelve al LLM en un bucle cerrado para que el agente se **autocorrija** hasta que funciona y devuelve el texto/tabla final a la interfaz.

### 3. 🧽 Pestaña: Data Cleansing Mágico
Los datos crudos suelen estar sucios. Desarrollamos una pantalla específica donde:
- Con 1 click, el `DataAgent` escanea las columnas y escribe un script para estandarizar nombres de columnas, rellenar Nulos indiscriminados, y hasta "rescatar" archivos CSV corruptos donde todas las comillas fallaron.
- El usuario puede descargar el `CSV limpio` instantáneamente y guardarlo en su directorio local.

### 4. 📈 Pestaña: Gráficos Automáticos Instantáneos
El usuario no necesita saber qué graficar.
- Al entrar a la pestaña de "Gráficos", la IA escanea los tipos de variables y dibuja 3 o 4 gráficas (con Plotly) interactivas, seleccionando automáticamente si corresponde un *Pie Chart* para categorías o un *Line Chart* para tiempos.
- **Resistencia "Cascade" API:** Esta zona cuenta con un bucle masivo de resistencia térmica (10 alias distintos de servidores Gemini) garantizando que, si se agota la cuota gratuita diaria de 1 servidor, rebotará automáticamente al siguiente para jamás bloquear al usuario.

### 5. 📄 Exportación de Reporte PDF "Big Four"
Botón en el panel izquierdo que actúa como un analista junior creando un entregable ejecutivo mensual.
- La librería nativa escupe un archivo PDF con formato y fuentes empresariales corporativas.
- **Auto-Estadísticas:** El reporte inyecta dinámicamente tablas estadísticas de Pandas (Media, Desviación, Porción Nula).
- **Auto-Plotting:** Gemini renderiza temporalmente Matrices de Correlación u otros gráficos como imágenes `.png` y los "pega" o incrusta visualmente en el interior del PDF finalizando la presentación, antes de eliminar los gráficos temporales.

### 6. 🕒 Memoria a Largo Plazo (Persistencia de Sesión)
Todo lo que se sube, se chatea y se limpia, vive para siempre.
- Al cerrar la app o empezar "Nuevo Chat", el estado actual (archivos json, Dataframes y mensajes en formato List) se comprimen y se inyectan en una base de datos SQLite.
- El panel lateral muestra botones con historiales anteriores. Al cliquear uno, el sistema re-hidrata las tablas dinámicas, vacía la interfaz y te transporta en el tiempo a ese análisis viejo.
- **UX Polish:** Posteriormente agregamos iconos Material natives para poder Renombrar ("✏️") amigablemente o Eliminar ("❌") directamente esas memorias SQL.

---

## 🔒 Estándares de Seguridad y Escalado Implementados

- **Sandbox Python:** `exec()` corre en un entorno severamente restringido sin acceso al OS ni librerías de request web.
- **Minificación de Tokens:** Para evitar agotar el límite de entrada de la IA (Context Window), si el usuario sube un dataset de 2 Millones de Filas, Gemini solo recibe el diccionario de *"ColumnDataTypes"* y las *primeras 2 filas*, economizando gigabytes de lectura artificial.

---

**Estado Final:** La arquitectura base de "Chat -> AST Sandboxing -> Auto-corrección -> UI Render" está cimentada fuertemente, convirtiéndola de un simple script a una plataforma madura de nivel empresarial.
