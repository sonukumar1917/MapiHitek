import os
import re
import time
from flask import Flask, request, jsonify
import requests
from functools import wraps

# ============================================================
#  CONFIGURATION (from environment variables)
# ============================================================
API_TOKEN = os.environ.get("8406324025:keIgs5YX")
if not API_TOKEN:
    raise RuntimeError("API_TOKEN environment variable is not set")

SEARCH_LIMIT = int(os.environ.get("SEARCH_LIMIT", 1000))
LANG = os.environ.get("LANG", "en")
API_URL = "https://leakosintapi.com/"

# Optional rate limiting (requests per minute per IP)
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 0))  # 0 = disabled
RATE_WINDOW = 60  # seconds

# ============================================================
#  RATE LIMITER (simple in‑memory)
# ============================================================
rate_store = {}

def rate_limit(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if RATE_LIMIT == 0:
            return f(*args, **kwargs)
        client_ip = request.remote_addr
        now = time.time()
        # Clean old entries
        for ip in list(rate_store.keys()):
            rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]
            if not rate_store[ip]:
                del rate_store[ip]
        if client_ip not in rate_store:
            rate_store[client_ip] = []
        if len(rate_store[client_ip]) >= RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
        rate_store[client_ip].append(now)
        return f(*args, **kwargs)
    return decorated

# ============================================================
#  FLASK APP
# ============================================================
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/search", methods=["GET"])
@rate_limit
def search():
    """
    Query the LeakOSINT API.
    Query parameters:
        q           (required) – email, phone, username, etc.
        limit       (optional) – override SEARCH_LIMIT
        lang        (optional) – override LANG
    Returns the raw JSON response from LeakOSINT.
    """
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    # Normalise phone numbers (optional – you can keep or remove)
    if re.fullmatch(r"\d{10}", query):
        query = "+91" + query
    elif re.fullmatch(r"91\d{10}", query):
        query = "+" + query

    # Override limits from query string
    limit = request.args.get("limit", SEARCH_LIMIT)
    lang = request.args.get("lang", LANG)

    payload = {
        "token": API_TOKEN,
        "request": query,
        "limit": int(limit),
        "lang": lang,
        "type": "json"
    }

    try:
        resp = requests.post(API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        # Return the exact JSON from the upstream API
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to LeakOSINT timed out"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"LeakOSINT API error: {str(e)}"}), 502

# ============================================================
#  RUN (for local development)
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)