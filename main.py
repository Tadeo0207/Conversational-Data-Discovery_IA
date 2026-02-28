import streamlit as st
import pandas as pd
from analytics_agent import DataAgent
import importlib
import sys
from sqlalchemy import create_engine, inspect

@st.dialog("Renombrar Sesión")
def rename_session_dialog(session_id, current_name):
    new_name = st.text_input("Nuevo Nombre:", value=current_name)
    if st.button("Guardar"):
        import db
        db.rename_session(session_id, new_name)
        st.session_state.rename_trigger = True # Hack para forzar rerun global después de cerrar el diálogo
        st.rerun()

import db
import json
import os
import shutil

CONFIG_FILE = "config.json"
UPLOAD_DIR = "data/uploads"
EXPORTS_DIR = "data/exports"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def safe_read_csv(file_obj):
    """Intenta leer un CSV con múltiples codificaciones comunes para evitar fallos."""
    try:
        return pd.read_csv(file_obj)
    except UnicodeDecodeError:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        try:
            return pd.read_csv(file_obj, encoding='latin1')
        except UnicodeDecodeError:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            return pd.read_csv(file_obj, encoding='cp1252')

# Cargar configuración (API Key)
config = load_config()
saved_api_key = config.get("api_key", "")

# Inicializar Base de Datos de Memoria
db.init_db()

# Forzar la recarga de los módulos para evitar caché antigua de Streamlit
if 'analytics_agent' in sys.modules:
    importlib.reload(sys.modules['analytics_agent'])
if 'db' in sys.modules:
    importlib.reload(sys.modules['db'])

# Configuración de página
st.set_page_config(page_title="Conversational Data Discovery", page_icon="📊", layout="wide")

