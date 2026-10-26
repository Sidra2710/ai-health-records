
import os
import re
import math
import sqlite3
from datetime import datetime, date

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "change-this-local-dev-key"
)

DB_PATH = os.environ.get("DATABASE_PATH", "patients.db")

# Keep API keys in environment variables, never in source code.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.0-flash"
).strip()


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                dob TEXT NOT NULL,
                email TEXT NOT NULL,
                glucose REAL NOT NULL,
                haemoglobin REAL NOT NULL,
                cholesterol REAL NOT NULL,
                remarks TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


# --------------------------------------------------
# FORM VALIDATION
# --------------------------------------------------

def validate_form(form):
    errors = []

    full_name = form.get("full_name", "").strip()
    dob_raw = form.get("dob", "").strip()
    email = form.get("email", "").strip()

    values = {}

    if not full_name:
        errors.append("Full name is required.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        errors.append(
            "Enter a valid email address, for example name@example.com."
        )

    try:
        dob = datetime.strptime(dob_raw, "%d/%m/%Y").date()

        if dob.strftime("%d/%m/%Y") != dob_raw:
            raise ValueError

        if dob > date.today():
            errors.append("Date of birth cannot be in the future.")

        values["dob"] = dob.strftime("%Y-%m-%d")

    except ValueError:
        errors.append(
            "Date of birth must be a real date in dd/mm/yyyy format."
        )

    for field, label in [
        ("glucose", "Glucose"),
        ("haemoglobin", "Haemoglobin"),
        ("cholesterol", "Cholesterol"),
    ]:
        raw = form.get(field, "").strip()

        try:
            number = float(raw)

            if not math.isfinite(number):
                errors.append(f"{label} must be a finite numeric value.")
            elif number < 0:
                errors.append(f"{label} must be zero or greater.")
            else:
                values[field] = number

        except (ValueError, TypeError):
            errors.append(f"{label} must be a numeric value.")

    values.update({
        "full_name": full_name,
        "email": email,
    })

    return errors, values


# --------------------------------------------------
# GEMINI AI INTEGRATION
# --------------------------------------------------

def generate_ai_remarks(patient):
    """Generate informational remarks using Gemini."""

    if not GEMINI_API_KEY:
        return (
            "AI is not configured. Set the GEMINI_API_KEY environment "
            "variable to enable AI remarks."
        )

    prompt = (
        "Write a brief, neutral summary for a health-record demonstration. "
        "Do not diagnose disease or claim that results are normal or abnormal "
        "without units, laboratory reference ranges, and clinical context. "
        "Explain that a qualified clinician should interpret the results. "
        f"Glucose: {patient['glucose']}; "
        f"Haemoglobin: {patient['haemoglobin']}; "
        f"Cholesterol: {patient['cholesterol']}."
    )

    # This must be a plain URL, not a Markdown hyperlink.
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    try:
        response = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            },
            timeout=45,
        )

        if response.status_code >= 400:
            try:
                message = response.json().get(
                    "error", {}
                ).get("message", "No details provided.")
            except ValueError:
                message = "Could not read the API error response."

            if response.status_code == 429:
                return (
                    "Gemini quota or rate limit reached. Try again later. "
                    f"Details: {message}"
                )

            if response.status_code == 503:
                return (
                    "Gemini is temporarily unavailable. Try again later. "
                    f"Details: {message}"
                )

            return (
                f"Gemini API error (HTTP {response.status_code}): {message}"
            )

        data = response.json()
        candidates = data.get("candidates", [])

        if not candidates:
            return "Gemini returned no answer. Please try again later."

        parts = candidates[0].get("content", {}).get("parts", [])

        answer = " ".join(
            part.get("text", "").strip()
            for part in parts
            if part.get("text")
        ).strip()

        if not answer:
            return "Gemini returned an empty answer. Please try again."

        return (
            answer
            + "\n\nInformational only; not a diagnosis. "
            "Consult a qualified clinician."
        )

    except requests.Timeout:
        return "Gemini request timed out. Please retry later."

    except requests.ConnectionError:
        return "Could not connect to Gemini. Check your internet connection."

    except requests.RequestException as exc:
        return f"Gemini request failed: {str(exc)[:250]}"

    except (KeyError, IndexError, TypeError, ValueError):
        return "Gemini returned an unexpected response. Please try again."


# --------------------------------------------------
# HOME PAGE AND PATIENT SEARCH
# --------------------------------------------------

