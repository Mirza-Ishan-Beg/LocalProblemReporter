"""
Local Problem Reporter — Flask backend.

Endpoints
---------
GET    /                             → serves index.html
GET    /api/reports                  → list reports (?category=Pothole)
GET    /api/reports/<id>/photo       → serve the stored image bytes
POST   /api/reports                  → create a report (multipart/form-data)
DELETE /api/reports                  → delete ALL reports
DELETE /api/reports/<id>             → delete ONE report
POST   /api/chat                     → chat with the LLM assistant

Storage
-------
- Rows    → Postgres (Aiven).        DATABASE_URL
- Photos  → Postgres BYTEA column.
- LLM     → pluggable provider.      LLM_PROVIDER + GROQ_API_KEY
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv(".env.local")
import requests
from flask import (
    Flask, jsonify, render_template, request, Response
)

from db import init_db, get_db, close_db
from llm import get_provider

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
VALID_CATEGORIES = {
    "Pothole", "Garbage", "Streetlight",
    "Drainage", "Pollution", "Other",
}

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_PHOTO_BYTES   = 2 * 1024 * 1024

MAX_NAME        = 80
MAX_LOCATION    = 500      # full Nominatim addresses can be long
MAX_DESCRIPTION = 500

MAX_CHAT_MESSAGES    = 20
MAX_CHAT_CHARS       = 2000
CONTEXT_REPORT_LIMIT = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES

# Bootstrap schema once at startup
init_db(app)

# Register teardown
app.teardown_appcontext(close_db)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_coordinate(raw: str, *, minimum: float, maximum: float):
    """Return (value, error_message). value is None if raw is empty."""
    if not raw:
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "not a number"
    if not (minimum <= value <= maximum):
        return None, f"must be between {minimum} and {maximum}"
    return value, None


def shape_report(r) -> dict:
    """Uniform JSON shape for a report row (dict_row)."""
    return {
        "id":          r["id"],
        "name":        r["name"],
        "category":    r["category"],
        "location":    r["location"],
        "latitude":    float(r["latitude"])  if r["latitude"]  is not None else None,
        "longitude":   float(r["longitude"]) if r["longitude"] is not None else None,
        "description": r["description"],
        "photo":       f"/api/reports/{r['id']}/photo" if r["has_photo"] else "",
        "date":        r["created_at"].isoformat() if r["created_at"] else "",
    }


def build_system_prompt() -> str:
    """Inject a short summary of recent reports so the bot has context."""
    with get_db().cursor() as cur:
        cur.execute(
            "SELECT category, location, description "
            "FROM reports ORDER BY id DESC LIMIT %s",
            (CONTEXT_REPORT_LIMIT,),
        )
        rows = cur.fetchall()

    if not rows:
        context = "No reports have been submitted yet."
    else:
        lines = [
            f"- [{r['category']}] {r['location']}: {r['description'][:120]}"
            for r in rows
        ]
        context = "Recent community reports:\n" + "\n".join(lines)

    return (
        "You are the Local Problem Reporter assistant — a concise, "
        "helpful bot for a neighborhood issue-reporting site. "
        "Users submit potholes, garbage, streetlight, drainage, and "
        "pollution reports. Help them understand the site, find "
        "reports, and think about what to submit.\n\n"
        f"{context}\n\n"
        "Keep answers short (2–4 sentences) unless asked for detail."
    )


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------- #
# API — read
# --------------------------------------------------------------------------- #
@app.get("/api/reports")
def list_reports():
    category = request.args.get("category", "All")
    if category and category != "All" and category not in VALID_CATEGORIES:
        return jsonify({"errors": ["Unknown category."]}), 400

    with get_db().cursor() as cur:
        if category and category != "All":
            cur.execute(
                "SELECT id, name, category, location, latitude, longitude, "
                "description, (photo IS NOT NULL) AS has_photo, created_at "
                "FROM reports WHERE category = %s ORDER BY id DESC",
                (category,),
            )
        else:
            cur.execute(
                "SELECT id, name, category, location, latitude, longitude, "
                "description, (photo IS NOT NULL) AS has_photo, created_at "
                "FROM reports ORDER BY id DESC"
            )
        rows = cur.fetchall()

    return jsonify([shape_report(r) for r in rows])


@app.get("/api/reports/<int:report_id>/photo")
def get_report_photo(report_id):
    with get_db().cursor() as cur:
        cur.execute(
            "SELECT photo, photo_type FROM reports WHERE id = %s",
            (report_id,),
        )
        row = cur.fetchone()

    if row is None or not row["photo"]:
        return jsonify({"errors": ["No photo found."]}), 404

    return Response(
        bytes(row["photo"]),
        mimetype=row["photo_type"] or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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

    latitude_raw  = (request.form.get("latitude")  or "").strip()
    longitude_raw = (request.form.get("longitude") or "").strip()

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

    # Coordinates are optional, but if one is present both must be valid.
    latitude  = None
    longitude = None
    if latitude_raw or longitude_raw:
        if not (latitude_raw and longitude_raw):
            errors.append("Both latitude and longitude must be provided together.")
        else:
            latitude, err = parse_coordinate(latitude_raw, minimum=-90.0, maximum=90.0)
            if err:
                errors.append(f"Invalid latitude ({err}).")
            longitude, err = parse_coordinate(longitude_raw, minimum=-180.0, maximum=180.0)
            if err:
                errors.append(f"Invalid longitude ({err}).")

    if errors:
        return jsonify({"errors": errors}), 400

    data = photo.read()
    if not data:
        return jsonify({"errors": ["The uploaded photo is empty."]}), 400
    if len(data) > MAX_PHOTO_BYTES:
        return jsonify({"errors": ["Photo must be smaller than 2 MB."]}), 400

    content_type = photo.mimetype or "application/octet-stream"
    created_at = datetime.now(timezone.utc)

    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reports
                    (name, category, location, description,
                     latitude, longitude, photo, photo_type, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, category, location, latitude, longitude,
                          description, (photo IS NOT NULL) AS has_photo, created_at
                """,
                (name, category, location, description,
                 latitude, longitude, data, content_type, created_at),
            )
            row = cur.fetchone()
        db.commit()
    except Exception:
        app.logger.exception("DB insert failed")
        return jsonify({"errors": ["Could not save report."]}), 500

    return jsonify(shape_report(row)), 201


