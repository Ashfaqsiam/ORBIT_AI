# ==========================================
# IMPORTS & INITIALIZATION
# ==========================================
import os
import re
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import webbrowser
from urllib.parse import quote_plus
import threading
import pyttsx3
import speech_recognition as sr
import webview
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from ai import ask_ai

app = Flask(__name__, template_folder="templates", static_folder="templates")
CORS(app)

current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = Path(current_dir) / "orbit_history.db"
settings_path = Path(current_dir) / "orbit_settings.json"

current_user = "Ashfaq"
tts_enabled = True


# ==========================================
# SETTINGS & LANGUAGE MODE HELPERS
# ==========================================
def load_language_mode():
    try:
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            mode = str(data.get("language_mode", "English")).title()
            return mode if mode in ("Bangla", "English") else "English"
    except (OSError, ValueError, TypeError):
        pass
    return "English"

def save_language_mode(mode):
    try:
        settings_path.write_text(json.dumps({"language_mode": mode}, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


# ==========================================
# DATABASE SETUP (USERS, SESSIONS, MESSAGES)
# ==========================================
def init_history_db():
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'New conversation', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE)""")

init_history_db()

def create_session(title="New conversation", username="Ashfaq"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db_path) as db:
        cur = db.execute("INSERT INTO sessions(username, title, created_at, updated_at) VALUES(?,?,?,?)",
                         (username, title, now, now))
        return cur.lastrowid

def save_message(session_id, role, content, username="Ashfaq"):
    if not session_id:
        session_id = create_session(username=username)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO messages(session_id, role, content, created_at) VALUES(?,?,?,?)",
                   (session_id, role, content, now))
        if role == "user":
            row = db.execute("SELECT title FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row and row[0] == "New conversation":
                title = " ".join(content.strip().split())[:48] or "New conversation"
                db.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, now, session_id))
            else:
                db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
        else:
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    return session_id


# ==========================================
# DESKTOP COMMANDS & TTS HELPERS
# ==========================================
def handle_desktop_command(message):
    compact = " ".join(message.strip().lower().split())
    if any(phrase in compact for phrase in ("open downloads", "downloads open", "download folder")):
        path = Path.home() / "Downloads"
        if path.is_dir():
            os.startfile(str(path))
            return f"Opening Downloads folder: {path}"
    if any(phrase in compact for phrase in ("open youtube", "youtube open", "youtube kholo")):
        webbrowser.open("https://www.youtube.com/", new=2)
        return "Opening YouTube in your default browser."
    return None

def speak_text(text, language_mode):
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 165 if language_mode == "Bangla" else 175)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception:
        pass


# ==========================================
# FLASK API ROUTES
# ==========================================
@app.route("/")
def index():
    return render_template("index.html")

# User Registration Route
@app.route("/api/register", methods=["POST"])
def register_user():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
        
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(db_path) as db:
            db.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)", (username, password, now))
        return jsonify({"status": "success", "message": "Account created successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400

# User Login Route
@app.route("/api/login", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    with sqlite3.connect(db_path) as db:
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        
    if user or (username == "Ashfaq" and password == "12345"):
        return jsonify({"status": "success", "username": username})
    return jsonify({"error": "Invalid username or password"}), 401

# Settings Route (Fixes the settings save error)
@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        data = request.json
        mode = data.get("language_mode", "English")
        save_language_mode(mode)
        return jsonify({"status": "success", "language_mode": mode})
    return jsonify({"language_mode": load_language_mode()})

# Fetch Chat Sessions
@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    global current_user
    with sqlite3.connect(db_path) as db:
        rows = db.execute("SELECT id, title, updated_at FROM sessions WHERE username=? ORDER BY updated_at DESC", (current_user,)).fetchall()
    sessions = [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]
    return jsonify(sessions)

# Create New Session
@app.route("/api/sessions/new", methods=["POST"])
def new_session():
    global current_user
    sid = create_session(username=current_user)
    return jsonify({"session_id": sid})

# Fetch Messages for a Session
@app.route("/api/session/<int:sid>/messages", methods=["GET"])
def get_messages(sid):
    with sqlite3.connect(db_path) as db:
        rows = db.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    messages = [{"role": r[0], "content": r[1]} for r in rows]
    return jsonify(messages)

# Python Voice Recognition Endpoint
@app.route("/api/voice", methods=["POST"])
def record_voice():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.2
    lang_mode = load_language_mode()
    locale = "bn-BD" if lang_mode == "Bangla" else "en-US"
    
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=25)
        transcript = recognizer.recognize_google(audio, language=locale).strip()
        return jsonify({"transcript": transcript})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Chat Endpoint (AI & Desktop Commands)
@app.route("/api/chat", methods=["POST"])
def chat():
    global current_user
    data = request.json
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id")
    
    if not session_id:
        session_id = create_session(username=current_user)
        
    if not user_message:
        return jsonify({"error": "Empty message"}), 400
        
    lang_mode = load_language_mode()
    
    desktop_reply = handle_desktop_command(user_message)
    if desktop_reply:
        sid = save_message(session_id, "user", user_message, current_user)
        save_message(sid, "assistant", desktop_reply, current_user)
        return jsonify({"response": desktop_reply, "session_id": sid})
        
    sid = save_message(session_id, "user", user_message, current_user)
    
    with sqlite3.connect(db_path) as db:
        rows = db.execute("SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
    conversation = [{"role": r, "content": c} for r, c in rows[-12:]]
    
    try:
        ai_answer = ask_ai(conversation, language=lang_mode)
    except Exception as e:
        ai_answer = f"Error communicating with AI: {e}"
        
    save_message(sid, "assistant", ai_answer, current_user)
    
    if tts_enabled:
        threading.Thread(target=speak_text, args=(ai_answer, lang_mode), daemon=True).start()
        
    return jsonify({"response": ai_answer, "session_id": sid})


# ==========================================
# MAIN ENTRY POINT (FLASK + PYWEBVIEW)
# ==========================================
def run_flask():
    app.run(port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    webview.create_window(
        "ORBIT | AI Desktop Assistant", 
        "http://localhost:5000", 
        width=1320, 
        height=840, 
        min_size=(980, 640)
    )
    webview.start()