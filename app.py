"""
Local Problem Reporter — Flask backend.

Endpoints
---------
GET    /                     → serves index.html
GET    /uploads/<filename>   → serves an uploaded photo
GET    /api/reports          → list reports (?category=Pothole)
POST   /api/reports          → create a report (multipart/form-data)
DELETE /api/reports          → delete ALL reports
DELETE /api/reports/<id>     → delete ONE report
POST   /api/stt-proxy        → proxy audio to Sarvam Speech-to-Text
POST   /api/doc/submit       → proxy digitise job submission
GET    /api/doc/status/<id>  → proxy job status poll
GET    /api/doc/download/<id>→ proxy signed download
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

import requests

from flask import (
    Flask, g, jsonify, render_template, request,
    send_from_directory, Response,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "reports.db")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
VALID_CATEGORIES = {
    "Pothole", "Garbage", "Streetlight",
    "Drainage", "Pollution", "Other",
}

MAX_REQUEST_BYTES = 8 * 1024 * 1024   # whole multipart request
MAX_PHOTO_BYTES   = 2 * 1024 * 1024   # per photo (matches frontend check)

MAX_NAME        = 80
MAX_LOCATION    = 200
MAX_DESCRIPTION = 500

# Sarvam
SARVAM_API_KEY  = os.environ.get("SARVAM_API_KEY", "").strip()
SARVAM_STT_URL  = "https://api.sarvam.ai/speech-to-text"
SARVAM_DOC_BASE = "https://api.sarvam.ai/doc-ai/v1"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

os.makedirs(UPLOAD_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                location    TEXT    NOT NULL,
                description TEXT    NOT NULL,
                photo       TEXT,
                created_at  TEXT    NOT NULL
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_category "
            "ON reports(category)"
        )
        db.commit()


init_db()


def row_to_dict(row):
    return {
        "id":          row["id"],
        "name":        row["name"],
        "category":    row["category"],
        "location":    row["location"],
        "description": row["description"],
        "photo":       f"/uploads/{row['photo']}" if row["photo"] else "",
        "date":        row["created_at"],
    }


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# --------------------------------------------------------------------------- #
# Pages & static files
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# --------------------------------------------------------------------------- #
# API — read
# --------------------------------------------------------------------------- #
@app.get("/api/reports")
def list_reports():
    category = request.args.get("category", "All")

    db = get_db()
    if category and category != "All":
        if category not in VALID_CATEGORIES:
            return jsonify({"errors": ["Unknown category."]}), 400
        rows = db.execute(
            "SELECT * FROM reports WHERE category = ? ORDER BY id DESC",
            (category,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM reports ORDER BY id DESC"
        ).fetchall()

    return jsonify([row_to_dict(r) for r in rows])


# --------------------------------------------------------------------------- #
# API — create
# --------------------------------------------------------------------------- #
@app.post("/api/reports")
def create_report():
    name        = (request.form.get("name") or "").strip()
    category    = (request.form.get("category") or "").strip()
    location    = (request.form.get("location") or "").strip()
    description = (request.form.get("description") or "").strip()
    photo       = request.files.get("photo")

    errors = []
    if not name or len(name) > MAX_NAME:
        errors.append(f"Name is required (max {MAX_NAME} characters).")
    if category not in VALID_CATEGORIES:
        errors.append("Please choose a valid problem type.")
    if not location or len(location) > MAX_LOCATION:
        errors.append(f"Location is required (max {MAX_LOCATION} characters).")
    if not description or len(description) > MAX_DESCRIPTION:
        errors.append(f"Description is required (max {MAX_DESCRIPTION} characters).")
    if photo is None or photo.filename == "":
        errors.append("A photo is required.")
    elif not allowed_file(photo.filename):
        errors.append("Unsupported image type (png, jpg, jpeg, gif, webp).")

    if errors:
        return jsonify({"errors": errors}), 400

    photo.stream.seek(0, os.SEEK_END)
    size = photo.stream.tell()
    photo.stream.seek(0)
    if size > MAX_PHOTO_BYTES:
        return jsonify({"errors": ["Photo must be smaller than 2 MB."]}), 400
    if size == 0:
        return jsonify({"errors": ["The uploaded photo is empty."]}), 400

    ext = photo.filename.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    photo.save(os.path.join(UPLOAD_DIR, stored_name))

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    db = get_db()
    cur = db.execute(
        """
        INSERT INTO reports (name, category, location, description, photo, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, category, location, description, stored_name, created_at),
    )
    db.commit()

    row = db.execute(
        "SELECT * FROM reports WHERE id = ?", (cur.lastrowid,)
    ).fetchone()

    return jsonify(row_to_dict(row)), 201


# --------------------------------------------------------------------------- #
# API — delete
# --------------------------------------------------------------------------- #
def _delete_photo(filename):
    if not filename:
        return
    path = os.path.join(UPLOAD_DIR, filename)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


@app.delete("/api/reports")
def clear_reports():
    db = get_db()
    rows = db.execute(
        "SELECT photo FROM reports WHERE photo IS NOT NULL"
    ).fetchall()
    for r in rows:
        _delete_photo(r["photo"])

    db.execute("DELETE FROM reports")
    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/reports/<int:report_id>")