# --------------------------------------------------------------------------- #
# API — delete
# --------------------------------------------------------------------------- #
@app.delete("/api/reports")
def clear_reports():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM reports")
    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/reports/<int:report_id>")
def delete_report(report_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id FROM reports WHERE id = %s", (report_id,))
        row = cur.fetchone()
        if row is None:
            return jsonify({"errors": ["Report not found."]}), 404
        cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
    db.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# API — chat
# --------------------------------------------------------------------------- #
@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    incoming = payload.get("messages")

    if not isinstance(incoming, list) or not incoming:
        return jsonify({"errors": ["messages must be a non-empty list."]}), 400

    cleaned = []
    for m in incoming[-MAX_CHAT_MESSAGES:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:MAX_CHAT_CHARS]})

    if not cleaned:
        return jsonify({"errors": ["No valid messages."]}), 400

    try:
        provider = get_provider()
        system = build_system_prompt()
        reply = provider.chat([{"role": "system", "content": system}, *cleaned])
        return jsonify({"reply": reply, "provider": provider.name})
    except NotImplementedError as e:
        return jsonify({"errors": [str(e)]}), 501
    except requests.HTTPError as e:
        app.logger.exception("LLM HTTP error")
        return jsonify({"errors": [f"LLM provider error: {e}"]}), 502
    except Exception:
        app.logger.exception("Chat failed")
        return jsonify({"errors": ["Chat failed. Try again."]}), 500


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


@app.errorhandler(405)
def method_not_allowed(_e):
    if request.path.startswith("/api/"):
        return jsonify({"errors": ["Method not allowed."]}), 405
    return "Method not allowed", 405


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api/"):
        return jsonify({"errors": ["Internal server error."]}), 500
    return "Internal server error", 500


# --------------------------------------------------------------------------- #
# Local dev
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run(debug=True, port=5000)
