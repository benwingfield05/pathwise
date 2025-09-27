import sqlite3
import random
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

        flash("Account created successfully. Please log in.")
        return redirect(url_for("index"))

    return render_template("register_step2.html", app_name=app_name)

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
    app.run(debug=True)