st.title("📊 Conversational Data Discovery")
st.markdown("Carga cualquier CSV o Excel y dialoga con tus datos utilizando Inteligencia Artificial.")
# Inicializar variables vitales de sesión UI antes del render
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# Sidebar
with st.sidebar:
    st.header("1. Configuración")
    api_key_input = st.text_input("Ingresa tu Gemini API Key:", value=saved_api_key, type="password", help="Puedes obtener tu API key en Google AI Studio")
    
    # Guardar la API key si ha cambiado
    if api_key_input and api_key_input != saved_api_key:
        config["api_key"] = api_key_input
        save_config(config)
        saved_api_key = api_key_input
        
    api_key = api_key_input
    
    st.header("2. Datos o Base de Datos")
    
    data_source_opt = st.radio("Fuente de Datos", ["Archivos", "Base de Datos SQL"])
    
    uploaded_files = None
    db_uri = None
    
    if data_source_opt == "Archivos":
        uploaded_files = st.file_uploader("Sube tus datasets (CSV o Excel)", type=["csv", "xlsx"], accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_key}")
    else:
        st.info("Ejemplo SQLite: sqlite:///mi_base.db\nEjemplo Postgres: postgresql://user:pass@localhost/db")
        db_uri = st.text_input("URI de Conexión (SQLAlchemy)")
        if st.button("Conectar DB"):
            try:
                engine = create_engine(db_uri)
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                
                db_schema = {}
                for table in tables:
                    columns = [col['name'] for col in inspector.get_columns(table)]
                    db_schema[table] = columns
                    
                st.session_state.db_schema = db_schema
                st.session_state.db_uri = db_uri
                # Guardamos info ficticia para engañar a main.py y forzar la entrada al main_flow
                st.session_state.current_file = f"DB: {db_uri.split('@')[-1] if '@' in db_uri else db_uri}"
                st.session_state.df = pd.DataFrame() # DataFrame vacío
                st.session_state.dataframes = {} # Reset de archivos
                
                # Crear sesión pura para DB, guardando el URI real en filename para poder reconectarse luego
                session_id = db.create_session("DB Session", f"DB_URI:{db_uri}")
                st.session_state.current_session_id = session_id
                st.success(f"Conectado exitosamente. Se encontraron {len(tables)} tablas.")
                st.rerun()
            except Exception as e:
                st.error(f"Error de conexión: {e}")
                
    st.markdown("---")
    if st.button("✨ Nuevo Chat / Limpiar Sesión", type="primary", use_container_width=True):
        st.session_state.current_session_id = None
        st.session_state.df = None
        st.session_state.df_original = None
        st.session_state.messages = []
        st.session_state.current_file = None
        st.session_state.suggestions = []
        st.session_state.db_schema = None
        st.session_state.db_uri = None
        st.session_state.dataframes = {}
        st.session_state.current_prompt = None
        st.session_state.uploader_key += 1 # Rompe la cache del widget para limpiar el archivo visible
        st.rerun()

    st.header("3. Historial (Memoria)")
    if getattr(st.session_state, 'rename_trigger', False):
        st.session_state.rename_trigger = False
        st.rerun()
        
    sessions = db.get_all_sessions()
    for s in sessions:
        # Mostrar solo los primeros 15 caracteres del nombre
        s_name = s['name'][:15] + "..." if len(s['name']) > 15 else s['name']
        
        col_name, col_edit, col_del = st.columns([6, 1.2, 1.2], vertical_alignment="center")
        with col_name:
            if st.button(f"📄 {s_name} - {s['created_at'][:10]}", key=s['id'], help=s['name'], use_container_width=True):
                st.session_state.current_session_id = s['id']
                st.session_state.messages = db.load_messages(s['id'])
                st.session_state.current_file = s['filename']
                st.session_state.suggestions = []
                st.session_state.current_prompt = None
                
                # REINICIAR variables de Base de Datos para evitar cruces
                st.session_state.db_schema = None
                st.session_state.db_uri = None
                
                # Trigger a UI wipe of the file uploader
                st.session_state.uploader_key += 1
                
                # Auto-load dataset o Auto-conectar DB
                if s['filename'].startswith("DB_URI:"):
                    # Es una sesión de Base de Datos
                    saved_db_uri = s['filename'].replace("DB_URI:", "")
                    st.session_state.db_uri = saved_db_uri
                    st.session_state.df = pd.DataFrame() # DataFrame vacío simulado
                    st.session_state.dataframes = {}
                    st.session_state.current_file = f"DB: {saved_db_uri.split('@')[-1] if '@' in saved_db_uri else saved_db_uri}"
                    
                    try:
                        # Re-construir esquema de la BD en memoria automáticamente
                        engine = create_engine(saved_db_uri)
                        inspector = inspect(engine)
                        tables = inspector.get_table_names()
                        db_schema = {}
                        for table in tables:
                            columns = [col['name'] for col in inspector.get_columns(table)]
                            db_schema[table] = columns
                        st.session_state.db_schema = db_schema
                    except Exception as e:
                        st.error(f"Error al reconectar con el esquema de la base de datos histórica: {e}")
                else:
                    # Es una sesión de Archivo CSV/Excel tradicional
                    # Check if the filename is a JSON list (new format) or a plain string (old format)
                    try:
                        import json
                        file_names = json.loads(s['filename'])
                    except:
                        file_names = [s['filename']]

                    st.session_state.dataframes = {}
                    
                    for i, fname in enumerate(file_names):
                        ext = fname.split('.')[-1]
                        
                        # Support for legacy old sessions where file was saved without index `_0`
                        filepath_new = os.path.join(UPLOAD_DIR, f"{s['id']}_{i}.{ext}")
                        filepath_old = os.path.join(UPLOAD_DIR, f"{s['id']}.{ext}")
                        
                        filepath = filepath_new if os.path.exists(filepath_new) else filepath_old
                        
                        if os.path.exists(filepath):
                            try:
                                if ext == 'csv':
                                    df = safe_read_csv(filepath)
                                elif ext == 'xlsx':
                                    df = pd.read_excel(filepath)
                                st.session_state.dataframes[fname] = df
                                
                                # Set the primary df to the first valid one loaded
                                if i == 0:
                                    st.session_state.df = df.copy()
                            except Exception as e:
                                print(f"Error cargando archivo {fname}: {e}")
                                
                    if not st.session_state.dataframes:
                        st.session_state.df = None
                        
                st.rerun()
                
        with col_edit:
            if st.button("", icon=":material/edit:", key=f"edit_{s['id']}", help="Renombrar sesión", use_container_width=True):
                rename_session_dialog(s['id'], s['name'])
                
        with col_del:
            if st.button("", icon=":material/delete:", key=f"del_{s['id']}", help="Borrar sesión", use_container_width=True):
                db.delete_session(s['id'])
                
                try:
                    import json
                    file_names = json.loads(s['filename'])
                except:
                    file_names = [s['filename']]
                    
                # Borrar todos los archivos fisicos asociados
                for i, fname in enumerate(file_names):
                    ext = fname.split('.')[-1]
                    filepath_new = os.path.join(UPLOAD_DIR, f"{s['id']}_{i}.{ext}")
                    filepath_old = os.path.join(UPLOAD_DIR, f"{s['id']}.{ext}")
                    
                    if os.path.exists(filepath_new):
                        os.remove(filepath_new)
                    elif os.path.exists(filepath_old):
                        os.remove(filepath_old)
                        
                if st.session_state.get('current_session_id') == s['id']:
                    st.session_state.current_session_id = None
                    st.session_state.df = None
                    st.session_state.messages = []
                    st.session_state.current_file = None
                    st.session_state.suggestions = []
                    st.session_state.db_schema = None
                    st.session_state.db_uri = None
                    st.session_state.dataframes = {}
                    st.session_state.uploader_key += 1
                    
                st.rerun()

