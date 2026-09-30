"""PRISM backend — Flask API.

  GET  /health           liveness, instant
  GET  /health/llm       is a local LLM reachable (D2)
  GET  /health/pipeline  which stages are ready (D9)
  POST /diagnose         the full pipeline (D9-01)
"""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

load_dotenv()

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MAX_UPLOAD_MB = int(os.getenv("PRISM_MAX_UPLOAD_MB", "20"))


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    # Without this a huge upload is read fully into memory before anything
    # rejects it. Flask turns the overflow into a 413, which the JSON error
    # handler below renders properly.
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "prism-backend"})

    @app.get("/health/llm")
    def health_llm():
        from models.llm import backend_info
        info = backend_info()
        return jsonify(info), (200 if info.get("available") else 503)

    @app.get("/health/pipeline")
    def health_pipeline():
        from models.pipeline import pipeline_info
        info = pipeline_info()
        return jsonify(info), (200 if info.get("ready") else 503)

    @app.post("/diagnose")
    def diagnose_endpoint():
        """Accepts multipart form: optional `image` file, optional `query` text.
        At least one must be present."""
        query = (request.form.get("query") or "").strip()
        upload = request.files.get("image")

        if not query and (upload is None or not upload.filename):
            return jsonify({
                "error": "empty_request",
                "detail": "Provide a symptom description, an image, or both.",
            }), 400

        tmp_path = None
        try:
            if upload is not None and upload.filename:
                name = secure_filename(upload.filename)
                ext = Path(name).suffix.lower()
                if ext not in ALLOWED_IMAGE_EXT:
                    return jsonify({
                        "error": "unsupported_file_type",
                        "detail": f"'{ext or name}' is not an image. "
                                  f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXT))}",
                    }), 400
                fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="prism_")
                os.close(fd)
                upload.save(tmp_path)

            from models.pipeline import run_diagnosis
            result = run_diagnosis(image_path=tmp_path, query=query)
            return jsonify(result), 200
        finally:
            # Never leave uploads behind; a long demo session would accumulate them.
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    app.logger.warning("could not remove temp upload %s", tmp_path)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        # Keep real status codes (404, 405, 413...) but answer in JSON so the
        # frontend never has to parse an HTML error page.
        detail = err.description
        if err.code == 413:
            # Read the app's real limit, not the module constant — otherwise the
            # message lies whenever the config is overridden.
            limit = current_app.config.get("MAX_CONTENT_LENGTH") or 0
            human = (f"{limit / 1024 / 1024:.0f} MB" if limit >= 1024 * 1024
                     else f"{limit / 1024:.0f} KB")
            detail = f"Image is larger than the {human} limit."
        return jsonify({"error": err.name, "detail": detail}), err.code

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
