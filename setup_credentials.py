"""
Helper script to set up API credentials in the database
Run this to add/update API keys for data sources
"""
from main import app
from database.models import db, APICredential

def setup_openai(api_key):
    """Set up OpenAI API credentials"""
    with app.app_context():
        # Check if credentials already exist
        cred = APICredential.query.filter_by(service_name="openai").first()

        if cred:
            print("Updating existing OpenAI credentials...")
            cred.set_credentials({"api_key": api_key})
        else:
            print("Creating new OpenAI credentials...")
            cred = APICredential(service_name="openai")
            cred.set_credentials({"api_key": api_key})
            db.session.add(cred)

        db.session.commit()
        print("[OK] OpenAI credentials saved successfully!")


def setup_google_gemini(api_key):
    """Set up Google Gemini API credentials"""
    with app.app_context():
        cred = APICredential.query.filter_by(service_name="google_gemini").first()

        if cred:
            print("Updating existing Google Gemini credentials...")
            cred.set_credentials({"api_key": api_key})
        else:
            print("Creating new Google Gemini credentials...")
            cred = APICredential(service_name="google_gemini")
            cred.set_credentials({"api_key": api_key})
            db.session.add(cred)

        db.session.commit()
        print("[OK] Google Gemini credentials saved successfully!")


def setup_youtube(api_key):
    """Set up YouTube API credentials"""
    with app.app_context():
        cred = APICredential.query.filter_by(service_name="youtube").first()

        if cred:
            print("Updating existing YouTube credentials...")
            cred.set_credentials({"api_key": api_key})
        else:
            print("Creating new YouTube credentials...")
            cred = APICredential(service_name="youtube")
            cred.set_credentials({"api_key": api_key})
            db.session.add(cred)

        db.session.commit()
        print("[OK] YouTube credentials saved successfully!")


def setup_ubersuggest(email, password):
    """Set up Ubersuggest credentials (email + password)"""
    with app.app_context():
        cred = APICredential.query.filter_by(service_name="ubersuggest").first()

        if cred:
            print("Updating existing Ubersuggest credentials...")
            cred.set_credentials({"email": email, "password": password})
        else:
            print("Creating new Ubersuggest credentials...")
            cred = APICredential(service_name="ubersuggest")
            cred.set_credentials({"email": email, "password": password})
            db.session.add(cred)

        db.session.commit()
        print("[OK] Ubersuggest credentials saved successfully!")


def list_credentials():
    """List all configured API credentials"""
    with app.app_context():
        creds = APICredential.query.all()
        if not creds:
            print("No API credentials configured yet.")
            return

        print("\n=== Configured API Credentials ===")
        for cred in creds:
            status = "[Active]" if cred.is_active else "[Inactive]"
            print(f"  - {cred.service_name}: {status} (last updated: {cred.updated_at})")
        print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
Usage:
  python setup_credentials.py <command> [args]

Commands:
  openai <api_key>                 - Set up OpenAI API credentials
  gemini <api_key>                 - Set up Google Gemini API credentials
  youtube <api_key>                - Set up YouTube API credentials
  ubersuggest <email> <password>   - Set up Ubersuggest login credentials
  list                             - List all configured credentials

Examples:
  python setup_credentials.py openai sk-proj-abc123...
  python setup_credentials.py gemini AIza...
  python setup_credentials.py list
        """)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "openai" and len(sys.argv) == 3:
        setup_openai(sys.argv[2])
    elif command == "gemini" and len(sys.argv) == 3:
        setup_google_gemini(sys.argv[2])
    elif command == "youtube" and len(sys.argv) == 3:
        setup_youtube(sys.argv[2])
    elif command == "ubersuggest" and len(sys.argv) == 4:
        setup_ubersuggest(sys.argv[2], sys.argv[3])
    elif command == "list":
        list_credentials()
    else:
        print("Invalid command. Run without arguments for usage help.")
        sys.exit(1)