# Inicializar estados de sesión
if "messages" not in st.session_state:
    st.session_state.messages = []

if "dataframes" not in st.session_state:
    st.session_state.dataframes = {}

if "df" not in st.session_state:
    st.session_state.df = None
    
if "df_original" not in st.session_state:
    st.session_state.df_original = None

if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

if "current_prompt" not in st.session_state:
    st.session_state.current_prompt = None

if "current_file" not in st.session_state:
    st.session_state.current_file = None

if "db_schema" not in st.session_state:
    st.session_state.db_schema = None
    
if "db_uri" not in st.session_state:
    st.session_state.db_uri = None

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# Procesar archivos cargados
if uploaded_files:
    try:
        # Extraemos nombres de los archivos actuales
        nombres_archivos = [f.name for f in uploaded_files]
        str_nombres = ", ".join(nombres_archivos)
        
        if st.session_state.current_file != str_nombres or not st.session_state.dataframes:
            
            st.session_state.dataframes = {}
            for uf in uploaded_files:
                if uf.name.endswith('.csv'):
                    st.session_state.dataframes[uf.name] = safe_read_csv(uf)
                elif uf.name.endswith('.xlsx'):
                    st.session_state.dataframes[uf.name] = pd.read_excel(uf)
                    
            # Si es una subida distinta, creamos nueva sesión (usando el nombre del primer archivo como base)
            if st.session_state.current_file != str_nombres:
                st.session_state.messages = []
                st.session_state.suggestions = []
                st.session_state.current_prompt = None
                
                # REINICIAR variables de Base de Datos para evitar cruces
                st.session_state.db_schema = None
                st.session_state.db_uri = None
                
                # El nombre de sesión es el primer archivo subido + " y otros" si hay más de 1
                base_name = uploaded_files[0].name.split('.')[0]
                if len(uploaded_files) > 1:
                    base_name += f" y {len(uploaded_files)-1} más"
                import json
                
                # Guardar en base de datos la lista de todos los archivos
                file_names = [uf.name for uf in uploaded_files]
                json_filenames = json.dumps(file_names)
                session_id = db.create_session(base_name, json_filenames)
                st.session_state.current_session_id = session_id
                
                # Seteamos el df principal (el primero) para limpieza/gráficos rápidos
                st.session_state.df = st.session_state.dataframes[uploaded_files[0].name].copy()
                st.session_state.df_original = st.session_state.df.copy()
                
                # Guardar TODOS los archivos físicamente para compatibilidad de historial
                for i, uf in enumerate(uploaded_files):
                    ext = uf.name.split('.')[-1]
                    filepath = os.path.join(UPLOAD_DIR, f"{session_id}_{i}.{ext}")
                    with open(filepath, "wb") as f:
                        f.write(uf.getvalue())
            
            st.session_state.current_file = str_nombres
    except Exception as e:
        st.error(f"Error al intentar leer los archivos: {e}")

