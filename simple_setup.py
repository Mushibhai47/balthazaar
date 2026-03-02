"""
Simple credential setup - ZERO external dependencies
Uses base64 encoding (built into Python) instead of cryptography
"""
import sqlite3
import json
import base64
import os

def encode_credentials(creds_dict):
    """Encode credentials using base64 (built-in, no packages needed)"""
    json_creds = json.dumps(creds_dict)
    encoded = base64.b64encode(json_creds.encode()).decode()
    return encoded

def setup_credential(service_name, creds_dict):
    """Insert or update credential in database"""
    conn = sqlite3.connect('balthazaar.db')
    cursor = conn.cursor()

    # Check if credential exists
    cursor.execute("SELECT id FROM api_credentials WHERE service_name = ?", (service_name,))
    existing = cursor.fetchone()

    encoded_creds = encode_credentials(creds_dict)

    if existing:
        # Update
        cursor.execute(
            "UPDATE api_credentials SET encrypted_credentials = ?, is_active = 1 WHERE service_name = ?",
            (encoded_creds, service_name)
        )
        print(f"[OK] Updated {service_name} credentials")
    else:
        # Insert
        cursor.execute(
            "INSERT INTO api_credentials (service_name, encrypted_credentials, is_active) VALUES (?, ?, 1)",
            (service_name, encoded_creds)
        )
        print(f"[OK] Created {service_name} credentials")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
Usage:
  python simple_setup.py <service> <credentials>

Examples:
  python simple_setup.py openai sk-proj-abc123...
  python simple_setup.py gemini AIza...
  python simple_setup.py youtube AIza...
  python simple_setup.py ubersuggest email@example.com password123
""")
        sys.exit(1)

    service = sys.argv[1].lower()

    if service == "openai" and len(sys.argv) == 3:
        setup_credential("openai", {"api_key": sys.argv[2]})
    elif service == "gemini" and len(sys.argv) == 3:
        setup_credential("google_gemini", {"api_key": sys.argv[2]})
    elif service == "youtube" and len(sys.argv) == 3:
        setup_credential("youtube", {"api_key": sys.argv[2]})
    elif service == "ubersuggest" and len(sys.argv) == 4:
        setup_credential("ubersuggest", {"email": sys.argv[2], "password": sys.argv[3]})
    else:
        print("Invalid arguments. Run without arguments for usage help.")
        sys.exit(1)
