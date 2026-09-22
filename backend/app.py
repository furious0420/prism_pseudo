"""PRISM backend — Flask API entrypoint.

Day 1 scope: health check only. Later days bolt on:
  Day 4  -> models/rag.py       (retrieval + grounded generation)
  Day 6  -> models/detect.py    (YOLOv8 defect detection)
  Day 7  -> models/risk.py      (SAE J1979 risk scoring)
  Day 8  -> models/case_memory.py
  Day 9  -> POST /diagnose      (orchestrates all of the above)
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)

    # React dev server runs on a different port; Day 9 needs this.
    CORS(app)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "prism-backend"})

    @app.get("/health/llm")
    def health_llm():
        """Day 2 — is a local LLM backend reachable right now?
        Kept off /health so the main check stays instant."""
        from models.llm import backend_info
        info = backend_info()
        return jsonify(info), (200 if info.get("available") else 503)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        # Keep real status codes (404, 405, 413...) but answer in JSON so the
        # frontend never has to parse an HTML error page.
        return jsonify({"error": err.name, "detail": err.description}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        # Genuine crashes only — HTTPExceptions are handled above.
        app.logger.exception("unhandled error")
        return jsonify({"error": "internal_error", "detail": str(err)}), 500

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)