# Flujo Principal si hay datos cargados o sesión seleccionada
if st.session_state.df is not None or st.session_state.current_session_id is not None:
    tab_chat, tab_clean, tab_graphs = st.tabs(["💬 Chat y Análisis", "🧽 Data Cleansing", "📈 Gráficos"])

    with tab_clean:
        st.subheader("🧽 Limpieza Mágica con IA")
        st.markdown("Deja que nuestra IA estandarice nombres de columnas, elimine nulos totales, impute valores y quite duplicados automáticamente.")
        
        col_clean1, col_clean2 = st.columns([1, 2])
        with col_clean1:
            if st.button("✨ Ejecutar Limpieza Automática", type="primary", use_container_width=True):
                if not api_key:
                    st.error("Necesitas ingresar tu API Key en el panel lateral.")
                else:
                    with st.spinner("🤖 Escribiendo y ejecutando código de limpieza..."):
                        agent = DataAgent(api_key=api_key)
                        success, cleaned_df, explanation, _ = agent.generate_cleaning_code(st.session_state.df)
                        
                        if success:
                            st.session_state.df = cleaned_df
                            st.session_state.messages = [] 
                            st.session_state.suggestions = []
                            st.session_state.cleaning_done = True
                            st.session_state.cleaning_explanation = explanation
                            st.rerun()
                        else:
                            st.error(f"Fallo en la limpieza: {explanation}")
        
        if st.session_state.get("cleaning_done"):
            st.success("¡Datos limpiados exitosamente!")
            st.info(f"💡 **Operaciones realizadas:**\n{st.session_state.cleaning_explanation}")
            
            if st.button("📥 Guardar CSV en Carpeta Local"):
                filepath = os.path.join(EXPORTS_DIR, f"dataset_limpio_{st.session_state.current_session_id}.csv")
                st.session_state.df.to_csv(filepath, index=False, encoding='utf-8-sig')
                st.success(f"✅ Archivo guardado correctamente en tu PC en la ruta:\n`{os.path.abspath(filepath)}`")

    with tab_graphs:
        st.subheader("📈 Previsualización Rápida de Gráficos")
        st.markdown("La IA ha detectado automáticamente y renderizado gráficas útiles basadas en el contenido de tus datos.")
        
        if "preview_charts" not in st.session_state:
            st.session_state.preview_charts = []
        if "preview_explanations" not in st.session_state:
            st.session_state.preview_explanations = []
            
        col_gen1, col_gen2 = st.columns([1, 2])
        with col_gen1:
            if st.button("🤖 Autogenerar Gráficos", type="primary", use_container_width=True):
                if not api_key:
                    st.error("Necesitas ingresar tu API Key en el panel lateral.")
                else:
                    with st.spinner("🤖 Escribiendo y dibujando gráficas instantáneas..."):
                        agent = DataAgent(api_key=api_key)
                        success, fig_list, exp_list, error = agent.generate_preview_charts(st.session_state.df)
                        
                        if success:
                            st.session_state.preview_charts = fig_list
                            st.session_state.preview_explanations = exp_list
                            st.rerun()
                        else:
                            st.error(f"Error generando gráficos: {error}")
        
        if st.session_state.preview_charts:
            st.divider()
            
            # Display charts in pairs (2 columns)
            cols = st.columns(2)
            for idx, fig in enumerate(st.session_state.preview_charts):
                col_idx = idx % 2
                with cols[col_idx]:
                    st.plotly_chart(fig, use_container_width=True)
                    if idx < len(st.session_state.preview_explanations):
                        st.info(f"💡 {st.session_state.preview_explanations[idx]}")

    with tab_chat:
        # Dividir la pantalla en dos columnas principales
        left_col, right_col = st.columns([1, 1.2], gap="large")

        with left_col:
            st.subheader("📊 Resumen Rápido del Dataset")
            
            if st.session_state.df is None:
                st.warning(f"⚠️ Estás viendo el chat histórico de '{st.session_state.current_file}'. Para continuar interactuando o ver el resumen, por favor vuelve a subir el archivo en el panel izquierdo.")
            else:
                if st.session_state.db_schema:
                    # KPIs for Database
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total Tablas", len(st.session_state.db_schema))
                    with col2:
                        total_cols = sum(len(cols) for cols in st.session_state.db_schema.values())
                        st.metric("Total Columnas Visibles", total_cols)
                    st.divider()
                else:
                    # 1. KPIs Rápido para Archivos
                    col1, col2 = st.columns(2)
                    with col1:
                        filas_str = f"{st.session_state.df.shape[0]:,}".replace(',', '.')
                        st.metric("Total Filas", filas_str)
                        
                        nulos = int(st.session_state.df.isnull().sum().sum())
                        total_elements = st.session_state.df.shape[0] * st.session_state.df.shape[1]
                        nulos_pct = (nulos / total_elements) * 100 if total_elements > 0 else 0
                        nulos_str = f"{nulos:,} ({nulos_pct:.1f}%)".replace(',', '.')
                        st.metric("Valores Nulos", nulos_str)
                        
                    with col2:
                        cols_str = f"{st.session_state.df.shape[1]:,}".replace(',', '.')
                        st.metric("Total Columnas", cols_str)
                        
                        mem_usage = st.session_state.df.memory_usage(deep=True).sum() / (1024 * 1024)
                        st.metric("Peso en Memoria", f"{mem_usage:.2f} MB")
                        
                    st.divider()

                # 2. Sugerencias Inteligentes
                if api_key and not st.session_state.suggestions:
                    with st.spinner("🤖 Analizando dataset para generar sugerencias inteligentes..."):
                        agent = DataAgent(api_key=api_key)
                        st.session_state.suggestions = agent.generate_suggestions(st.session_state.df, db_schema=st.session_state.db_schema)
                        st.rerun() # Refresh para mostrar los botones
                
                if api_key and st.session_state.suggestions:
                    col_q, col_btn = st.columns([4, 1])
                    with col_q:
                        st.markdown("### 💡 Haz una pregunta rápida:")
                    with col_btn:
                        if st.button("🔄 Nuevas", help="Generar nuevas sugerencias", use_container_width=True):
                            st.session_state.suggestions = []
                            st.rerun()
                            
                    for i, sugg in enumerate(st.session_state.suggestions):
                        if st.button(sugg, key=f"sugg_{i}", use_container_width=True):
                            st.session_state.current_prompt = sugg
                            st.rerun()
                    st.divider()

                # Componente: PDF Report
                st.markdown("### 📄 Reporte PDF Automático")
                if st.button("Generar Analisis PDF", use_container_width=True):
                    with st.spinner("🤖 Analizando y diseñando reporte ejecutivo..."):
                        agent = DataAgent(api_key=api_key)
                        try:
                            pdf_bytes = agent.generate_pdf_report(
                                df=st.session_state.df,
                                db_schema=st.session_state.db_schema,
                                db_uri=st.session_state.db_uri
                            )
                            st.session_state.pdf_bytes = bytes(pdf_bytes)
                        except Exception as e:
                            st.error(f"{e}")
                
                if "pdf_bytes" in st.session_state:
                    if st.button("📥 Guardar PDF en Carpeta Local", use_container_width=True):
                        filepath = os.path.join(EXPORTS_DIR, f"reporte_ejecutivo_{st.session_state.current_session_id}.pdf")
                        with open(filepath, "wb") as f:
                            f.write(st.session_state.pdf_bytes)
                        st.success(f"✅ PDF guardado correctamente en tu PC en la ruta:\n`{os.path.abspath(filepath)}`")
                
                st.divider()

                # Componente: Data Preview (Editable)
                if st.session_state.db_schema:
                    with st.expander("👁️ Ver Estructura de Base de Datos", expanded=False):
                        st.markdown("Tablas y columnas mapeadas desde la conexión SQL:")
                        st.json(st.session_state.db_schema)
                else:
                    with st.expander("👁️ Ver Data Preview (Editor Interactivo)", expanded=False):
                        st.markdown("Cualquier cambio que realices aquí se aplicará automáticamente al dataset activo correspondiente.")
                        
                        if st.session_state.dataframes:
                            # Create a tab for every loaded dataset
                            df_names = list(st.session_state.dataframes.keys())
                            tabs = st.tabs(df_names)
                            
                            for i, df_name in enumerate(df_names):
                                with tabs[i]:
                                    current_df = st.session_state.dataframes[df_name]
                                    edited_df = st.data_editor(current_df, num_rows="dynamic", use_container_width=True, key=f"editor_{df_name}")
                                    st.session_state.dataframes[df_name] = edited_df
                                    
                                    # Override the main df if it's the primary one being edited
                                    if uploaded_files and len(uploaded_files) > 0 and df_name == uploaded_files[0].name:
                                        st.session_state.df = edited_df
                                        
                                    st.caption(f"Archivo: {df_name} | Total de filas: {current_df.shape[0]} | Total de columnas: {current_df.shape[1]}")
                                    
                        elif st.session_state.df is not None:
                            # Fallback for old history sessions without 'dataframes' dict
                            edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", use_container_width=True)
                            st.session_state.df = edited_df
                            st.caption(f"Total de filas: {st.session_state.df.shape[0]} | Total de columnas: {st.session_state.df.shape[1]}")
                        
                        if st.session_state.get('df_original') is not None:
                            if st.button("⏪ Revertir a Original", type="secondary"):
                                st.session_state.df = st.session_state.df_original.copy()
                                # Limpiar el dict de diccionarios también si hay uploaded_files actual
                                if uploaded_files and len(uploaded_files) > 0:
                                     st.session_state.dataframes[uploaded_files[0].name] = st.session_state.df_original.copy()
                                st.rerun()

        with right_col:
            st.subheader("💬 Chat Analítico")
            
            # Opciones de exportación de Chat
            if st.session_state.messages:
                export_html = "<h2>Reporte de Descubrimiento de Datos</h2>"
                for msg in st.session_state.messages:
                    role = "👤 Usuario:" if msg["role"] == "user" else "🤖 Agente AI:"
                    export_html += f"<h3>{role}</h3>"
                    if "text" in msg and msg["text"]:
                        export_html += f"<p>{msg['text']}</p>"
                    if "fig" in msg and msg["fig"]:
                        export_html += msg["fig"].to_html(include_plotlyjs="cdn", full_html=False)
                    if "code" in msg and msg["code"]:
                        export_html += f"<pre><code>{msg['code']}</code></pre>"
                    if "insights_dict" in msg and msg["insights_dict"]:
                        export_html += "<h4>📌 Insights Clave</h4><ul>"
                        for k, v in msg["insights_dict"].items():
                            export_html += f"<li><b>{k}:</b> {v}</li>"
                        export_html += "</ul>"
                    export_html += "<hr>"
                    
                if st.button("📥 Exportar Reporte HTML a Carpeta Local", use_container_width=True):
                    filepath = os.path.join(EXPORTS_DIR, f"reporte_chat_{st.session_state.current_session_id}.html")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(export_html)
                    st.success(f"✅ HTML guardado correctamente en tu PC en la ruta:\n`{os.path.abspath(filepath)}`")

            # Contenedor para el historial de mensajes
            chat_container = st.container(height=500)
            
            with chat_container:
                if not st.session_state.messages:
                    st.info("👋 ¡Hola! Soy tu IA experta en datos. Elige una sugerencia o hazme cualquier pregunta.")
                    
                # Mostrar historial de Chat
                for msg in st.session_state.messages:
                    with st.chat_message(msg["role"]):
                        if "text" in msg and msg["text"] is not None:
                            st.markdown(msg["text"])
                        if "fig" in msg and msg["fig"] is not None:
                            st.plotly_chart(msg["fig"], use_container_width=True)
                        if "insights_dict" in msg and msg["insights_dict"]:
                            st.markdown("##### 📌 Insights Clave")
                            items = list(msg["insights_dict"].items())
                            cols = st.columns(len(items))
                            for i, (k, v) in enumerate(items):
                                cols[i].markdown(f"**{k}**<br><span style='font-size: 1.1em;'>{str(v)}</span>", unsafe_allow_html=True)
                        if "explanation" in msg and msg["explanation"] is not None:
                            st.info(f"💡 **Conclusión de IA:**\n{msg['explanation']}")
                        if "code" in msg and msg["code"] is not None:
                            with st.expander("🔍 Auditoría de Código"):
                                st.code(msg["code"], language="python")

            # Input de Chat
            if not api_key:
                st.warning("⚠️ Recuerda ingresar tu Gemini API Key en el panel lateral superior para poder chatear.")
            elif st.session_state.df is None:
                st.info("Sube el dataset desde el panel izquierdo para poder continuar chateando en esta sesión.")
            else:
                # Input de Chat normal
                prompt = st.chat_input("Pregúntale a tus datos (ej. 'Genera un histograma de edades')...")
                
                # Check si se presionó una sugerencia o se mandó input manualmente
                if st.session_state.get('current_prompt'):
                    prompt = st.session_state.current_prompt
                    st.session_state.current_prompt = None

                if prompt:
                    # Mostrar pregunta del usuario
                    st.session_state.messages.append({"role": "user", "text": prompt})
                    with chat_container:
                        with st.chat_message("user"):
                            st.markdown(prompt)

                    # Respuesta del Agente
                    with chat_container:
                        with st.chat_message("assistant"):
                            with st.spinner("🧠 Programando y analizando datos..."):
                                agent = DataAgent(api_key=api_key)
                                result, fig, explanation, insights_dict, code = agent.process_query(
                                    df=st.session_state.df,
                                    dataframes=st.session_state.dataframes,
                                    user_query=prompt,
                                    db_schema=st.session_state.db_schema,
                                    db_uri=st.session_state.db_uri,
                                    chat_history=st.session_state.messages
                                )
                                
                                response_text = None
                                if result:
                                    response_text = str(result)
                                    st.markdown(response_text)
                                elif fig is None and explanation is None and not insights_dict:
                                    response_text = "Se ejecutó la instrucción correctamente, pero el script no devolvió un resultado en texto o un gráfico."
                                    st.markdown(response_text)
                                if fig is not None:
                                    st.plotly_chart(fig, use_container_width=True)
                                    
                                if insights_dict:
                                    st.markdown("##### 📌 Insights Clave")
                                    items = list(insights_dict.items())
                                    cols = st.columns(len(items))
                                    for i, (k, v) in enumerate(items):
                                        cols[i].markdown(f"**{k}**<br><span style='font-size: 1.1em;'>{str(v)}</span>", unsafe_allow_html=True)
                                        
                                if explanation is not None:
                                    st.info(f"💡 **Conclusión de IA:**\n{explanation}")

                                if code is not None:
                                    with st.expander("🔍 Auditoría de Código"):
                                        st.code(code, language="python")

                                # Guardar en historial
                                msg_data = {
                                    "role": "assistant",
                                    "text": response_text,
                                    "fig": fig,
                                    "explanation": explanation,
                                    "insights_dict": insights_dict,
                                    "code": code
                                }
                                st.session_state.messages.append(msg_data)
                                
                                # Guardar en base de datos
                                db.save_message(st.session_state.current_session_id, "user", prompt)
                                db.save_message(st.session_state.current_session_id, "assistant", response_text, explanation, fig, insights_dict)
else:
    # Estado inicial sin archivo
    st.info("👈 Por favor, carga un archivo CSV o Excel desde el panel lateral izquierdo para comenzar el análisis conversacional.")
