import sqlite3
import os

DB_PATH = "app.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if secret_key exists
        cursor.execute("PRAGMA table_info(user_api_keys)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "secret_key" not in columns:
            print("Adding secret_key column...")
            cursor.execute("ALTER TABLE user_api_keys ADD COLUMN secret_key TEXT")
            conn.commit()

        if "description" not in columns:
            print("Adding description column...")
            cursor.execute("ALTER TABLE user_api_keys ADD COLUMN description TEXT")
            conn.commit()

        if "last_used" not in columns:
            print("Adding last_used column...")
            cursor.execute("ALTER TABLE user_api_keys ADD COLUMN last_used DATETIME")
            conn.commit()
            
        print("Migration check complete.")

    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
