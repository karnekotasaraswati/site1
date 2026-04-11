import os
import sqlite3
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Supabase Configuration
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip() or None
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip() or None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")

def get_supabase():
    """Initializes Supabase client only if credentials and network are available."""
    url = (os.getenv("SUPABASE_URL") or "").strip() or None
    key = (os.getenv("SUPABASE_KEY") or "").strip() or None
    
    if not url or not key:
        return None
        
    try:
        return create_client(url, key)
    except Exception as e:
        print(f"DEBUG SUPABASE: Client creation error: {e}")
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

    # Table for Chat History
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table for Feedback based on requirements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT,
            session_id TEXT,
            question TEXT,
            answer TEXT,
            feedback TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def save_api_key(api_key: str, secret_key: str = None, description: str = "My Key"):
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

    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("user_api_keys").insert(
                {"api_key": api_key, "secret_key": secret_key, "description": description}
            ).execute()
        except Exception as e:
            print(f"Supabase user_api_keys insert error: {e}")

    return True, None

def delete_api_key(key_id: int):
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("user_api_keys").delete().eq("id", key_id).execute()
        except Exception as e: 
            pass

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_api_keys WHERE id = ?", (int(key_id),))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        return False

def get_all_keys_info():
    results = []
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
        pass
    return results

def update_key_usage(api_key: str):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_api_keys SET last_used = ? WHERE api_key = ?", (now, api_key))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("user_api_keys").update({"last_used": now}).eq("api_key", api_key).execute()
        except Exception:
            pass

def save_chat(session_id: str, question: str, answer: str):
    # Saves a conversation to Supabase and SQLite fallback.
    supabase = get_supabase()

    # SUPABASE
    if supabase:
        try:
            supabase.table("chat_history").insert(
                {"session_id": session_id, "question": question, "answer": answer}
            ).execute()
        except Exception as e:
            print(f"Supabase chat save error: {e}")

    # SQLITE FALLBACK
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (session_id, question, answer) VALUES (?, ?, ?)",
            (session_id, question, answer)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def save_feedback(session_id: str, question: str, answer: str, feedback: str):
    # Saves user feedback to Supabase and SQLite fallback.
    import uuid
    feedback_id = str(uuid.uuid4())
    supabase = get_supabase()

    # SUPABASE
    if supabase:
        try:
            supabase.table("feedback").insert(
                {"id": feedback_id, "session_id": session_id, "question": question, "answer": answer, "feedback": feedback}
            ).execute()
        except Exception as e:
            print(f"Supabase feedback save error: {e}")

    # SQLITE FALLBACK
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO feedback (id, session_id, question, answer, feedback) VALUES (?, ?, ?, ?, ?)",
            (feedback_id, session_id, question, answer, feedback)
        )
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def verify_api_key_pair(api_key: str, secret_key: str):
    supabase = get_supabase()
    if supabase:
        try:
            response = supabase.table("user_api_keys").select("*").eq("api_key", api_key).eq("secret_key", secret_key).execute()
            if response.data:
                return True
        except Exception as e:
            pass

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
    key_pairs = {}
    valid_env_keys = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    for k in valid_env_keys:
        key_pairs[k] = None

    try:
        supabase = get_supabase()
        if supabase:
            response = supabase.table("user_api_keys").select("api_key", "secret_key").execute()
            if response.data:
                for row in response.data:
                    key_pairs[row["api_key"]] = row["secret_key"]
    except:
        pass

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

# --- RAG Implementation ---
knowledge_texts = []
knowledge_embeddings = None
embedder = None

def init_knowledge_base():
    global knowledge_texts, knowledge_embeddings, embedder
    try:
        from sentence_transformers import SentenceTransformer
        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        print("sentence-transformers not installed. RAG will just return raw text.")
        return

    text_file = os.path.join(BASE_DIR, "knowledge.txt")
    if os.path.exists(text_file):
        with open(text_file, "r", encoding="utf-8") as f:
            content = f.read()
            # Split into chunks (simple double newline split)
            knowledge_texts = [chunk.strip() for chunk in content.split("\\n") if chunk.strip()]
            
        if knowledge_texts:
            print("Encoding knowledge base...")
            knowledge_embeddings = embedder.encode(knowledge_texts, convert_to_tensor=True)
            print("Knowledge base encoded.")

def retrieve_knowledge(query: str, top_k: int = 3):
    global knowledge_texts, knowledge_embeddings, embedder
    if not knowledge_texts:
        # Fallback raw text if embedder fails
        text_file = os.path.join(BASE_DIR, "knowledge.txt")
        if os.path.exists(text_file):
            with open(text_file, "r", encoding="utf-8") as f:
                return f.read()
        return "StarZopp: Creative Networking."
        
    if embedder is None or knowledge_embeddings is None:
        return " ".join(knowledge_texts)

    from sentence_transformers import util
    query_embedding = embedder.encode(query, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, knowledge_embeddings, top_k=top_k)[0]
    
    results = [knowledge_texts[hit['corpus_id']] for hit in hits]
    return " ".join(results)