import webview
import threading
import subprocess
import time
import sys
import os

def start_streamlit():
    # Inicia el proceso de Streamlit en segundo plano usando el mismo ejecutable de Python
    # "--server.headless=true" evita que Streamlit intente abrir el navegador automáticamente
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "main.py", "--server.headless=true"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=env,
        stdout=subprocess.DEVNULL, # Silenciamos los logs de streamlit para la app de escritorio
        stderr=subprocess.DEVNULL
    )

if __name__ == '__main__':
    # Lanzar Streamlit en un hilo en segundo plano (daemon=True para que se cierre con el programa principal)
    t = threading.Thread(target=start_streamlit)
    t.daemon = True
    t.start()
    
    # Dar unos segundos de gracia al servidor para arrancar por completo
    time.sleep(3)
    
    # Crear la ventana nativa apuntando al servidor local de Streamlit
    window = webview.create_window(
        "Conversational Data Discovery", 
        "http://localhost:8501",
        width=1200,
        height=800,
        text_select=True
    )
    
    # Iniciar el bucle de eventos de la ventana de escritorio
    webview.start()
