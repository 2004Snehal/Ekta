"""Quick Gemini connectivity check using GOOGLE_API_KEY from .env."""

import os
import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    try:
        import google.genai as genai  # type: ignore
    except ImportError as e:
        sys.exit(f"google-genai not installed: {e}")

    key = os.getenv("GOOGLE_API_KEY")
    print("API key present:", bool(key))
    if not key:
        sys.exit("Missing GOOGLE_API_KEY")

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say hello, Gemini!",
    )
    print("Response:", resp.text)


if __name__ == "__main__":
    main()