
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps



import os
import joblib
import numpy as np
# ------------------------------
# APP CONFIGURATION
# ------------------------------

app = Flask(__name__)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Sanji521'
app.config['MYSQL_DB'] = 'siksha_sarathi'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

app.secret_key = 'your_super_secret_key_123'

mysql = MySQL(app)

# ------------------------------
# LOAD MACHINE LEARNING MODEL
# ------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

model = joblib.load(
    os.path.join(BASE_DIR, "ml", "performance_model.pkl")
)

label_encoder = joblib.load(
    os.path.join(BASE_DIR, "ml", "label_encoder.pkl")
)



# ------------------------------
# ROLES
# ------------------------------

STUDENT = "student"
TEACHER = "teacher"
ADMIN = "admin"


# ------------------------------
# SECURITY DECORATORS
# ------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):

        if 'user_id' not in session:
            flash("Please login first.", "warning")
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated



def role_required(role):

    def decorator(f):

        @wraps(f)
        def decorated(*args, **kwargs):

            if 'user_id' not in session:
                return redirect(url_for('login'))

            if session.get('role') != role:
                flash("Access Denied.", "danger")
                return redirect(url_for('login'))

            return f(*args, **kwargs)

        return decorated

    return decorator



# ------------------------------
# HOME
# ------------------------------

@app.route('/')
def home():
    return render_template('home.html')



# ------------------------------
# REGISTER
# ------------------------------

@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        if not role:
            role = "student"


        try:

            cur = mysql.connection.cursor()

            cur.execute(
                "SELECT id FROM users WHERE email=%s",
                (email,)
            )

            if cur.fetchone():

                flash("Email already registered.", "warning")
                return redirect(url_for('register'))


            hashed_password = generate_password_hash(password)


            cur.execute(
                """
                INSERT INTO users
                (username,email,password,role)
                VALUES(%s,%s,%s,%s)
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


            flash("Registration successful.", "success")

            return redirect(url_for('login'))


        except Exception as e:

            flash(f"Database Error: {e}", "danger")


    return render_template('register.html')



# ------------------------------
# LOGIN
# ------------------------------

@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':

        email=request.form.get('email')
        password=request.form.get('password')


        cur=mysql.connection.cursor()

        cur.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user=cur.fetchone()

        cur.close()



        if user and check_password_hash(user['password'],password):

            session.clear()

            session['user_id']=user['id']
            session['username']=user['username']
            session['role']=user['role']


            flash(
                f"Welcome {user['username']}",
                "success"
            )


            if user['role']=="student":
                return redirect(url_for('student_dashboard'))

            elif user['role']=="teacher":
                return redirect(url_for('teacher_dashboard'))

            elif user['role']=="admin":
                return redirect(url_for('admin_dashboard'))


        else:

            flash(
                "Invalid email or password",
                "danger"
            )


    return render_template('login.html')



# ------------------------------
# STUDENT DASHBOARD
# ------------------------------

@app.route('/student_dashboard')
@login_required
@role_required(STUDENT)
def student_dashboard():

    return render_template(
        'dashboard.html',
        name=session.get('username')
    )



# ------------------------------
# STUDENT NOTES VIEW
# ------------------------------

@app.route('/notes')
@login_required
@role_required(STUDENT)
def notes():

    cur=mysql.connection.cursor()

    cur.execute(
        """
        SELECT title,subject,chapter,content,created_at
        FROM notes
        ORDER BY created_at DESC
        """
    )

    notes=cur.fetchall()

    cur.close()


    return render_template(
        'notes.html',
        notes=notes
    )



# ------------------------------
# TEACHER DASHBOARD
# ------------------------------

@app.route('/teacher_dashboard')
@login_required
@role_required(TEACHER)
def teacher_dashboard():

    return render_template(
        'teacher_dashboard.html',
        name=session.get('username')
    )



# ------------------------------
# TEACHER UPLOAD NOTES
# ------------------------------

@app.route('/upload_notes', methods=['GET','POST'])
@login_required
@role_required(TEACHER)
def upload_notes():

    if request.method=="POST":

        title=request.form.get('title')
        subject=request.form.get('subject')
        chapter=request.form.get('chapter')
        content=request.form.get('content')


        cur=mysql.connection.cursor()


        cur.execute(
            """
            INSERT INTO notes
            (title,subject,chapter,content,uploaded_by)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (
                title,
                subject,
                chapter,
                content,
                session['user_id']
            )
        )


        mysql.connection.commit()

        cur.close()


        flash(
            "Note uploaded successfully",
            "success"
        )


        return redirect(url_for('upload_notes'))


    return render_template('upload_notes.html')



# ------------------------------
# OTHER PAGES
# ------------------------------


@app.route('/performance')
@login_required
@role_required(STUDENT)
def performance():
    return render_template('performance.html')

@app.route('/ai_assistant')
@login_required
@role_required(STUDENT)
def ai_assistant():
    return render_template('ai_assistant.html')


@app.route('/ask_ai', methods=['POST'])
@login_required
@role_required(STUDENT)
def ask_ai():

    question = request.form.get("question")

    from assistant import generate_answer

    subject, answer = generate_answer(question)

    cur = mysql.connection.cursor()

    cur.execute("""
        INSERT INTO chat_history
        (student_id, subject, question, answer)
        VALUES(%s,%s,%s,%s)
    """,
    (
        session['user_id'],
        subject,
        question,
        answer
    ))

    mysql.connection.commit()
    cur.close()

    return render_template(
        "ai_assistant.html",
        subject=subject,
        question=question,
        answer=answer
    )

@app.route('/predict', methods=['GET', 'POST'])
@login_required
@role_required(STUDENT)
def predict():

    prediction = None

    if request.method == "POST":

        attendance = float(request.form["attendance"])
        assignment = float(request.form["assignment"])
        quiz = float(request.form["quiz"])
        study_hours = float(request.form["study_hours"])

        prediction_result = model.predict([
            [attendance, assignment, quiz, study_hours]
        ])

        prediction = label_encoder.inverse_transform(prediction_result)[0]

        cur = mysql.connection.cursor()

        cur.execute("""
        INSERT INTO predictions
        (
            student_id,
            attendance,
            assignment_score,
            quiz_score,
            study_hours,
            prediction
        )
        VALUES(%s,%s,%s,%s,%s,%s)
        """,
        (
            session['user_id'],
            attendance,
            assignment,
            quiz,
            study_hours,
            prediction
        ))

        mysql.connection.commit()
        cur.close()

    return render_template(
        "predict.html",
        prediction=prediction
    )

@app.route('/admin_dashboard')
@login_required
@role_required(ADMIN)
def admin_dashboard():

    return render_template(
        'admin_dashboard.html'
    )



@app.route('/logout')
@login_required
def logout():

    session.clear()

    return redirect(url_for('login'))



# ------------------------------
# RUN
# ------------------------------

if __name__ == "__main__":
    app.run(debug=True)