def delete_report(report_id):
    db = get_db()
    row = db.execute(
        "SELECT photo FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    if row is None:
        return jsonify({"errors": ["Report not found."]}), 404

    _delete_photo(row["photo"])
    db.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# API — Sarvam Speech-to-Text proxy
# --------------------------------------------------------------------------- #
@app.post("/api/stt-proxy")
def stt_proxy():
    if not SARVAM_API_KEY:
        return jsonify({"errors": ["SARVAM_API_KEY not configured on server."]}), 500

    audio = request.files.get("file")
    if not audio:
        return jsonify({"errors": ["No audio file received."]}), 400

    language = request.form.get("language_code", "en-IN")
    model    = request.form.get("model", "saarika:v2")

    files = {
        "file": (
            audio.filename or "speech.webm",
            audio.stream,
            audio.mimetype or "audio/webm",
        )
    }
    data = {
        "model": model,
        "language_code": language,
    }
    headers = {"api-subscription-key": SARVAM_API_KEY}

    try:
        r = requests.post(
            SARVAM_STT_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=60,
        )
    except requests.Timeout:
        return jsonify({"errors": ["Sarvam STT timed out."]}), 504
    except requests.RequestException as e:
        return jsonify({"errors": [f"Sarvam request failed: {str(e)}"]}), 502

    return Response(
        r.content,
        status=r.status_code,
        content_type=r.headers.get("Content-Type", "application/json"),
    )


# --------------------------------------------------------------------------- #
# API — Sarvam Doc-AI proxy (submit / status / download)
# --------------------------------------------------------------------------- #
@app.post("/api/doc/submit")
def doc_submit():
    if not SARVAM_API_KEY:
        return jsonify({"errors": ["SARVAM_API_KEY not configured."]}), 500

    doc = request.files.get("file")
    if not doc or not doc.filename:
        return jsonify({"errors": ["No document file received."]}), 400

    files = {
        "file": (
            doc.filename,
            doc.stream,
            doc.mimetype or "application/octet-stream",
        )
    }
    data = {
        "language":      request.form.get("language", "en-IN"),
        "output_format": request.form.get("output_format", "html"),
        "content_type":  request.form.get("content_type", "printed"),
        "auto_orient":   request.form.get("auto_orient", "true"),
    }
    headers = {"api-subscription-key": SARVAM_API_KEY}

    try:
        r = requests.post(
            f"{SARVAM_DOC_BASE}/job/digitise",
            headers=headers, files=files, data=data, timeout=180,
        )
    except requests.Timeout:
        return jsonify({"errors": ["Sarvam submit timed out."]}), 504
    except requests.RequestException as e:
        return jsonify({"errors": [f"Sarvam submit failed: {e}"]}), 502

    return Response(
        r.content,
        status=r.status_code,
        content_type=r.headers.get("Content-Type", "application/json"),
    )


@app.get("/api/doc/status/<job_id>")
def doc_status(job_id):
    if not SARVAM_API_KEY:
        return jsonify({"errors": ["SARVAM_API_KEY not configured."]}), 500

    headers = {"api-subscription-key": SARVAM_API_KEY}

    try:
        r = requests.get(
            f"{SARVAM_DOC_BASE}/job/{job_id}/status",
            headers=headers, timeout=30,
        )
    except requests.Timeout:
        return jsonify({"errors": ["Sarvam status timed out."]}), 504
    except requests.RequestException as e:
        return jsonify({"errors": [f"Sarvam status failed: {e}"]}), 502

    return Response(
        r.content,
        status=r.status_code,
        content_type=r.headers.get("Content-Type", "application/json"),
    )


@app.get("/api/doc/download/<job_id>")
def doc_download(job_id):
    if not SARVAM_API_KEY:
        return jsonify({"errors": ["SARVAM_API_KEY not configured."]}), 500

    headers = {"api-subscription-key": SARVAM_API_KEY}

    # Step 1 — get signed URL from Sarvam
    try:
        link_res = requests.get(
            f"{SARVAM_DOC_BASE}/job/{job_id}/download-url",
            headers=headers, timeout=30,
        )
    except requests.Timeout:
        return jsonify({"errors": ["Download-url request timed out."]}), 504
    except requests.RequestException as e:
        return jsonify({"errors": [f"Download-url request failed: {e}"]}), 502

    if not link_res.ok:
        return Response(
            link_res.content,
            status=link_res.status_code,
            content_type="application/json",
        )

    link = link_res.json()
    url       = link.get("url")
    dl_headers = link.get("headers") or {}

    if not url:
        return jsonify({"errors": ["Sarvam did not return a download URL."]}), 502

    # Step 2 — fetch the actual content through the proxy (no CORS for browser)
    try:
        out = requests.get(url, headers=dl_headers, timeout=180)
    except requests.Timeout:
        return jsonify({"errors": ["Content download timed out."]}), 504
    except requests.RequestException as e:
        return jsonify({"errors": [f"Content download failed: {e}"]}), 502

    content_type = out.headers.get("Content-Type", "application/octet-stream")
    return Response(out.content, status=out.status_code, content_type=content_type)


# --------------------------------------------------------------------------- #
# Error handlers
# --------------------------------------------------------------------------- #
@app.errorhandler(413)
def request_too_large(_e):
    return jsonify({"errors": ["Upload too large (max 8 MB)."]}), 413


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify({"errors": ["Not found."]}), 404
    return render_template("index.html"), 404


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api/"):
        return jsonify({"errors": ["Internal server error."]}), 500
    return "Internal server error", 500


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run(debug=True, port=5000)