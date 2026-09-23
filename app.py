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
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import (
    Flask, g, jsonify, render_template, request, send_from_directory
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

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

os.makedirs(UPLOAD_DIR, exist_ok=True)


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def get_db():
    """One SQLite connection per request, stored on Flask's `g`."""
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
        db.execute("PRAGMA journal_mode = WAL")   # better concurrent reads
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                location    TEXT    NOT NULL,
                description TEXT    NOT NULL,
                photo       TEXT,                 -- stored filename or NULL
                created_at  TEXT    NOT NULL      -- ISO-8601 UTC
            )
            """
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_category "
            "ON reports(category)"
        )
        db.commit()


init_db()   # runs on import, so it also works under gunicorn


def row_to_dict(row):
    """Shape a DB row exactly like the old localStorage objects."""
    return {
        "id":          row["id"],
        "name":        row["name"],
        "category":    row["category"],
        "location":    row["location"],
        "description": row["description"],
        "photo":       f"/uploads/{row['photo']}" if row["photo"] else "",
        "date":        row["created_at"],          # ISO string; JS formats it
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
    # send_from_directory blocks path traversal
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

    # Per-file size check (MAX_CONTENT_LENGTH only caps the whole request)
    photo.stream.seek(0, os.SEEK_END)
    size = photo.stream.tell()
    photo.stream.seek(0)
    if size > MAX_PHOTO_BYTES:
        return jsonify({"errors": ["Photo must be smaller than 2 MB."]}), 400
    if size == 0:
        return jsonify({"errors": ["The uploaded photo is empty."]}), 400

    # Save with a random name — never trust the client's filename
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