@app.route("/")
def index():
    search_query = request.args.get("q", "").strip()

    with get_db() as conn:
        if search_query:
            pattern = f"%{search_query}%"

            patients = conn.execute(
                """
                SELECT * FROM patients
                WHERE full_name LIKE ? OR email LIKE ?
                ORDER BY id
                """,
                (pattern, pattern),
            ).fetchall()
        else:
            patients = conn.execute(
                "SELECT * FROM patients ORDER BY id"
            ).fetchall()

        total_records = conn.execute(
            "SELECT COUNT(*) FROM patients"
        ).fetchone()[0]

    return render_template(
        "index.html",
        patients=patients,
        search_query=search_query,
        total_records=total_records,
        ai_configured=bool(GEMINI_API_KEY),
    )


# --------------------------------------------------
# CREATE PATIENT
# --------------------------------------------------

@app.route("/patients/new", methods=["GET", "POST"])
def create_patient():
    if request.method == "POST":
        errors, values = validate_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")

            return render_template(
                "form.html",
                patient=request.form,
                mode="Create",
            )

        values["remarks"] = generate_ai_remarks(values)

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO patients (
                    full_name, dob, email, glucose,
                    haemoglobin, cholesterol, remarks
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["full_name"],
                    values["dob"],
                    values["email"],
                    values["glucose"],
                    values["haemoglobin"],
                    values["cholesterol"],
                    values["remarks"],
                ),
            )

        flash("Patient record created.", "success")
        return redirect(url_for("index"))

    return render_template(
        "form.html",
        patient={},
        mode="Create",
    )


# --------------------------------------------------
# EDIT PATIENT
# --------------------------------------------------

@app.route(
    "/patients/<int:patient_id>/edit",
    methods=["GET", "POST"],
)
def edit_patient(patient_id):
    with get_db() as conn:
        patient = conn.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

    if patient is None:
        flash("Record not found.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        errors, values = validate_form(request.form)

        if errors:
            for error in errors:
                flash(error, "error")

            return render_template(
                "form.html",
                patient=request.form,
                mode="Edit",
                patient_id=patient_id,
            )

        # Keep existing remarks unless the user requests a refresh.
        remarks = patient["remarks"]

        if request.form.get("refresh_ai") == "yes":
            remarks = generate_ai_remarks(values)

        with get_db() as conn:
            conn.execute(
                """
                UPDATE patients
                SET full_name = ?,
                    dob = ?,
                    email = ?,
                    glucose = ?,
                    haemoglobin = ?,
                    cholesterol = ?,
                    remarks = ?
                WHERE id = ?
                """,
                (
                    values["full_name"],
                    values["dob"],
                    values["email"],
                    values["glucose"],
                    values["haemoglobin"],
                    values["cholesterol"],
                    remarks,
                    patient_id,
                ),
            )

        flash("Patient record updated.", "success")
        return redirect(url_for("index"))

    display_patient = dict(patient)
    display_patient["dob"] = datetime.strptime(
        patient["dob"], "%Y-%m-%d"
    ).strftime("%d/%m/%Y")

    return render_template(
        "form.html",
        patient=display_patient,
        mode="Edit",
        patient_id=patient_id,
    )


# --------------------------------------------------
# DELETE PATIENT
# --------------------------------------------------

@app.route(
    "/patients/<int:patient_id>/delete",
    methods=["POST"],
)
def delete_patient(patient_id):
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM patients WHERE id = ?",
            (patient_id,),
        )

    if result.rowcount:
        flash("Patient record deleted.", "success")
    else:
        flash("Record not found.", "error")

    return redirect(url_for("index"))


# --------------------------------------------------
# REFRESH AI REMARKS
# --------------------------------------------------

@app.route(
    "/patients/<int:patient_id>/refresh-ai",
    methods=["POST"],
)
def refresh_ai(patient_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()

        if row is None:
            flash("Record not found.", "error")
            return redirect(url_for("index"))

        remarks = generate_ai_remarks(dict(row))

        conn.execute(
            "UPDATE patients SET remarks = ? WHERE id = ?",
            (remarks, patient_id),
        )

    if (
        remarks.startswith("Gemini API error")
        or "quota or rate limit" in remarks
        or "temporarily unavailable" in remarks
        or "timed out" in remarks
        or "Could not connect" in remarks
        or "not configured" in remarks
        or "request failed" in remarks
        or "unexpected response" in remarks
        or "returned no answer" in remarks
        or "returned an empty answer" in remarks
    ):
        flash(remarks, "error")
    else:
        flash("AI remarks refreshed.", "success")

    return redirect(url_for("index"))


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/health")
def health():
    return {
        "status": "ok",
        "ai_configured": bool(GEMINI_API_KEY),
    }


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
