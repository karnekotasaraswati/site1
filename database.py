import os
import sqlite3
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")


def get_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for API Keys
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table for Chat History (NEW)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def save_api_key(api_key: str):

    supabase = get_supabase()

    # 🔹 SUPABASE
    if supabase:
        try:
            response = supabase.table("user_api_keys").insert(
                {"api_key": api_key}
            ).execute()

            if response.data:
                return True, None

        except Exception as e:
            print("Supabase error:", e)

    # 🔹 SQLITE FALLBACK
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("INSERT INTO user_api_keys (api_key) VALUES (?)", (api_key,))
        conn.commit()
        conn.close()

        return True, None

    except Exception as e:
        return False, str(e)


def save_chat(prompt: str, response: str):
    """Saves a conversation to Supabase and SQLite fallback."""
    supabase = get_supabase()

    # 🔹 SUPABASE
    if supabase:
        try:
            supabase.table("chat_history").insert(
                {"prompt": prompt, "response": response}
            ).execute()
        except Exception as e:
            print("Supabase chat save error:", e)

    # 🔹 SQLITE FALLBACK
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (prompt, response) VALUES (?, ?)",
            (prompt, response)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def verify_api_key(api_key: str):

    supabase = get_supabase()

    if supabase:
        try:
            response = supabase.table("user_api_keys").select("*").eq("api_key", api_key).execute()
            if response.data:
                return True
        except Exception as e:
            print("Supabase verify error:", e)

    # SQLite fallback
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM user_api_keys WHERE api_key = ?", (api_key,))
        result = cursor.fetchone()
        conn.close()

        return result is not None

    except:
        return False