import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google import genai
import io
import contextlib
import traceback
import re
import ast
from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        # Logo ficticio / Cuadrado de color corporativo
        self.set_fill_color(33, 37, 41)
        self.rect(10, 10, 10, 10, 'F')
        
        self.set_font('helvetica', 'B', 18)
        self.set_text_color(33, 37, 41)
        # Mover a la derecha del logo
        self.cell(15)
        self.cell(0, 10, 'Reporte de Análisis Estratégico AI', align='L', new_x="LMARGIN", new_y="NEXT")
        
        # Línea separadora decorativa simulando Big Four
        self.set_draw_color(0, 102, 204) # Azul corporativo
        self.set_line_width(1)
        self.line(10, 25, 200, 25)
        self.ln(10)
        
    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Generado Automáticamente | Página {self.page_no()}', align='C')

class DataAgent:
    def __init__(self, api_key, model_name="gemini-flash-latest"):
        self.api_key = api_key
        # Inicializando el cliente nuevo
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def extract_code(self, text):
        """Extrae el bloque de código de la respuesta y elimina creaciones de diccionarios/dataframes dummy."""
        pattern = r"```(?:python)?\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            code = matches[-1]
            
            # FILTRO DE ALUCINACIONES: Muchas veces la IA intenta recrear el DF localmente
            # Borramos cualquier línea que defina diccionarios de prueba o reescriba el df base.
            cleaned_lines = []
            skip_dict = False
            for line in code.split('\n'):
                # Ignorar bloques de diccionarios de prueba _data = { ... }
                if line.strip().startswith('_data =') or line.strip().startswith('data = {') or line.strip().startswith('_faulty_row'):
                    skip_dict = True
                    continue
                if skip_dict and line.strip() == '}':
                    skip_dict = False
                    continue
                if skip_dict:
                    continue
                
                # Ignorar reasignaciones directas del df original
                if line.strip().startswith('df = pd.DataFrame('):
                    continue
                if line.strip().startswith('df.loc[len(df)]'):
                    continue
                    
                cleaned_lines.append(line)
                
            return '\n'.join(cleaned_lines)
            
        return text 

    def get_df_context(self, df, dataframes=None, db_schema=None):
        """Prepara el contexto del DataFrame activo, diccionario auxiliar y base de datos minimizando el uso de tokens."""
        context = ""
        
        if df is not None and not df.empty:
            # Minification: Just send dict of {col: dtype} instead of df.info()
            dtypes_dict = {col: str(dtype) for col, dtype in df.dtypes.items()}
            # Send only 2 rows in CSV format to save space
            head_csv = df.head(2).to_csv(index=False)
            context += f"### DataFrame Activo ('df'):\nColumnas y Tipos: {dtypes_dict}\n\n### Datos de muestra (CSV):\n{head_csv}\n"
        
        if dataframes and len(dataframes) > 0:
            context += "\nOtros DataFrames cargados en memoria en el dict `dataframes['nombre']`:\n"
            for name, aux_df in dataframes.items():
                # Minification
                aux_dtypes = {col: str(dtype) for col, dtype in aux_df.dtypes.items()}
                context += f"- Archivo '{name}': {aux_dtypes}\n"
                
        if db_schema and len(db_schema) > 0:
            context += "\nBASE DE DATOS CONECTADA (puedes usar `engine` con pd.read_sql_query):\n"
            # Si hay demasiadas tablas, solo mostramos las primeras 15 para no saturar tokens
            tablas_mostradas = list(db_schema.items())[:15]
            for table, cols in tablas_mostradas:
                # Mostrar primeros 20 columnas max
                cols_str = ', '.join(cols[:20]) + ('...' if len(cols) > 20 else '')
                context += f" - Tabla '{table}': {cols_str}\n"
            if len(db_schema) > 15:
                context += f" - (... y {len(db_schema) - 15} tablas más)\n"
                
        return context

    def generate_suggestions(self, df, db_schema=None):
        """Genera 3 sugerencias de preguntas analíticas basadas en el dataframe o en la base de datos."""
        df_context = self.get_df_context(df, db_schema=db_schema)
        prompt = f"""
Eres un Analista de Datos Senior.
Tienes el siguiente esquema de datos disponible (puede ser un DataFrame en memoria o una Base de Datos SQL):

{df_context}

Tu objetivo es observar las columnas/tablas y devolver EXACTAMENTE 3 preguntas analíticas muy interesantes, útiles y de negocio que el usuario podría hacerle a estos datos.
Devuelve las preguntas como una lista simple separada por saltos de línea, sin números, viñetas ni texto extra.
Escribe las preguntas en español, sé creativo, y pon un emoji relevante al principio de cada una.
Ejemplo:
📊 ¿Cuál es la correlación entre Edad y Salario?
📈 Muestra la tendencia de Ventas en el último año comparado con los gastos
📉 ¿Qué categoría de productos genera mayores márgenes?
"""
        models_to_try = [
            self.model_name, 
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview", 
            "gemini-2.5-flash", 
            "gemini-2.0-flash-001",
            "gemini-2.0-flash",
            "gemini-2.5-pro", 
            "gemini-pro-latest",
            "gemini-3-pro-preview"
        ]
        try:
            response = None
            for m_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=m_name,
                        contents=prompt
                    )
                    break
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        continue
                    raise e # Si es otro error, lanzarlo
                    
            if not response:
                 raise Exception("Quota Excedida en todos los modelos")
                 
            lines = [line.strip() for line in response.text.split('\n') if line.strip() and len(line) > 5][:3]
            if not lines:
                raise Exception("Respuesta vacía")
            return lines
        except Exception as e:
            if db_schema:
                return [
                    "📊 Muestra un recuento de registros por cada tabla importante",
                    "📈 ¿Qué tabla contiene la mayor cantidad de datos?",
                    "📉 Enumera las columnas clave de la base de datos"
                ]
            else:
                return [
                    "📊 Muestra un resumen general estadístico de los datos numéricos",
                    "📈 ¿Cuáles son y en qué columnas están los valores nulos del dataset?",
                    "📉 Genera una tabla con las 5 filas donde los valores sean más altos"
                ]

    def generate_cleaning_code(self, df):
        """Genera y ejecuta código para limpiar el DataFrame cargado."""
        df_context = self.get_df_context(df)
        prompt = f"""
Eres un Data Engineer Senior experto en Pandas de Python. 
Tu objetivo es limpiar el siguiente dataset cargado localmente en la variable `df`.

{df_context}

INSTRUCCIONES DE LIMPIEZA OBLIGATORIAS Y ESTRICTAS (NO DESTRUCTIVAS):
1. ¡CRÍTICO! La variable `df` YA EXISTE en memoria. NUNCA crees diccionarios `_data = {{}}` ni redefinas `df = pd.DataFrame(...)` para simular el entorno. Trabaja directamente sobre el `df` implícito.
2. Elimina filas o columnas que sean enteramente nulas: `df.dropna(how='all', inplace=True)`. ¡ESTA ES LA ÚNICA RAZÓN VÁLIDA PARA BORRAR UNA FILA!
3. NUNCA borres una fila parcialmente. ¡Limpia el texto o imputa, no destruyas el dato!
4. NUNCA inventes datos numéricos. Si un campo como 'ingresos' está vacío, DÉJALO VACÍO (`NaN` o `None`).
5. Para textos vacíos irrelevantes puedes usar 'Desconocido', pero no borres la fila.
6. ¡RESCATE DE COMILLAS!: Si notas que una fila entera se leyó como un solo string largo en la primera columna (ej. por un error de comillas), DIVIDE ese string por comas y reasigna los valores a sus columnas.
7. Convierte columnas numéricas que tengan caracteres/espacios a tipo numérico de Pandas coercionando errores (`errors='coerce'`).
8. Elimina filas duplicadas EXACTAS: `df.drop_duplicates(inplace=True)`.
4. Estandariza los nombres de columnas: pasa a minúsculas, reemplaza espacios por guiones bajos.
5. Usa estructuras Try-Except si intentas convertir columnas de fecha (ej: `pd.to_datetime`), para que el script no crashee por culpa de un mal formato.
6. ¡CRÍTICO! Asigna el DataFrame ya limpio a la variable `result`. NO USES OTRAS VARIABLES: `result = df.copy()`
7. Asigna un breve resumen en string a la variable `explanation`.
8. Devuelve ÚNICAMENTE un bloque de código rodeado por ```python y ```. NO INCLUYAS TEXTO FUERA DEL BLOQUE.
"""
        max_retries = 2
        current_prompt = prompt
        models_to_try = [
            self.model_name, 
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview", 
            "gemini-2.5-flash", 
            "gemini-2.0-flash-001",
            "gemini-2.0-flash",
            "gemini-2.5-pro", 
            "gemini-pro-latest",
            "gemini-3-pro-preview"
        ]
        
        for attempt in range(max_retries):
            code = None
            last_error = None
            
            for m_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=m_name,
                        contents=current_prompt
                    )
                    code = self.extract_code(response.text)
                    if code:
                        break # Exito con este modelo
                except Exception as e:
                    last_error = str(e)
                    continue # Intenta el siguiente modelo
            
            if not code:
                if "429" in str(last_error) or "RESOURCE_EXHAUSTED" in str(last_error):
                    return False, None, "⏳ Límite de Cuota Gratuita (Google Gemini) Alcanzado. Por favor espera aproximadamente 1 minuto antes de volver a intentar limpiar los datos.", None
                return False, None, f"Error de API: {last_error}", None
                
            is_valid, ast_error = self.validate_code(code)
            if not is_valid:
                current_prompt += f"\n\nEl código falló la auditoría de seguridad:\n{ast_error}\nCorrige el código usando solo librerías permitidas."
                continue
                
            success, result_df, _, explanation, insights_dict, _, error = self.execute_code(code, df)
            
            if success and result_df is not None:
                return True, result_df, explanation, code
            else:
                current_prompt += f"\n\nEl código falló con error:\n{error}\nCorrige el código pandas y devuelve solo código python."
                
        return False, None, "No se pudo generar un código de limpieza válido tras varios intentos.", code

    def validate_code(self, code):
        """Pre-chequeo del código generado utilizando AST (Abstract Syntax Tree) para sandboxing seguro."""
        import ast

        class SecurityScanner(ast.NodeVisitor):
            def __init__(self):
                self.errors = []
                self.allowed_modules = {'pandas', 'pd', 'numpy', 'np', 'plotly', 'sklearn'}
                self.blocked_calls = {'eval', 'exec', 'open', '__import__', 'os', 'sys', 'subprocess', 'shutil'}

            def visit_Import(self, node):
                for alias in node.names:
                    root_module = alias.name.split('.')[0]
                    if root_module not in self.allowed_modules:
                        self.errors.append(f"Importación no permitida: '{alias.name}'. Solo se permite pandas, numpy, plotly y sklearn.")
                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                if node.module:
                    root_module = node.module.split('.')[0]
                    if root_module not in self.allowed_modules:
                        self.errors.append(f"Importación no permitida: '{node.module}'. Solo se permite pandas, numpy, plotly y sklearn.")
                self.generic_visit(node)

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.blocked_calls:
                        self.errors.append(f"Llamada a función restringida: '{node.func.id}()'")
                elif isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in self.blocked_calls:
                        self.errors.append(f"Llamada a atributo restringido: '{node.func.value.id}.{node.func.attr}'")
                self.generic_visit(node)

        try:
            tree = ast.parse(code)
            scanner = SecurityScanner()
            scanner.visit(tree)
            
            if scanner.errors:
                return False, "\n".join(scanner.errors)
            return True, None
        except SyntaxError as e:
            return False, f"Error de sintaxis de Python: {e}"

    def execute_code(self, code, df, dataframes=None, db_uri=None):
        """Ejecuta el código generado en un entorno seguro y aislado."""
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
        from sklearn.linear_model import LinearRegression, LogisticRegression
        
        engine_obj = None
        if db_uri:
            from sqlalchemy import create_engine
            engine_obj = create_engine(db_uri)
            
        # Variables pasadas al entorno de ejecución
        local_vars = {
            'df': df,
            'dataframes': dataframes if dataframes else {},
            'engine': engine_obj,
            'pd': pd,
            'px': px,
            'go': go,
            'RandomForestRegressor': RandomForestRegressor,
            'RandomForestClassifier': RandomForestClassifier,
            'LinearRegression': LinearRegression,
            'LogisticRegression': LogisticRegression,
            'result': None,
            'fig': None,
            'explanation': None,
            'insights_dict': None
        }
        
        output = io.StringIO()
        try:
            # Capturar cualquier print o salida estándar
            with contextlib.redirect_stdout(output):
                exec(code, globals(), local_vars)
            
            # Retornar estado, posibles resultados extraídos y salida estándar
            return True, local_vars.get('result'), local_vars.get('fig'), local_vars.get('explanation'), local_vars.get('insights_dict'), output.getvalue(), None
            
        except Exception as e:
            # En caso de error, capturar el traceback para que el agente se autocorriga
            error_msg = traceback.format_exc()
            return False, None, None, None, None, output.getvalue(), error_msg

    def generate_preview_charts(self, df):
        """Genera un script que produce una lista de 3 a 4 gráficos sugeridos."""
        df_context = self.get_df_context(df)
        prompt = f"""
Eres un Analista de Datos Senior experto en Visualización con Plotly Express.
Tienes un DataFrame `df`. Tu objetivo es crear exactamente 3 o 4 gráficas INÚTILES y EXCELENTES que resuman el comportamiento del dataset para mostrarlas en un Panel de Control.

{df_context}

INSTRUCCIONES OBLIGATORIAS:
1. Usa combinaciones de datos valiosas (por ejemplo: si hay fechas usa gráficos de línea `px.line`, si hay categorías `px.bar` o `px.pie`, si hay valores numéricos continuos `px.histogram` o `px.box`, si hay ubicaciones `px.scatter_geo`).
2. ¡CRÍTICO PARA RENDIMIENTO (EVITAR LAG)! NUNCA grafiques miles de puntos en crudo. Si usas `px.scatter`, `px.line` o similares con un dataframe grande, DEBES agrupar los datos primero (ej: por fecha/categoría) o tomar una muestra aleatoria (`df.sample(n=min(500, len(df)))`). Si graficas categorías, grafica SOLO el Top 10 (`.nlargest(10)`). ¡Graficar todo el dataset congelará la interfaz web!
3. Asígnale a las gráficas títulos claros y descriptivos en español usando `title="Titulo"`.
4. ¡CRÍTICO! Debes guardar todas las figuras generadas en una sola lista de Python llamada `result`. Por ejemplo: `result = [fig1, fig2, fig3]`.
4. OPCIONAL PERO RECOMENDADO: asigna a la variable `explanation` una lista de textos explicativos (strings en español) que correspondan a cada figura en `result` explicándola brevemente. Ej: `explanation = ["Texto 1", "Texto 2", "Texto 3"]`.
5. Devuelve ÚNICAMENTE código Python delimitado por ```python y ```.
"""
        max_retries = 2
        current_prompt = prompt
        models_to_try = [
            self.model_name, 
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview", 
            "gemini-2.5-flash", 
            "gemini-2.0-flash-001",
            "gemini-2.0-flash",
            "gemini-2.5-pro", 
            "gemini-pro-latest",
            "gemini-3-pro-preview"
        ]
        
        for attempt in range(max_retries):
            code = None
            last_error = None
            
            for m_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=m_name,
                        contents=current_prompt
                    )
                    code = self.extract_code(response.text)
                    if code:
                        break
                except Exception as e:
                    last_error = str(e)
                    continue
                    
            if not code:
                if "429" in str(last_error) or "RESOURCE_EXHAUSTED" in str(last_error):
                    return False, [], [], "Feedback: ⏳ Límite de Cuota Gratuita (Gemini). Por favor, espera al menos un minuto para generar los gráficos automáticos."
                return False, [], [], f"Error API: {last_error}"
                
            success, result_list, _, explanations_list, insights_dict, _, error = self.execute_code(code, df)
            
            if success and isinstance(result_list, list) and len(result_list) > 0:
                if not isinstance(explanations_list, list):
                    explanations_list = ["Sin explicación generada."] * len(result_list)
                return True, result_list, explanations_list, None
            else:
                current_prompt += f"\n\nFalló! (Error: {error} o result no era una lista de figuras). Devuelve solo el código corrigiendo."
                
        return False, [], [], "Feedback: No se pudieron renderizar los gráficos rápidos"

    def generate_pdf_report(self, df, db_schema=None, db_uri=None):
        """Genera un reporte PDF descriptivo del dataset utilizando fpdf2 y datos reales si es SQL."""
        
        datos_extra = ""
        if db_schema and db_uri:
            # 1. En vez de gastar 1 llamada a la API para que Gemini escriba el código SQL,
            # lo escribimos nosotros directamente iterando sobre el esquema, y luego llamamos a pd.read_sql
            # Esto previene el error 429 RESOURCE_EXHAUSTED en el Free Tier.
            import pandas as pd
            from sqlalchemy import create_engine
            
            try:
                engine_obj = create_engine(db_uri)
                muestras = []
                # Tomamos maximo 3 tablas para no saturar tokens
                tablas_a_procesar = list(db_schema.keys())[:3]
                
                for tabla in tablas_a_procesar:
                    query = f"SELECT * FROM {tabla} LIMIT 3"
                    df_muestra = pd.read_sql_query(query, engine_obj)
                    muestras.append(f"--- Datos de la Tabla '{tabla}' ---\n{df_muestra.to_string()}")
                    
                datos_extra = "\n\n### Muestra de Datos Reales Extraída de SQL:\n" + "\n".join(muestras)
            except Exception as e:
                datos_extra = f"\n\n(No se pudo extraer muestra de datos: {e})"

        # 2. Generar el reporte final con el LLM (Única llamada a la API)
        df_context = self.get_df_context(df, db_schema=db_schema)
        prompt = f"""
Eres un Consultor de Datos Experto. Escribe un reporte formal y estructurado de análisis de datos para el siguiente contexto tecnológico (puede ser un DataFrame local o esquema SQL).
El reporte debe contener:
1. Resumen: ¿De qué trata este modelo de datos? (Infiere el propósito empresarial a partir de las columnas).
2. Puntos de Interés: ¿Qué tablas o columnas son clave para tomar decisiones de negocio?
3. Anomalías o Alertas: Riesgos, valores nulos, posibles sesgos o variables dominantes.

{df_context}
{datos_extra}

Devuelve ÚNICAMENTE texto estructurado. NO uses markdown complicado (evita **, ##, etc). Usa mayúsculas para títulos y guiones para viñetas. Redacta en español claro y profesional.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            report_text = response.text.replace('**', '').replace('#', '')
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                raise Exception("⏳ Límite de Cuota Gratuita (Google Gemini) Alcanzado. Por favor espera aproximadamente 1 minuto antes de volver a intentar generar el reporte.")
            raise Exception(f"Error generando reporte con LLM: {error_str}")
        
        import os
        import urllib.request
        font_path = "DejaVuSans.ttf"
        font_bold_path = "DejaVuSans-Bold.ttf"
        
        # Descargar The DejaVuSans para soporte Unicode completo de FPDF2 (acentos perfectos)
        if not os.path.exists(font_path):
            try:
                urllib.request.urlretrieve("https://github.com/matomo-org/travis-scripts/raw/master/fonts/DejaVuSans.ttf", font_path)
            except:
                pass
        if not os.path.exists(font_bold_path):
            try:
                urllib.request.urlretrieve("https://github.com/matomo-org/travis-scripts/raw/master/fonts/DejaVuSans-Bold.ttf", font_bold_path)
            except:
                pass

        pdf = PDF()
        pdf.add_page()
        
        has_unicode = False
        if os.path.exists(font_path) and os.path.exists(font_bold_path):
            pdf.add_font("DejaVu", "", font_path)
            pdf.add_font("DejaVu", "B", font_bold_path)
            pdf.set_font("DejaVu", size=11)
            has_unicode = True
        else:
            pdf.set_font("helvetica", size=11)

        # SECCIÓN 1: Estadísticas Descriptivas
        pdf.set_font("DejaVu" if has_unicode else "helvetica", style="B", size=14)
        pdf.cell(0, 10, "1. Estadísticas Descriptivas (Numéricas)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu" if has_unicode else "helvetica", size=10)
        
        try:
            desc = df.describe().T[['mean', '50%', 'std', 'count']]
            nulls_pct = (df[desc.index].isnull().sum() / len(df)) * 100
            desc['% Nulos'] = nulls_pct
            
            cols = ["Variable", "Media", "Mediana", "Desv. Est", "Conteo", "% Nulos"]
            col_widths = [50, 28, 28, 28, 28, 28]
            
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font(style="B")
            for i, col_name in enumerate(cols):
                pdf.cell(col_widths[i], 8, col_name, border=1, fill=True, align='C')
            pdf.ln()
            
            pdf.set_font(style="")
            for idx, row in desc.iterrows():
                pdf.cell(col_widths[0], 8, str(idx)[:20], border=1)
                pdf.cell(col_widths[1], 8, f"{row.get('mean', 0):.2f}", border=1, align='R')
                pdf.cell(col_widths[2], 8, f"{row.get('50%', 0):.2f}", border=1, align='R')
                pdf.cell(col_widths[3], 8, f"{row.get('std', 0):.2f}", border=1, align='R')
                pdf.cell(col_widths[4], 8, f"{int(row.get('count', 0))}", border=1, align='R')
                pdf.cell(col_widths[5], 8, f"{row.get('% Nulos', 0):.2f}%", border=1, align='R')
                pdf.ln()
            pdf.ln(5)
        except Exception as e:
            pdf.cell(0, 10, "(No hay columnas numéricas o falló el cálculo estadístico)", new_x="LMARGIN", new_y="NEXT")
            pdf.ln()

        # SECCIÓN 2: Visualización Embebida
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        pdf.set_font("DejaVu" if has_unicode else "helvetica", style="B", size=14)
        pdf.cell(0, 10, "2. Visualización Principal", new_x="LMARGIN", new_y="NEXT")
        
        try:
            plt.figure(figsize=(9, 5))
            cat_cols = df.select_dtypes(include=['object', 'category']).columns
            num_cols = df.select_dtypes(include=['number']).columns
            
            if len(cat_cols) > 0 and len(num_cols) > 0:
                # Gráfico de barras simple y útil para negocios (Top 10 Categorías por una Métrica)
                cat_col = cat_cols[0]
                num_col = num_cols[0]
                grouped = df.groupby(cat_col)[num_col].sum().nlargest(10)
                sns.barplot(x=grouped.values, y=grouped.index, palette='viridis')
                plt.title(f"Top 10 '{cat_col}' según '{num_col}' (Suma)")
            elif len(num_cols) >= 1:
                # Distribución simple si solo hay números
                sns.histplot(df[num_cols[0]].dropna(), kde=True, color="teal")
                plt.title(f"Distribución General de '{num_cols[0]}'")
            elif len(cat_cols) >= 1:
                # Top 10 conteo si solo hay categorías
                val_counts = df[cat_cols[0]].value_counts().nlargest(10)
                sns.barplot(x=val_counts.values, y=val_counts.index, palette='viridis')
                plt.title(f"Top 10 Frecuencias en '{cat_cols[0]}'")
                
            plt.tight_layout()
            chart_path = "temp_chart_pdf.png"
            plt.savefig(chart_path, dpi=150)
            plt.close()
            
            pdf.image(chart_path, w=160)
            pdf.ln(5)
            if os.path.exists(chart_path):
                os.remove(chart_path)
        except Exception as e:
            pdf.set_font("DejaVu" if has_unicode else "helvetica", size=10)
            pdf.cell(0, 10, "(No se pudo renderizar la visualización)", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

        # SECCIÓN 3: Conclusiones de IA
        pdf.set_font("DejaVu" if has_unicode else "helvetica", style="B", size=14)
        pdf.cell(0, 10, "3. Conclusiones del Modelo de IA", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu" if has_unicode else "helvetica", size=11)
        
        for line in report_text.split('\n'):
            if has_unicode:
                pdf.multi_cell(0, 8, txt=line, new_x="LMARGIN", new_y="NEXT")
            else:
                # Fallback latino si falla la fuente
                sanitized_line = line.encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 8, txt=sanitized_line, new_x="LMARGIN", new_y="NEXT")
            
        return pdf.output()

    def process_query(self, df, dataframes, user_query, db_schema=None, db_uri=None, max_retries=3, chat_history=None):
        """Procesa la pregunta del usuario con memoria histórica limitada, genera código, lo ejecuta y se autocorrige."""
        df_context = self.get_df_context(df, dataframes, db_schema)
        
        # Minify chat history (max last 4 messages, text only)
        history_context = ""
        if chat_history and len(chat_history) > 0:
            history_context = "\n### Historial Reciente de la Conversación:\n"
            # Tomamos ultimos 4 mensajes
            recent = chat_history[-4:]
            for msg in recent:
                role_name = "USUARIO" if msg.get("role") == "user" else "ASISTENTE"
                text_content = msg.get("text", "")
                if text_content:
                    history_context += f"{role_name}: {text_content}\n"
        
        base_prompt = f"""
