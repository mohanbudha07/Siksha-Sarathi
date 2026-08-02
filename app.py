from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re
import os

# ------------------------------
# 1. APP CONFIGURATION
# ------------------------------
app = Flask(__name__)

# Database Configuration (Update these with your actual details)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Sanji521'       # Put your MySQL password here if you have one
app.config['MYSQL_DB'] = 'siksha_sarathi'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.secret_key = 'your_super_secret_key_123' # Change this to something random

# Initialize MySQL
mysql = MySQL(app)

# ------------------------------
# 2. ROLE CONSTANTS
# ------------------------------

STUDENT = "student"
TEACHER = "teacher"
ADMIN = "admin"
# ------------------------------
# 3. DECORATORS (Security)
# ------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):

            if 'user_id' not in session:
                flash("Please login first.", "warning")
                return redirect(url_for('login'))

            if session.get('role') != role:
                flash("Access Denied.", "danger")
                return redirect(url_for('login'))

            return f(*args, **kwargs)

        return decorated
    return wrapper

# ------------------------------
# 4. ROUTES
# ------------------------------

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))

        if not role:
            role = "student"

        try:
            cur = mysql.connection.cursor()

            # Check existing email
            cur.execute(
                "SELECT id FROM users WHERE email=%s",
                (email,)
            )

            user = cur.fetchone()

            if user:
                flash("Email already registered.", "warning")
                cur.close()
                return redirect(url_for('register'))

            # Encrypt password
            hashed_password = generate_password_hash(password)

            # Insert user
            cur.execute(
                """
                INSERT INTO users
                (username, email, password, role)
                VALUES (%s,%s,%s,%s)
                """,
                (
                    username,
                    email,
                    hashed_password,
                    role
                )
            )

            mysql.connection.commit()
            cur.close()

            flash(
                "Registration successful. Please login.",
                "success"
            )

            return redirect(url_for('login'))

        except Exception as e:

            mysql.connection.rollback()
            flash(
                f"Database Error: {e}",
                "danger"
            )

    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash("Please enter email and password.", "danger")
            return redirect(url_for('login'))

        try:
            cur = mysql.connection.cursor()

            cur.execute(
                "SELECT * FROM users WHERE email=%s",
                (email,)
            )

            user = cur.fetchone()

            cur.close()

            if user and check_password_hash(user['password'], password):

                session.clear()

                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']

                flash(
                    f"Welcome {user['username']}!",
                    "success"
                )

                if user['role'] == 'student':
                    return redirect(url_for('student_dashboard'))

                elif user['role'] == 'teacher':
                    return redirect(url_for('teacher_dashboard'))

                elif user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))

            else:
                flash(
                    "Invalid email or password.",
                    "danger"
                )

        except Exception as e:

            flash(
                f"Database Error: {e}",
                "danger"
            )

    return render_template('login.html')

@app.route('/student_dashboard')
@login_required
@role_required(STUDENT)
def student_dashboard():
    return render_template(
        'dashboard.html',
        name=session.get('username')
    )
@app.route('/teacher_dashboard')
@login_required
@role_required(TEACHER)
def teacher_dashboard():
    return render_template('teacher_dashboard.html', name=session.get('user_name'))

@app.route('/admin_dashboard')
@login_required
@role_required(ADMIN)
def admin_dashboard():
    return render_template('admin_dashboard.html', name=session.get('user_name'))

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

# ------------------------------
# 5. RUN THE APP
# ------------------------------
if __name__ == '__main__':
    app.run(debug=True)