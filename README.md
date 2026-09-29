# Siksha Sarathi

[![CI](https://github.com/mohanbudha07/Siksha-Sarathi/actions/workflows/ci.yml/badge.svg)](https://github.com/mohanbudha07/Siksha-Sarathi/actions/workflows/ci.yml)

**Siksha Sarathi** is a smart education platform designed for secondary-level students and teachers.  
It helps students track their academic performance using Machine Learning, take quizzes, access learning notes, and get help from an AI assistant.

---

## Features

### Student
- Student Dashboard
- Learning Notes
- Interactive Quizzes
- Evidence-based practice plans from quiz activity
- Gemini-powered Study Assistant with an automatic offline fallback
- Grounded tutoring mode with authorized school context and safe provenance

### Phase 11 grounded tutor
- `GROUNDED_TUTOR_VERSION = "1"`
- Subject selection is restricted to the student's current authorized class subjects.
- The assistant uses only the logged-in student's own current-class data, notes, recommendations, and active support plans.
- Personalization is limited to minimal, relevant context and never includes raw ML feature vectors, credentials, or internal IDs.
- Prompting explicitly treats notes/resources as untrusted reference material, not instructions.
- The assistant remains useful in `general_only` mode and may fall back to offline help without a live Gemini key.
- No prediction or model metadata is sent to Gemini, and no Gemini search/web tools are enabled.

### Teacher
- Teacher Dashboard
- Upload & Manage Notes
- View class-scoped learning analytics and intervention progress
- Active class teachers record monthly attendance registers

### Attendance
- Students see their own monthly attendance history, including previous classes.
- Admins have read-only class/month oversight and register inspection.
- Saved attendance remains available after student transfers; new register rosters use active enrollments only.

### Admin
- System Overview Dashboard

### Notices
- Notices are immutable, one-way official announcements; Chat is a separate feature.
- Admins can target the institution, students, teachers, a class, or one person; only Admins can publish public notices.
- Teachers can publish internal notices only within active class-teacher or assigned subject scopes.
- Recipients are snapshotted at publication, so class transfers do not erase prior deliveries; inbox read state is per recipient.
- The public homepage reads only institution-wide public notices from the public feed.

---

## Tech Stack

**Frontend**
- React + Vite
- React Router
- Axios
- Material UI (partial)

**Backend**
- Python Flask
- Flask-CORS
- MySQL
- Session-based Authentication

**Machine Learning**
- Scikit-learn
- Joblib

---

## Local setup

Create a private environment file before starting the backend:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated value into `SECRET_KEY` in `.env`, then enter the local
MySQL password in `MYSQL_PASSWORD`. The `.env` file is ignored by Git and must
never be committed.

The Study Assistant works in limited offline mode without an external key. To
enable Gemini answers, create a Gemini API key and add it only to your private
`.env` file:

```bash
GEMINI_API_KEY=your_private_key
GEMINI_MODEL=gemini-flash-latest
```

Never put the real API key in `.env.example`, source code, screenshots or Git.

School administrators provision all administrator, teacher, and student
accounts. Teachers and students sign in with accounts issued by the school;
public account registration is not available.

Authentication portal summary:
- Student/Teacher portal: `/login` and `POST /api/login`
- Admin/Principal portal: `/admin/login` and `POST /api/admin/login`
- The submitted portal role is a UI choice only; the persisted database role is
  authoritative when the backend checks credentials.
- There is no public registration flow and no `super_admin` role in the
  current single-school release.

Public website summary:
- The root path `/` is a public institution landing page with sections for Home,
  About, Academics, Faculty, Notices, and Contact.
- The page keeps Student/Teacher and Admin portal buttons available without
  requiring authentication on the public site.
- Public content is intentionally config-driven from the frontend profile file
  so the institution can update the landing page without a separate notice-management backend.
- The protected portal and admin dashboards remain separate from the public
  website and continue to enforce the role-based access rules.

Login attempts are rate-limited per client IP and email. The default in-memory
storage is appropriate for this single-process prototype. A multi-worker
deployment should set `RATELIMIT_STORAGE_URI` to a shared backend such as Redis.

Install and run the backend:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m backend.app
```

Run the React frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

For production, set `APP_ENV=production`, configure the deployed frontend in
`CORS_ORIGINS`, use HTTPS, and set `SESSION_COOKIE_SECURE=true`. The application
refuses to start in production without `SECRET_KEY`.

## Project Structure

```text
frontend/       React application
backend/        Flask application, routes, schema, migrations, scripts and tests
ai/             Study assistant and machine-learning code and data
requirements.txt
```

Backend tests:

```bash
python -m unittest discover -s backend/tests -q
```

Database schema and migrations are in `backend/setup_db.sql` and
`backend/migrations/`. AI and ML code are in `ai/` and `ai/ml/`.
