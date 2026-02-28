import sqlite3
import json
import uuid
from datetime import datetime
import plotly.io as pio

DB_FILE = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT,
            filename TEXT,
            created_at TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            text TEXT,
            explanation TEXT,
            fig_json TEXT,
            insights_json TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    ''')
    conn.commit()
    conn.close()

def create_session(name, filename):
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (id, name, filename, created_at) VALUES (?, ?, ?, ?)",
        (session_id, name, filename, datetime.now())
    )
    conn.commit()
    conn.close()
    return session_id

def get_all_sessions():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, filename, created_at FROM sessions ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "filename": r[2], "created_at": r[3]} for r in rows]

def save_message(session_id, role, text, explanation=None, fig=None, insights_dict=None):
    if not session_id:
        return
        
    fig_json = fig.to_json() if fig is not None else None
    insights_json = json.dumps(insights_dict) if insights_dict else None
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (session_id, role, text, explanation, fig_json, insights_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, role, text, explanation, fig_json, insights_json, datetime.now())
    )
    conn.commit()
    conn.close()

def load_messages(session_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT role, text, explanation, fig_json, insights_json FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    rows = c.fetchall()
    conn.close()
    
    messages = []
    for r in rows:
        role, text, explanation, fig_json, insights_json = r
        fig = pio.from_json(fig_json) if fig_json else None
        insights_dict = json.loads(insights_json) if insights_json else None
        messages.append({
            "role": role,
            "text": text,
            "explanation": explanation,
            "fig": fig,
            "insights_dict": insights_dict
        })
    return messages

def get_session(session_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, filename, created_at FROM sessions WHERE id = ?", (session_id,))
    r = c.fetchone()
    conn.close()
    if r:
        return {"id": r[0], "name": r[1], "filename": r[2], "created_at": r[3]}
    return None

def delete_session(session_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

def rename_session(session_id, new_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE sessions SET name = ? WHERE id = ?", (new_name, session_id))
    conn.commit()
    conn.close()
