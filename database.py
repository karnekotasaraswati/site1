import os
import sqlite3
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Supabase Configuration (Optional, for persistent storage)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

def get_supabase():
    """Initializes Supabase client only if credentials and network are available."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        # Create client with a small timeout for requests
        # Note: supabase-py uses postgrest-py internally which uses httpx
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for API Keys
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            secret_key TEXT,
            description TEXT,
            last_used DATETIME,
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

    # Create feedback table if missing
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            response TEXT,
            feedback_type TEXT,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_api_key(api_key: str, secret_key: str = None, description: str = "My Key"):
    """Saves the API key to both Local SQLite (primary) and Supabase (sync)."""
    # 🔹 Always save to local SQLite first (instant and reliable)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_api_keys (api_key, secret_key, description) VALUES (?, ?, ?)", 
            (api_key, secret_key, description)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return False, str(e)

    # 🔹 Then try to sync with Supabase in a fire-and-forget manner
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("user_api_keys").insert(
                {"api_key": api_key, "secret_key": secret_key, "description": description}
            ).execute()
        except Exception:
            # Silent fail for Supabase, data is already saved locally
            pass

    return True, None


def delete_api_key(key_id: int):
    print(f"DEBUG: Attempting to delete key with ID: {key_id}")
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("user_api_keys").delete().eq("id", key_id).execute()
        except Exception as e: 
            print(f"DEBUG: Supabase delete error: {e}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_api_keys WHERE id = ?", (int(key_id),))
        rows_affected = conn.total_changes
        conn.commit()
        conn.close()
        print(f"DEBUG: SQLite delete success. Rows affected: {rows_affected}")
        return True
    except Exception as e:
        print(f"DEBUG: SQLite delete error: {e}")
        return False


def get_all_keys_info():
    """Returns metadata for all keys, combining Local SQLite and any reachable Supabase data."""
    results = []
    
    # 🔹 Primary: Fetch from Local SQLite (Always works, instant)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, api_key, secret_key, description, last_used, created_at FROM user_api_keys ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        for row in rows:
            key = row['api_key']
            secret = row['secret_key'] or ""
            
            results.append({
                "id": row['id'],
                "api_key": key,
                "secret_key": secret,
                "description": row['description'] or "No description",
                "last_used": row['last_used'] or "Never used",
                "created_at": row['created_at']
            })
        conn.close()
    except Exception as e:
        print(f"DEBUG: SQLite fetch error: {e}")

    # Note: We don't merge with Supabase here to avoid dashboard lag.
    # Supabase is used primarily for persistent backups and sync between deploys.
    return results


def update_key_usage(api_key: str):
    """Updates the last_used timestamp. Prioritizes local SQLite for performance."""
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # 🔹 Update Local SQLite (Instant)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user_api_keys SET last_used = ? WHERE api_key = ?", 
            (now, api_key)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DEBUG: SQLite usage update error: {e}")

    # 🔹 Sync with Supabase (Optional network call)
    supabase = get_supabase()
    if supabase:
        try:
            # We don't await this or block on it; fire-and-forget
            supabase.table("user_api_keys").update({"last_used": now}).eq("api_key", api_key).execute()
        except Exception:
            pass


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


def save_feedback(prompt: str, response: str, feedback_type: str, comment: str = ""):
    """Saves user feedback to Supabase and SQLite fallback."""
    supabase = get_supabase()

    # 🔹 SUPABASE
    if supabase:
        try:
            supabase.table("feedback").insert(
                {"prompt": prompt, "response": response, "feedback_type": feedback_type, "comment": comment}
            ).execute()
        except Exception as e:
            print("Supabase feedback save error:", e)

    # 🔹 SQLITE FALLBACK
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO feedback (prompt, response, feedback_type, comment) VALUES (?, ?, ?, ?)",
            (prompt, response, feedback_type, comment)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def verify_api_key_pair(api_key: str, secret_key: str):
    """Verifies that the provided API key and Secret key pair exist and match."""
    supabase = get_supabase()

    if supabase:
        try:
            response = supabase.table("user_api_keys").select("*").eq("api_key", api_key).eq("secret_key", secret_key).execute()
            if response.data:
                return True
        except Exception as e:
            print("Supabase verify error:", e)

    # SQLite fallback
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM user_api_keys WHERE api_key = ? AND secret_key = ?", (api_key, secret_key))
        result = cursor.fetchone()
        conn.close()

        return result is not None

    except:
        return False


def load_all_key_pairs():
    """Returns a dictionary mapping API keys to their Secret keys for memory caching."""
    key_pairs = {}
    
    # 🔹 Load from Env
    valid_env_keys = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    for k in valid_env_keys:
        key_pairs[k] = None

    # 🔹 Load from Supabase
    try:
        supabase = get_supabase()
        if supabase:
            response = supabase.table("user_api_keys").select("api_key", "secret_key").execute()
            if response.data:
                for row in response.data:
                    key_pairs[row["api_key"]] = row["secret_key"]
    except:
        pass

    # 🔹 Load from SQLite
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT api_key, secret_key FROM user_api_keys")
        for row in cursor.fetchall():
            key_pairs[row[0]] = row[1]
        conn.close()
    except:
        pass
        
    return key_pairs