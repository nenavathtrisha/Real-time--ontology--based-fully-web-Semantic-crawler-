# Smart Healthcare Appointment and Telemedicine System

This project is a database-driven web application for managing patients, doctors, appointments, prescriptions, payments, and medical records for a telemedicine workflow.

## Tech stack

- Flask web framework
- SQLite relational database
- Normalized schema with primary keys, foreign keys, constraints, and indexes
- Role-based login for `admin`, `receptionist`, `doctor`, and `patient`

## Features

- Patient, doctor, appointment, prescription, payment, and medical record tables
- ACID-aware appointment booking flow using a transaction and duplicate-slot validation
- Doctor availability tracking
- Payment records created automatically for each booking
- Role-aware dashboards and access controls
- Query-friendly analytics views for admins and reception staff

## How to run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the app:

```bash
python app.py
```

3. Open the local URL shown by Flask, usually `http://127.0.0.1:5000`.

## Demo logins

- `admin` / `admin123`
- `reception` / `reception123`
- `aarav` / `patient123`
- `drpriya` / `doctor123`
