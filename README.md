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

### Teacher
- Teacher Dashboard
- Upload & Manage Notes
- View class-scoped learning analytics and intervention progress

### Admin
- System Overview Dashboard

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
