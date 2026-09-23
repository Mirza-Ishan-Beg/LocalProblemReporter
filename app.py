"""
Local Problem Reporter — Flask backend for Render.
"""

import os
from datetime import datetime, timezone

from flask import (
    Flask, jsonify, render_template, request, Response
)

from db import init_db, get_db, close_db

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
MAX_LOCATION    = 200
MAX_DESCRIPTION = 500

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
                "SELECT id, name, category, location, description, "
                "(photo IS NOT NULL) AS has_photo, created_at "
                "FROM reports WHERE category = %s ORDER BY id DESC",
                (category,),
            )
        else:
            cur.execute(
                "SELECT id, name, category, location, description, "
                "(photo IS NOT NULL) AS has_photo, created_at "
                "FROM reports ORDER BY id DESC"
            )
        rows = cur.fetchall()

    def shape(r):
        return {
            "id":          r["id"],
            "name":        r["name"],
            "category":    r["category"],
            "location":    r["location"],
            "description": r["description"],
            "photo":       f"/api/reports/{r['id']}/photo" if r["has_photo"] else "",
            "date":        r["created_at"].isoformat() if r["created_at"] else "",
        }

    return jsonify([shape(r) for r in rows])


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
                     photo, photo_type, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, category, location, description,
                          (photo IS NOT NULL) AS has_photo, created_at
                """,
                (name, category, location, description,
                 data, content_type, created_at),
            )
            row = cur.fetchone()
        db.commit()
    except Exception:
        app.logger.exception("DB insert failed")
        return jsonify({"errors": ["Could not save report."]}), 500

    return jsonify({
        "id":          row["id"],
        "name":        row["name"],
        "category":    row["category"],
        "location":    row["location"],
        "description": row["description"],
        "photo":       f"/api/reports/{row['id']}/photo" if row["has_photo"] else "",
        "date":        row["created_at"].isoformat() if row["created_at"] else "",
    }), 201


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
# Local dev
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    app.run(debug=True, port=5000)
