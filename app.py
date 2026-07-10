from __future__ import annotations

from io import BytesIO
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, make_response, redirect, render_template, request, session, url_for
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "healthcare.db"

app = Flask(__name__, template_folder="app/templates", static_folder="app/static")
app.config["SECRET_KEY"] = "smart-healthcare-demo-secret"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_: object | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)
    migrate_users_table(db)

    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count == 0:
        seed_demo_data(db)
    ensure_additional_doctors(db)

    db.commit()
    db.close()


def migrate_users_table(db: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    if "email" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN email TEXT")

    db.execute(
        """
        UPDATE users
        SET email = (
            SELECT patients.email FROM patients WHERE patients.patient_id = users.patient_id
        )
        WHERE email IS NULL AND patient_id IS NOT NULL
        """
    )
    db.execute(
        """
        UPDATE users
        SET email = (
            SELECT doctors.email FROM doctors WHERE doctors.doctor_id = users.doctor_id
        )
        WHERE email IS NULL AND doctor_id IS NOT NULL
        """
    )
    db.execute(
        """
        UPDATE users
        SET email = CASE
            WHEN role = 'admin' THEN 'admin@smarthealth.local'
            WHEN role = 'receptionist' THEN 'reception@smarthealth.local'
            ELSE lower(username) || '@smarthealth.local'
        END
        WHERE email IS NULL
        """
    )
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def seed_demo_data(db: sqlite3.Connection) -> None:
    patients = [
        ("Aarav Mehta", "1995-02-14", "Male", "aarav@example.com", "9876543210", "New Delhi", "B+", "Peanut Allergy"),
        ("Sara Khan", "1990-11-03", "Female", "sara@example.com", "9988776655", "Mumbai", "O+", "Asthma"),
    ]
    doctors = [
        ("Dr. Priya Sharma", "Cardiology", "priya.sharma@example.com", "9000000001", 12, 650.0),
        ("Dr. Rohan Verma", "Dermatology", "rohan.verma@example.com", "9000000002", 8, 500.0),
    ]
    db.executemany(
        """
        INSERT INTO patients (full_name, date_of_birth, gender, email, phone, address, blood_group, allergies)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patients,
    )
    db.executemany(
        """
        INSERT INTO doctors (full_name, specialization, email, phone, years_of_experience, consultation_fee)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        doctors,
    )

    availability = [
        (1, "Monday", "09:00", "13:00", "Online"),
        (1, "Wednesday", "10:00", "14:00", "Offline"),
        (2, "Tuesday", "11:00", "16:00", "Online"),
        (2, "Thursday", "09:00", "12:00", "Offline"),
    ]
    db.executemany(
        """
        INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, consultation_mode)
        VALUES (?, ?, ?, ?, ?)
        """,
        availability,
    )

    appointments = [
        (1, 1, "2026-04-12", "10:30", "Online", "Scheduled", "Routine heart check-up"),
        (2, 2, "2026-04-13", "11:30", "Offline", "Completed", "Skin allergy consultation"),
    ]
    db.executemany(
        """
        INSERT INTO appointments
        (patient_id, doctor_id, appointment_date, appointment_time, consultation_type, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        appointments,
    )
    db.execute(
        """
        INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, treatment_notes, vitals, record_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            2,
            2,
            2,
            "Seasonal dermatitis",
            "Topical steroid prescribed. Follow-up in 2 weeks if symptoms persist.",
            "BP 118/76, Temp 98.2 F",
            "2026-04-13",
        ),
    )
    db.execute(
        """
        INSERT INTO prescriptions (appointment_id, patient_id, doctor_id, medicines, instructions, issued_on)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            2,
            2,
            2,
            "Cetirizine 10mg, Hydrocortisone cream",
            "Take cetirizine after dinner and apply cream twice daily for 7 days.",
            "2026-04-13",
        ),
    )
    db.execute(
        """
        INSERT INTO payments (appointment_id, patient_id, amount, payment_method, payment_status, paid_on)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (2, 2, 500.0, "UPI", "Paid", "2026-04-13 12:10:00"),
    )

    users = [
        ("admin", "admin@smarthealth.local", "admin123", "admin", None, None),
        ("reception", "reception@smarthealth.local", "reception123", "receptionist", None, None),
        ("aarav", "aarav@example.com", "patient123", "patient", 1, None),
        ("sara", "sara@example.com", "patient123", "patient", 2, None),
        ("drpriya", "priya.sharma@example.com", "doctor123", "doctor", None, 1),
        ("drrohan", "rohan.verma@example.com", "doctor123", "doctor", None, 2),
    ]
    db.executemany(
        """
        INSERT INTO users (username, email, password_hash, role, patient_id, doctor_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (u, email, generate_password_hash(p), r, patient_id, doctor_id)
            for u, email, p, r, patient_id, doctor_id in users
        ],
    )


def ensure_additional_doctors(db: sqlite3.Connection) -> None:
    extra_doctors = [
        ("Dr. Ananya Iyer", "Neurology", "ananya.iyer@example.com", "9000000003", 10, 900.0),
        ("Dr. Vivek Nair", "Orthopedics", "vivek.nair@example.com", "9000000004", 11, 750.0),
        ("Dr. Meera Joshi", "Pediatrics", "meera.joshi@example.com", "9000000005", 9, 600.0),
        ("Dr. Karan Malhotra", "Psychiatry", "karan.malhotra@example.com", "9000000006", 13, 850.0),
        ("Dr. Neha Kapoor", "Gynecology", "neha.kapoor@example.com", "9000000007", 12, 700.0),
        ("Dr. Sanjay Rao", "ENT", "sanjay.rao@example.com", "9000000008", 7, 550.0),
        ("Dr. Ishita Sen", "Ophthalmology", "ishita.sen@example.com", "9000000009", 8, 620.0),
        ("Dr. Arjun Pillai", "General Medicine", "arjun.pillai@example.com", "9000000010", 14, 500.0),
    ]
    availability_by_email = {
        "ananya.iyer@example.com": [("Monday", "14:00", "18:00", "Online"), ("Friday", "10:00", "13:00", "Offline")],
        "vivek.nair@example.com": [("Tuesday", "09:00", "13:00", "Offline"), ("Saturday", "11:00", "14:00", "Online")],
        "meera.joshi@example.com": [("Monday", "09:00", "12:00", "Offline"), ("Thursday", "15:00", "18:00", "Online")],
        "karan.malhotra@example.com": [("Wednesday", "12:00", "16:00", "Online"), ("Friday", "16:00", "19:00", "Online")],
        "neha.kapoor@example.com": [("Tuesday", "10:00", "14:00", "Offline"), ("Saturday", "09:00", "12:00", "Offline")],
        "sanjay.rao@example.com": [("Wednesday", "09:00", "12:00", "Offline"), ("Friday", "13:00", "17:00", "Online")],
        "ishita.sen@example.com": [("Thursday", "09:00", "13:00", "Offline"), ("Sunday", "10:00", "12:00", "Online")],
        "arjun.pillai@example.com": [("Monday", "17:00", "20:00", "Online"), ("Thursday", "09:00", "12:00", "Offline")],
    }

    for full_name, specialization, email, phone, years, fee in extra_doctors:
        doctor = db.execute("SELECT doctor_id FROM doctors WHERE email = ?", (email,)).fetchone()
        if doctor is None:
            db.execute(
                """
                INSERT INTO doctors (full_name, specialization, email, phone, years_of_experience, consultation_fee)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (full_name, specialization, email, phone, years, fee),
            )
            doctor_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            username = slugify_username(email, db)
            db.execute(
                """
                INSERT INTO users (username, email, password_hash, role, patient_id, doctor_id)
                VALUES (?, ?, ?, 'doctor', NULL, ?)
                """,
                (username, email, generate_password_hash("doctor123"), doctor_id),
            )
        else:
            doctor_id = doctor["doctor_id"]

        for day_of_week, start_time, end_time, consultation_mode in availability_by_email[email]:
            exists = db.execute(
                """
                SELECT 1 FROM doctor_availability
                WHERE doctor_id = ? AND day_of_week = ? AND start_time = ? AND end_time = ? AND consultation_mode = ?
                """,
                (doctor_id, day_of_week, start_time, end_time, consultation_mode),
            ).fetchone()
            if not exists:
                db.execute(
                    """
                    INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, consultation_mode)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doctor_id, day_of_week, start_time, end_time, consultation_mode),
                )


def slugify_username(email: str, db: sqlite3.Connection) -> str:
    base = email.split("@", 1)[0].strip().lower().replace(" ", "")
    base = "".join(ch for ch in base if ch.isalnum() or ch in {"_", "."}) or "patient"
    candidate = base
    suffix = 1
    while db.execute("SELECT 1 FROM users WHERE username = ?", (candidate,)).fetchone():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                return redirect(url_for("login"))
            if g.user["role"] not in roles:
                flash("You do not have access to that page.", "error")
                return redirect(url_for("dashboard"))
            return view(**kwargs)

        return wrapped_view

    return decorator


def can_access_patient(patient_id: int) -> bool:
    if g.user is None:
        return False
    if g.user["role"] in {"admin", "receptionist"}:
        return True
    if g.user["role"] == "patient":
        return g.user["patient_id"] == patient_id
    return bool(
        get_db().execute(
            """
            SELECT 1
            FROM appointments
            WHERE patient_id = ? AND doctor_id = ?
            LIMIT 1
            """,
            (patient_id, g.user["doctor_id"]),
        ).fetchone()
    )


def build_patient_report(db: sqlite3.Connection, patient_id: int) -> str:
    patient = db.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
    if patient is None:
        raise LookupError("Patient not found")

    appointments = db.execute(
        """
        SELECT a.*, d.full_name AS doctor_name, d.specialization
        FROM appointments a
        JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.patient_id = ?
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
        """,
        (patient_id,),
    ).fetchall()
    records = db.execute(
        """
        SELECT mr.*, d.full_name AS doctor_name
        FROM medical_records mr
        JOIN doctors d ON d.doctor_id = mr.doctor_id
        WHERE mr.patient_id = ?
        ORDER BY mr.record_date DESC
        """,
        (patient_id,),
    ).fetchall()
    prescriptions = db.execute(
        """
        SELECT pr.*, d.full_name AS doctor_name
        FROM prescriptions pr
        JOIN doctors d ON d.doctor_id = pr.doctor_id
        WHERE pr.patient_id = ?
        ORDER BY pr.issued_on DESC
        """,
        (patient_id,),
    ).fetchall()

    lines = [
        "SMART HEALTHCARE PATIENT REPORT",
        "",
        f"Patient ID: {patient['patient_id']}",
        f"Name: {patient['full_name']}",
        f"Email: {patient['email']}",
        f"Phone: {patient['phone']}",
        f"Blood Group: {patient['blood_group'] or '-'}",
        f"Allergies: {patient['allergies'] or '-'}",
        "",
        "APPOINTMENTS",
    ]
    if appointments:
        for appointment in appointments:
            lines.extend(
                [
                    f"- #{appointment['appointment_id']} | {appointment['appointment_date']} {appointment['appointment_time']} | {appointment['doctor_name']} ({appointment['specialization']})",
                    f"  Type: {appointment['consultation_type']} | Status: {appointment['status']}",
                    f"  Reason: {appointment['reason']}",
                ]
            )
    else:
        lines.append("- No appointments found")

    lines.extend(["", "MEDICAL RECORDS"])
    if records:
        for record in records:
            lines.extend(
                [
                    f"- {record['record_date']} | {record['doctor_name']}",
                    f"  Diagnosis: {record['diagnosis']}",
                    f"  Vitals: {record['vitals'] or '-'}",
                    f"  Treatment: {record['treatment_notes']}",
                ]
            )
    else:
        lines.append("- No medical records found")

    lines.extend(["", "PRESCRIPTIONS"])
    if prescriptions:
        for prescription in prescriptions:
            lines.extend(
                [
                    f"- {prescription['issued_on']} | {prescription['doctor_name']}",
                    f"  Medicines: {prescription['medicines']}",
                    f"  Instructions: {prescription['instructions']}",
                ]
            )
    else:
        lines.append("- No prescriptions found")

    return "\n".join(lines)


def build_patient_report_pdf(report_text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left_margin = 50
    top_margin = height - 50
    line_height = 16

    text = pdf.beginText(left_margin, top_margin)
    text.setFont("Helvetica", 11)

    for raw_line in report_text.splitlines():
        line = raw_line or " "
        wrapped_lines = [line[i:i + 95] for i in range(0, len(line), 95)] or [" "]
        for wrapped in wrapped_lines:
            if text.getY() <= 50:
                pdf.drawText(text)
                pdf.showPage()
                text = pdf.beginText(left_margin, top_margin)
                text.setFont("Helvetica", 11)
            text.textLine(wrapped)

    pdf.drawText(text)
    pdf.save()
    return buffer.getvalue()


@app.before_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


@app.context_processor
def inject_now() -> dict[str, str]:
    def format_appointment_status(status: str) -> str:
        if status == "Scheduled":
            return "Booked"
        return status

    def format_payment_status(status: str, booked_on: str | None = None, paid_on: str | None = None) -> str:
        if status == "Pending":
            if booked_on:
                return f"Booked on {booked_on[:10]}"
            return "Booked"
        if status == "Paid" and paid_on:
            return f"Paid on {paid_on[:10]}"
        return status

    return {
        "now": datetime.now().strftime("%Y"),
        "format_appointment_status": format_appointment_status,
        "format_payment_status": format_payment_status,
    }


@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]
        date_of_birth = request.form["date_of_birth"]
        gender = request.form["gender"]
        address = request.form["address"].strip()
        blood_group = request.form["blood_group"].strip() or None
        allergies = request.form["allergies"].strip() or None

        db = get_db()
        existing_user = db.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone()
        existing_patient = db.execute("SELECT 1 FROM patients WHERE lower(email) = ? OR phone = ?", (email, phone)).fetchone()

        if existing_user or existing_patient:
            flash("An account with this email or phone number already exists.", "error")
            return redirect(url_for("register"))

        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT INTO patients (full_name, date_of_birth, gender, email, phone, address, blood_group, allergies)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (full_name, date_of_birth, gender, email, phone, address, blood_group, allergies),
            )
            patient_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            username = slugify_username(email, db)
            db.execute(
                """
                INSERT INTO users (username, email, password_hash, role, patient_id, doctor_id)
                VALUES (?, ?, ?, 'patient', ?, NULL)
                """,
                (username, email, generate_password_hash(password), patient_id),
            )
            user_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            db.commit()
        except sqlite3.DatabaseError:
            db.rollback()
            flash("Registration failed due to a database error.", "error")
            return redirect(url_for("register"))

        session.clear()
        session["user_id"] = user_id
        flash("Registration successful. Your patient portal is ready.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    role = g.user["role"]
    counts = {
        "patients": db.execute("SELECT COUNT(*) AS count FROM patients").fetchone()["count"],
        "doctors": db.execute("SELECT COUNT(*) AS count FROM doctors").fetchone()["count"],
        "appointments": db.execute("SELECT COUNT(*) AS count FROM appointments").fetchone()["count"],
        "payments": db.execute("SELECT COUNT(*) AS count FROM payments").fetchone()["count"],
    }

    if role == "patient":
        patient_id = g.user["patient_id"]
        upcoming = db.execute(
            """
            SELECT a.*, d.full_name AS doctor_name, d.specialization
            FROM appointments a
            JOIN doctors d ON d.doctor_id = a.doctor_id
            WHERE a.patient_id = ?
            ORDER BY a.appointment_date, a.appointment_time
            """,
            (patient_id,),
        ).fetchall()
    elif role == "doctor":
        doctor_id = g.user["doctor_id"]
        upcoming = db.execute(
            """
            SELECT a.*, p.full_name AS patient_name
            FROM appointments a
            JOIN patients p ON p.patient_id = a.patient_id
            WHERE a.doctor_id = ?
            ORDER BY a.appointment_date, a.appointment_time
            """,
            (doctor_id,),
        ).fetchall()
    else:
        upcoming = db.execute(
            """
            SELECT a.*, p.full_name AS patient_name, d.full_name AS doctor_name
            FROM appointments a
            JOIN patients p ON p.patient_id = a.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
            ORDER BY a.appointment_date, a.appointment_time
            LIMIT 8
            """
        ).fetchall()

    payments_total = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE payment_status = 'Paid'"
    ).fetchone()["total"]
    return render_template("dashboard.html", counts=counts, upcoming=upcoming, payments_total=payments_total)


@app.route("/patients")
@role_required("admin", "receptionist", "doctor")
def patients():
    db = get_db()
    rows = db.execute(
        """
        SELECT p.*,
               COUNT(DISTINCT a.appointment_id) AS appointment_count,
               MAX(a.appointment_date) AS last_visit
        FROM patients p
        LEFT JOIN appointments a ON a.patient_id = p.patient_id
        GROUP BY p.patient_id
        ORDER BY p.full_name
        """
    ).fetchall()
    return render_template("patients.html", patients=rows)


@app.route("/doctors")
@login_required
def doctors():
    db = get_db()
    doctor_rows = db.execute(
        """
        SELECT d.*, COUNT(DISTINCT a.appointment_id) AS appointment_count
        FROM doctors d
        LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
        GROUP BY d.doctor_id
        ORDER BY d.full_name
        """
    ).fetchall()
    availability = db.execute(
        """
        SELECT da.*, d.full_name AS doctor_name
        FROM doctor_availability da
        JOIN doctors d ON d.doctor_id = da.doctor_id
        ORDER BY d.full_name, da.day_of_week, da.start_time
        """
    ).fetchall()
    return render_template("doctors.html", doctors=doctor_rows, availability=availability)


@app.route("/appointments", methods=("GET", "POST"))
@login_required
def appointments():
    db = get_db()
    role = g.user["role"]

    if request.method == "POST":
        patient_id = int(request.form["patient_id"])
        doctor_id = int(request.form["doctor_id"])
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]
        consultation_type = request.form["consultation_type"]
        reason = request.form["reason"].strip()
        payment_method = request.form["payment_method"]

        if role == "patient" and patient_id != g.user["patient_id"]:
            flash("Patients can only book for themselves.", "error")
            return redirect(url_for("appointments"))

        try:
            db.execute("BEGIN IMMEDIATE")
            conflict = db.execute(
                """
                SELECT appointment_id
                FROM appointments
                WHERE doctor_id = ?
                  AND appointment_date = ?
                  AND appointment_time = ?
                  AND status IN ('Scheduled', 'Confirmed')
                """,
                (doctor_id, appointment_date, appointment_time),
            ).fetchone()
            if conflict:
                raise ValueError("This doctor already has an appointment at the selected time.")

            db.execute(
                """
                INSERT INTO appointments
                (patient_id, doctor_id, appointment_date, appointment_time, consultation_type, status, reason)
                VALUES (?, ?, ?, ?, ?, 'Scheduled', ?)
                """,
                (patient_id, doctor_id, appointment_date, appointment_time, consultation_type, reason),
            )
            appointment_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            fee = db.execute(
                "SELECT consultation_fee FROM doctors WHERE doctor_id = ?",
                (doctor_id,),
            ).fetchone()["consultation_fee"]
            db.execute(
                """
                INSERT INTO payments
                (appointment_id, patient_id, amount, payment_method, payment_status, paid_on)
                VALUES (?, ?, ?, ?, 'Pending', NULL)
                """,
                (appointment_id, patient_id, fee, payment_method),
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            flash(str(exc), "error")
        except sqlite3.DatabaseError:
            db.rollback()
            flash("Booking failed due to a database error.", "error")
        else:
            flash("Appointment booked and payment record created successfully.", "success")
        return redirect(url_for("appointments"))

    if role == "patient":
        appointment_rows = db.execute(
            """
            SELECT a.*, d.full_name AS doctor_name, d.specialization, p.full_name AS patient_name
            FROM appointments a
            JOIN doctors d ON d.doctor_id = a.doctor_id
            JOIN patients p ON p.patient_id = a.patient_id
            WHERE a.patient_id = ?
            ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """,
            (g.user["patient_id"],),
        ).fetchall()
    elif role == "doctor":
        appointment_rows = db.execute(
            """
            SELECT a.*, d.full_name AS doctor_name, d.specialization, p.full_name AS patient_name
            FROM appointments a
            JOIN doctors d ON d.doctor_id = a.doctor_id
            JOIN patients p ON p.patient_id = a.patient_id
            WHERE a.doctor_id = ?
            ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """,
            (g.user["doctor_id"],),
        ).fetchall()
    else:
        appointment_rows = db.execute(
            """
            SELECT a.*, d.full_name AS doctor_name, d.specialization, p.full_name AS patient_name
            FROM appointments a
            JOIN doctors d ON d.doctor_id = a.doctor_id
            JOIN patients p ON p.patient_id = a.patient_id
            ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """
        ).fetchall()

    patient_rows = db.execute("SELECT patient_id, full_name FROM patients ORDER BY full_name").fetchall()
    doctor_rows = db.execute(
        "SELECT doctor_id, full_name, specialization, consultation_fee FROM doctors ORDER BY full_name"
    ).fetchall()
    if role == "patient":
        payment_rows = db.execute(
            """
            SELECT pay.*, p.full_name AS patient_name, d.full_name AS doctor_name, a.created_at AS booked_on
            FROM payments pay
            JOIN appointments a ON a.appointment_id = pay.appointment_id
            JOIN patients p ON p.patient_id = pay.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
            WHERE pay.patient_id = ?
            ORDER BY pay.payment_id DESC
            LIMIT 10
            """,
            (g.user["patient_id"],),
        ).fetchall()
    elif role == "doctor":
        payment_rows = db.execute(
            """
            SELECT pay.*, p.full_name AS patient_name, d.full_name AS doctor_name, a.created_at AS booked_on
            FROM payments pay
            JOIN appointments a ON a.appointment_id = pay.appointment_id
            JOIN patients p ON p.patient_id = pay.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
            WHERE a.doctor_id = ?
            ORDER BY pay.payment_id DESC
            LIMIT 10
            """,
            (g.user["doctor_id"],),
        ).fetchall()
    else:
        payment_rows = db.execute(
            """
            SELECT pay.*, p.full_name AS patient_name, d.full_name AS doctor_name, a.created_at AS booked_on
            FROM payments pay
            JOIN appointments a ON a.appointment_id = pay.appointment_id
            JOIN patients p ON p.patient_id = pay.patient_id
            JOIN doctors d ON d.doctor_id = a.doctor_id
            ORDER BY pay.payment_id DESC
            LIMIT 10
            """
        ).fetchall()
    return render_template(
        "appointments.html",
        appointments=appointment_rows,
        patients=patient_rows,
        doctors=doctor_rows,
        payments=payment_rows,
    )


@app.route("/appointments/<int:appointment_id>")
@login_required
def appointment_detail(appointment_id: int):
    db = get_db()
    appointment = db.execute(
        """
        SELECT a.*, p.full_name AS patient_name, p.email AS patient_email, p.phone AS patient_phone,
               d.full_name AS doctor_name, d.specialization, d.email AS doctor_email, d.phone AS doctor_phone,
               d.years_of_experience, d.consultation_fee
        FROM appointments a
        JOIN patients p ON p.patient_id = a.patient_id
        JOIN doctors d ON d.doctor_id = a.doctor_id
        WHERE a.appointment_id = ?
        """,
        (appointment_id,),
    ).fetchone()
    if appointment is None:
        abort(404)

    role = g.user["role"]
    if role == "patient" and appointment["patient_id"] != g.user["patient_id"]:
        abort(403)
    if role == "doctor" and appointment["doctor_id"] != g.user["doctor_id"]:
        abort(403)

    prescription = db.execute(
        """
        SELECT *
        FROM prescriptions
        WHERE appointment_id = ?
        ORDER BY prescription_id DESC
        LIMIT 1
        """,
        (appointment_id,),
    ).fetchone()
    medical_record = db.execute(
        """
        SELECT *
        FROM medical_records
        WHERE appointment_id = ?
        ORDER BY record_id DESC
        LIMIT 1
        """,
        (appointment_id,),
    ).fetchone()
    payment = db.execute(
        "SELECT * FROM payments WHERE appointment_id = ?",
        (appointment_id,),
    ).fetchone()

    return render_template(
        "appointment_detail.html",
        appointment=appointment,
        prescription=prescription,
        medical_record=medical_record,
        payment=payment,
    )


@app.route("/records")
@login_required
def records():
    db = get_db()
    role = g.user["role"]

    if role == "patient":
        medical_records = db.execute(
            """
            SELECT mr.*, d.full_name AS doctor_name, p.full_name AS patient_name
            FROM medical_records mr
            JOIN doctors d ON d.doctor_id = mr.doctor_id
            JOIN patients p ON p.patient_id = mr.patient_id
            WHERE mr.patient_id = ?
            ORDER BY mr.record_date DESC
            """,
            (g.user["patient_id"],),
        ).fetchall()
        prescriptions = db.execute(
            """
            SELECT pr.*, d.full_name AS doctor_name
            FROM prescriptions pr
            JOIN doctors d ON d.doctor_id = pr.doctor_id
            WHERE pr.patient_id = ?
            ORDER BY pr.issued_on DESC
            """,
            (g.user["patient_id"],),
        ).fetchall()
    elif role == "doctor":
        medical_records = db.execute(
            """
            SELECT mr.*, d.full_name AS doctor_name, p.full_name AS patient_name
            FROM medical_records mr
            JOIN doctors d ON d.doctor_id = mr.doctor_id
            JOIN patients p ON p.patient_id = mr.patient_id
            WHERE mr.doctor_id = ?
            ORDER BY mr.record_date DESC
            """,
            (g.user["doctor_id"],),
        ).fetchall()
        prescriptions = db.execute(
            """
            SELECT pr.*, p.full_name AS patient_name
            FROM prescriptions pr
            JOIN patients p ON p.patient_id = pr.patient_id
            WHERE pr.doctor_id = ?
            ORDER BY pr.issued_on DESC
            """,
            (g.user["doctor_id"],),
        ).fetchall()
    else:
        medical_records = db.execute(
            """
            SELECT mr.*, d.full_name AS doctor_name, p.full_name AS patient_name
            FROM medical_records mr
            JOIN doctors d ON d.doctor_id = mr.doctor_id
            JOIN patients p ON p.patient_id = mr.patient_id
            ORDER BY mr.record_date DESC
            """
        ).fetchall()
        prescriptions = db.execute(
            """
            SELECT pr.*, d.full_name AS doctor_name, p.full_name AS patient_name
            FROM prescriptions pr
            JOIN doctors d ON d.doctor_id = pr.doctor_id
            JOIN patients p ON p.patient_id = pr.patient_id
            ORDER BY pr.issued_on DESC
            """
        ).fetchall()

    return render_template("records.html", medical_records=medical_records, prescriptions=prescriptions)


@app.route("/reports/<int:patient_id>/download")
@login_required
def download_patient_report(patient_id: int):
    if not can_access_patient(patient_id):
        abort(403)

    db = get_db()
    try:
        report_text = build_patient_report(db, patient_id)
    except LookupError:
        abort(404)

    patient = db.execute("SELECT full_name FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
    filename = f"{patient['full_name'].lower().replace(' ', '_')}_report.pdf"
    response = make_response(build_patient_report_pdf(report_text))
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/analytics")
@role_required("admin", "receptionist")
def analytics():
    db = get_db()
    specialization_stats = db.execute(
        """
        SELECT d.specialization, COUNT(a.appointment_id) AS total_appointments
        FROM doctors d
        LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
        GROUP BY d.specialization
        ORDER BY total_appointments DESC, d.specialization
        """
    ).fetchall()
    status_stats = db.execute(
        """
        SELECT status, COUNT(*) AS total
        FROM appointments
        GROUP BY status
        ORDER BY total DESC
        """
    ).fetchall()
    return render_template("analytics.html", specialization_stats=specialization_stats, status_stats=status_stats)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
