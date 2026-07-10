PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    gender TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL UNIQUE,
    address TEXT,
    blood_group TEXT,
    allergies TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    specialization TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL UNIQUE,
    years_of_experience INTEGER NOT NULL DEFAULT 0,
    consultation_fee REAL NOT NULL CHECK (consultation_fee >= 0)
);

CREATE TABLE IF NOT EXISTS doctor_availability (
    availability_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    consultation_mode TEXT NOT NULL CHECK (consultation_mode IN ('Online', 'Offline')),
    FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    consultation_type TEXT NOT NULL CHECK (consultation_type IN ('Online', 'Offline')),
    status TEXT NOT NULL CHECK (status IN ('Scheduled', 'Confirmed', 'Completed', 'Cancelled')),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS medical_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_id INTEGER UNIQUE,
    diagnosis TEXT NOT NULL,
    treatment_notes TEXT NOT NULL,
    vitals TEXT,
    record_date TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
    FOREIGN KEY (appointment_id) REFERENCES appointments (appointment_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    medicines TEXT NOT NULL,
    instructions TEXT NOT NULL,
    issued_on TEXT NOT NULL,
    FOREIGN KEY (appointment_id) REFERENCES appointments (appointment_id) ON DELETE SET NULL,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id INTEGER NOT NULL UNIQUE,
    patient_id INTEGER NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    payment_method TEXT NOT NULL,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('Pending', 'Paid', 'Failed', 'Refunded')),
    paid_on TEXT,
    FOREIGN KEY (appointment_id) REFERENCES appointments (appointment_id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'receptionist', 'doctor', 'patient')),
    patient_id INTEGER UNIQUE,
    doctor_id INTEGER UNIQUE,
    FOREIGN KEY (patient_id) REFERENCES patients (patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
    CHECK (
        (role = 'patient' AND patient_id IS NOT NULL AND doctor_id IS NULL) OR
        (role = 'doctor' AND doctor_id IS NOT NULL AND patient_id IS NULL) OR
        (role IN ('admin', 'receptionist') AND patient_id IS NULL AND doctor_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_appointments_doctor_slot
ON appointments (doctor_id, appointment_date, appointment_time);

CREATE INDEX IF NOT EXISTS idx_appointments_patient_date
ON appointments (patient_id, appointment_date);

CREATE INDEX IF NOT EXISTS idx_medical_records_patient_date
ON medical_records (patient_id, record_date);

CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_date
ON prescriptions (patient_id, issued_on);
