"""
Shared helper for calling Gemini, used by every AI step in this app
(categorization, variance explanations, and later the analyst).
Centralizing this means the retry/backoff logic and model choice live
in exactly one place instead of being copy-pasted everywhere.
"""
import os
import time

from google import genai

DEFAULT_MODEL = "gemini-3.1-flash-lite"


def call_gemini(prompt: str, model: str = DEFAULT_MODEL, max_attempts: int = 4) -> str:
    """Calls Gemini with the given prompt, retrying with exponential
    backoff on transient errors (e.g. 503 UNAVAILABLE under high demand).
    Returns the raw text response."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            return response.text.strip()
        except Exception as e:
            last_error = e
            if attempt == max_attempts:
                raise
            wait = 2 ** attempt
            print(f"Gemini call failed (attempt {attempt}/{max_attempts}): {e}. Retrying in {wait}s...")
            time.sleep(wait)

    raise last_error
