import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
DATABASE = "database.db"

app_name = "PathWise"

# ---------- DB HELPER FUNCTIONS ----------
# Get the database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# Initialize the database if not already created
def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT,
            school TEXT,
            year TEXT,
            major TEXT,
            gpa REAL
        )
    """)
    db.commit()


# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html", app_name=app_name)

# First step in registration
@app.route("/register", methods=["GET", "POST"])
def register_step1():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Store hashed password
        session["new_user_email"] = email
        session["new_user_password"] = generate_password_hash(password)

        return redirect(url_for("register_step2"))
    return render_template("register_step1.html", app_name=app_name)

# Second step in registration
@app.route("/register/details", methods=["GET", "POST"])
def register_step2():
    if "new_user_email" not in session:
        return redirect(url_for("register_step1"))

    if request.method == "POST":
        name = request.form.get("name")
        school = request.form.get("school")
        year = request.form.get("year")
        major = request.form.get("major")
        gpa = request.form.get("gpa")

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (email, password, name, school, year, major, gpa) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session["new_user_email"],
                    session["new_user_password"],
                    name, school, year, major, gpa
                )
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("Email already registered.")
            return redirect(url_for("register_step1"))

        # clear session temp vars
        session.pop("new_user_email", None)
        session.pop("new_user_password", None)
        
        if (major == "undecided"):
            return redirect(url_for("major_quiz"))
        
        flash("Account created successfully. Please log in.")
        return redirect(url_for("index"))
    
    majors = {
        ("STEM & Data", "Computer Science, Engineering, Math, Physics, Statistics"),
        ("Arts & Humanities", "English, Journalism, Communications, Philosophy, History"),
        ("Health & Sciences", "Biology, Chemistry, Nursing, Pre-Med, Environmental Science"),
        ("Creative & Design", "Art, Music, Graphic Design, Theater, Film, Architecture"),
        ("Social Sciences & Business", "Psychology, Sociology, Political Science, Education, Business, Economics")
    }

    return render_template("register_step2.html", app_name=app_name, majors=majors)

@app.route("/major_quiz", methods=["GET", "POST"])
def major_quiz():
    # question text + options
    questions = {
        1: {"text": "What subjects or activities do you genuinely enjoy?",
            "options": {"a": "Math, logic, problem-solving",
                        "b": "Writing, reading, storytelling",
                        "c": "Science and experiments",
                        "d": "Art, music, design",
                        "e": "Helping people, teaching, volunteering"}},
        2: {"text": "Which high school classes did you look forward to most?",
            "options": {"a": "Math or Computer Science",
                        "b": "English or History",
                        "c": "Biology or Chemistry",
                        "d": "Art or Theater",
                        "e": "Business or Economics"}},
        3: {"text" : "What are your strongest skills?",
            "options" : {"a": "Logical reasoning, analysis",
                         "b": "Writing, communication",
                         "c": "Scientific observation, lab work",
                         "d": "Creativity, design",
                         "e": "Empathy, leadership, helping others"}},
        4: {"text" : "What type of work do you prefer?",
            "options" : {"a": "Numbers and Data",
                         "b": "Words and Ideas",
                         "c": "Experiments and Fieldwork",
                         "d": "Creative Projects",
                         "e": "Working With People"}},
        5: {"text" : "Do you prefer structured or open-ended tasks?",
            "options" : {"a": "Structured tasks with rules",
                         "b": "Open-ended, creative projects",
                         "c": "A balance of both"}},
        6: {"text" : "Would you rather?",
            "options" : {"a": "Work independently",
                         "b": "Collaborate in teams",
                         "c": "Lead others"}},
        7: {"text" : "What kind of impact do you want your work to have?",
            "options" : {"a": "Solve technical or scientific problems",
                         "b": "Inspire or inform others",
                         "c": "Heal, teach, or support people directly",
                         "d": "Shape businesses, organizations, or governments"}},  
        8: {"text" : "What matters more to you in a career?",
            "options" : {"a": "High salary and stability",
                         "b": "Passion and fulfillment",
                         "c": "A mix of both"}},
        9: {"text" : "Which careers/majors spark curiosity for you?",
            "options" : {"a": "STEM (science, tech, engineering, math)",
                         "b": "Arts & Humanities",
                         "c": "Social Sciences (psych, sociology, political science)",
                         "d": "Health & Medicine",
                         "e": "Business & Economics"}},
        10: {"text" : "What lifestyle do you see yourself having?",
            "options" : {"a": "Fast-paced corporate or tech career",
                         "b": "Flexible creative/freelance lifestyle",
                         "c": "Steady professional (doctor, engineer, teacher)",
                         "d": "Entrepreneurial, leadership-driven",
                         "e": "Research-focused or academic"}}                                                                                                                                              
    }

    # Category mapping
    categories = {
        "a": {"name": "STEM & Data",
              "majors": ["Computer Science", "Engineering", "Math", "Physics", "Statistics"]},
        "b": {"name": "Arts & Humanities",
              "majors": ["English", "Journalism", "Communications", "Philosophy", "History"]},
        "c": {"name": "Health & Sciences",
              "majors": ["Biology", "Chemistry", "Nursing", "Pre-Med", "Environmental Science"]},
        "d": {"name": "Creative & Design",
              "majors": ["Art", "Music", "Graphic Design", "Theater", "Film", "Architecture"]},
        "e": {"name": "Social Sciences & Business",
              "majors": ["Psychology", "Sociology", "Political Science", "Education", "Business", "Economics"]},
    }

    if request.method == "POST":
        counts = {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0}

        # Tally answers
        for i in questions.keys():
            ans = request.form.get(f"q{i}")
            if ans in counts:
                counts[ans] += 1

        # Find which letter is most common
        top_letter = max(counts, key=counts.get)
        recommended_category = categories[top_letter]

        return render_template("quiz_results.html",
                               category=recommended_category["name"],
                               majors=recommended_category["majors"],
                               counts=counts)

    return render_template("quiz.html", questions=questions)

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        flash("Logged in successfully.")
        return redirect(url_for("dashboard"))
    else:
        flash("Invalid email or password.")
        return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))

    db = get_db()
    name = db.execute("SELECT name FROM users WHERE id = ?", (session["user_id"],)).fetchone()["name"]
    return render_template("dashboard.html", app_name=app_name, name=name)

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)