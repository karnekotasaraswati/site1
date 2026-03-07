import secrets
import os
from pathlib import Path

def generate_api_key(length=32):
    """Generates a secure random API key."""
    return secrets.token_urlsafe(length)

def save_key_to_env(key):
    """Saves the key to the .env file."""
    env_path = Path(".env")
    
    existing_content = ""
    if env_path.exists():
        existing_content = env_path.read_text()

    if "API_KEYS=" in existing_content:
        # Append to existing keys
        lines = existing_content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("API_KEYS="):
                new_line = f"{line},{key}"
                lines[i] = new_line
                break
        new_content = "\n".join(lines)
    else:
        # Add new entry
        new_content = existing_content + f"\nAPI_KEYS={key}\n"

    env_path.write_text(new_content.strip() + "\n")
    print(f"Key generated and saved to .env: {key}")

if __name__ == "__main__":
    new_key = generate_api_key()
    save_key_to_env(new_key)
    print("\nIMPORTANT: Keep your .env file secure and never commit it to version control!")
