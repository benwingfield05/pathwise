import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import time
import requests

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
SCORECARD_KEY = os.getenv("SCORECARD_API_KEY")
SCORECARD_BASE = "https://api.data.gov/ed/collegescorecard/v1/schools"
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

def init_school_table():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS schools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER UNIQUE,
            name TEXT,
            state TEXT,
            median_gpa REAL,
            sat_median INTEGER,
            act_median INTEGER,
            majors_json TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()

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

fields = [
    "id",
    "school.name",
    "school.state",
    "latest.admissions.sat_scores.average.overall",
    "latest.admissions.act_scores.midpoint.cumulative",
    "latest.admissions.admission_rate.overall"
]

# --- Scorecard fetcher + cache updater ---
def fetch_school_from_scorecard_by_id(school_id):
    url = "https://api.data.gov/ed/collegescorecard/v1/schools"
    params = {
        "id": school_id,
        "fields": ",".join(fields),
        "api_key": SCORECARD_KEY
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()["results"][0] if resp.json()["results"] else None

# Get school info by name
def fetch_school_from_scorecard_by_name(name):
    url = "https://api.data.gov/ed/collegescorecard/v1/schools"
    params = {
        "school.name" : name,
        "fields": ",".join(fields),
        "api_key": SCORECARD_KEY
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()["results"][0] if resp.json()["results"] else None

def upsert_school(db, school):
    db.execute("""
        INSERT INTO schools (school_id, name, state, median_gpa, sat_median, act_median, majors_json, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(school_id) DO UPDATE SET
            name=excluded.name,
            state=excluded.state,
            median_gpa=excluded.median_gpa,
            sat_median=excluded.sat_median,
            act_median=excluded.act_median,
            majors_json=excluded.majors_json,
            last_updated=CURRENT_TIMESTAMP
    """, (
        school.get("school_id"),
        school.get("name"),
        school.get("state"),
        school.get("median_gpa"),
        school.get("sat_median"),
        school.get("act_median"),
        json.dumps(school.get("majors_json")) if school.get("majors_json") else None
    ))
    db.commit()

# Example utility: bulk-update a small set of schools by id
def bulk_update_schools_by_ids(ids):
    db = get_db()
    for sid in ids:
        try:
            s = fetch_school_from_scorecard_by_id(sid)
            if s:
                upsert_school(db, s)
                time.sleep(0.2)  # be polite with API
        except Exception as e:
            current_app.logger.warning(f"fetch error for {sid}: {e}")


# ---------- GPA SCORING HELPERS ----------

def compute_school_score_gpa(user_gpa, school_gpa):
    """Compare user GPA to school GPA median. Normalized diff in [-1,1]."""
    if user_gpa is None or school_gpa is None:
        return 0.0
    user_norm = float(user_gpa) / 4.0
    school_norm = float(school_gpa) / 4.0
    return user_norm - school_norm

def classify_school_gpa(user_gpa, school_gpa):
    """Classify schools as reach/target/safety based on GPA delta only."""
    score = compute_school_score_gpa(user_gpa, school_gpa)
    if score <= -0.10:
        return {"classification": "reach", "score": score}
    elif score <= 0.10:
        return {"classification": "target", "score": score}
    else:
        return {"classification": "safety", "score": score}
    


# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html", app_name=app_name)

@app.route("/api/recommendations_gpa", methods=["POST"])
def api_recommendations_gpa():
    """
    Body JSON: { "gpa": 3.6, "candidate_school_ids": [100654, 139959] }
    """
    user = request.get_json() or {}
    user_gpa = user.get("gpa")
    if user_gpa is None:
        return jsonify({"error": "please supply user GPA"}), 400

    candidate_ids = user.get("candidate_school_ids") or []
    db = get_db()

    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = db.execute(f"SELECT * FROM schools WHERE school_id IN ({placeholders})", candidate_ids).fetchall()
    else:
        rows = db.execute("SELECT * FROM schools ORDER BY last_updated DESC LIMIT 10").fetchall()

    detail = []
    for r in rows:
        classification = classify_school_gpa(float(user_gpa), r["median_gpa"])
        record = dict(r)
        record.update(classification)
        detail.append(record)

    recommendations = {"reach": [], "target": [], "safety": []}
    for r in detail:
        recommendations[r["classification"]].append({
            "school_id": r["school_id"],
            "name": r["name"],
            "state": r["state"],
            "median_gpa": r["median_gpa"],
            "score": r["score"]
        })

    return jsonify({"recommendations": recommendations, "detail": detail})


@app.route("/api/insights_gpa", methods=["POST"])
def api_insights_gpa():
    """
    Body JSON: { "gpa": 3.6, "candidate_school_ids": [100654, 139959] }
    """
    import numpy as np

    user = request.get_json() or {}
    user_gpa = user.get("gpa")
    if user_gpa is None:
        return jsonify({"error": "please supply user GPA"}), 400

    candidate_ids = user.get("candidate_school_ids") or []
    db = get_db()

    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = db.execute(f"SELECT * FROM schools WHERE school_id IN ({placeholders})", candidate_ids).fetchall()
    else:
        rows = db.execute("SELECT * FROM schools ORDER BY last_updated DESC LIMIT 20").fetchall()

    values = [r["median_gpa"] for r in rows if r["median_gpa"] is not None]
    if not values:
        return jsonify({"error": "no GPA data for candidate schools"}), 400

    le = sum(1 for v in values if v <= float(user_gpa))
    user_pct = 100.0 * le / len(values)

    bins = np.arange(2.0, 4.1, 0.2)  # 2.0–4.0 in 0.2 steps
    hist, edges = np.histogram(values, bins=bins)
    labels = [f"{edges[i]:.1f}-{edges[i+1]:.1f}" for i in range(len(edges)-1)]

    return jsonify({
        "labels": labels,
        "counts": hist.tolist(),
        "user_percentile": user_pct,
        "n_schools": len(values)
    })

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
    user = db.execute("SELECT name, email FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if user is None:
        session.pop("user_id", None)
        flash("Please log in again.")
        return redirect(url_for("index"))

    display_name = user["name"] or user["email"].split("@")[0]
    return render_template("dashboard.html", app_name=app_name, name=display_name, email=user["email"])





@app.route("/insights")

def insights():

    if "user_id" not in session:

        return redirect(url_for("index"))



    db = get_db()

    user = db.execute("SELECT name, email FROM users WHERE id = ?", (session["user_id"],)).fetchone()



    if user is None:

        session.pop("user_id", None)

        flash("Please log in again.")

        return redirect(url_for("index"))



    display_name = user["name"] or user["email"].split("@")[0]



    categories = [

        {"name": "Reach", "percentile": random.randint(30, 75)},

        {"name": "Target", "percentile": random.randint(55, 90)},

        {"name": "Safety", "percentile": random.randint(70, 98)},

    ]



    metrics = [

        {"label": "GPA (Unweighted)", "value": "3.6"},

        {"label": "GPA (Weighted)", "value": "4.1"},

        {"label": "SAT Score", "value": "1450"},

    ]



    schools = [

        {

            "name": "Northbridge University",

            "logo": "https://via.placeholder.com/96?text=NU",

            "location": "Boston, MA",

            "percentile": f"{random.randint(30, 80)}%",

            "acceptance_rate": "24%",

            "average_sat": "1430",

        },

        {

            "name": "Summit College",

            "logo": "https://via.placeholder.com/96?text=SC",

            "location": "Denver, CO",

            "percentile": f"{random.randint(40, 90)}%",

            "acceptance_rate": "32%",

            "average_sat": "1370",

        },

        {

            "name": "Harbor State",

            "logo": "https://via.placeholder.com/96?text=HS",

            "location": "San Diego, CA",

            "percentile": f"{random.randint(55, 98)}%",

            "acceptance_rate": "48%",

            "average_sat": "1280",

        },

    ]



    return render_template("insights.html", app_name=app_name, name=display_name, email=user["email"], categories=categories, metrics=metrics, schools=schools)





@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.")
    return redirect(url_for("index"))

if __name__ == "__main__":
    with app.app_context():
        init_db()
        init_school_table()

        # Test API responses
        print(fetch_school_from_scorecard_by_id(100654))
        print(fetch_school_from_scorecard_by_name(name="Alabama A & M University"))
    app.run(debug=True)