Eres un Analista de Datos Senior y Arquitecto de BI experto en Python (Pandas, Plotly, Scikit-Learn) y SQL.
El usuario ha proporcionado el siguiente entorno de datos:

{df_context}
{history_context}

Consulta ACTUAL del usuario: "{user_query}"

INSTRUCCIONES CRÍTICAS ESTRICTAS:
1. AUTONOMÍA DE HERRAMIENTAS: Tienes que decidir si usar archivos locales (`df` / `dataframes`) o realizar una consulta a la BASE DE DATOS si ves conectividad conectada a `engine`.
2. SI USAS SQL: Ya tienes acceso a una variable `engine` conectada. Usa ALGORITMOS NATIVOS escribiendo variables locales de dataframe así: `df_db = pd.read_sql_query("SELECT * FROM tabla_x", engine)`. Luego opera sobre `df_db`. 
3. SI USAS ARCHIVOS: Opera con `df` o cruzando tablas del diccionario `dataframes` (ej: `dataframes['clientes.csv']`).
4. El código será ejecutado mediante `exec()`. Las librerías de ML, Pandas (`pd`) y Plotly (`px`) ya están importadas.
5. PREVISIONES Y MACHINE LEARNING: Usa e importa `sklearn` si el usuario pide predicciones.
6. SI VES UN ERROR AST: Significa que intentaste usar librerías restringidas (os, sys, eval, open). NO USES HERRAMIENTAS PELIGROSAS.
7. OBLIGATORIO: SIEMPRE debes asignar a la variable `result` una respuesta en formato texto (string) respondiendo DIRECTAMENTE a la pregunta del usuario. Escribe conclusiones claras con los datos crudos extraídos de tu análisis. NUNCA dejes `result` vacío, incluso si haces un gráfico.
8. Si la consulta merece un gráfico: crea la figura de Plotly y asígnala a la variable `fig`. NO uses `fig.show()`. CRITICO PARA RENDIMIENTO: Usa `.nlargest(15)` para categorías. NUNCA grafiques miles de puntos brutos en scatter/line plots (usa `groupby` o `df.sample(500)`) para evitar que la interfaz del usuario colapse por lag.
9. NOTAS ADICIONALES: Asigna a la variable `explanation` un breve párrafo en español resumiendo el insight principal.
10. OBLIGATORIO (INSIGHTS): Asigna a la variable `insights_dict` un diccionario de Python con 2 o 3 "Insights Clave" extraídos de tu análisis (ej: `{{"Ventas": "Subieron 20%", "Anomalía": "Pico en marzo"}}`).
11. MANEJO DE PREGUNTAS FUERA DE DOMINIO: Si el usuario pregunta algo totalmente desconectado de los datos (ej: dar una receta, contar un chiste, charlar), DEBES responder en `result` empezando con una advertencia graciosa o sarcástica reconociendo que eres un Analista de Datos muy caro obligado a responder frivolidades, y luego dale la respuesta que pide de todos modos.
12. Devuelve ÚNICAMENTE bloques de código delimitados por ```python y ```.
"""
        
        current_prompt = base_prompt
        
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=current_prompt
                )
                code = self.extract_code(response.text)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    return "⏳ **Límite de Cuota Gratuita Alcanzado (Google Gemini)**\n\nHas excedido el número de peticiones por minuto de la versión gratuita. Por favor, espera entre **40 y 60 segundos** antes de enviar otra consulta.", None, None, None, None
                return f"Error en la API de Gemini: {error_str}", None, None, None, None
                
            if not code.strip():
                return "No se pudo generar código válido para esta consulta.", None, None, None, None
                
            is_valid, ast_error = self.validate_code(code)
            if not is_valid:
                current_prompt += f"\n\nEl código falló la auditoría de seguridad:\n{ast_error}\nEscribe el código usando SOLO métodos permitidos o SQL nativo."
                continue
                
            success, result, fig, explanation, insights_dict, stdout, error = self.execute_code(code, df, dataframes, db_uri)
            
            if success:
                # Si el código se ejecutó bien pero el modelo usó prints en vez de "result"
                if result is None and fig is None and stdout:
                    result = stdout.strip()
                return result, fig, explanation, insights_dict, code
            else:
                # Loop de autocorrección: Informar al modelo del error
                current_prompt += f"\n\nEl código anterior generado:\n```python\n{code}\n```\nFalló con este error:\n{error}\nPor favor, analiza el error, corrige el código y devuelve SOLO el código corregido en Python."
                
        return f"Error al ejecutar el código tras {max_retries} intentos de autocorrección. Último error:\n{error}", None, None, None, None
