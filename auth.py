# auth.py
import os, sqlite3
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from passlib.hash import bcrypt

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB = os.path.join(BASE_DIR, "users.db")

def get_db():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# ---- helpers ----
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


# ---- routes ----
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    username = request.form.get("username","").strip()
    password = request.form.get("password","")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not bcrypt.verify(password, row["password_hash"]):
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401
    session["user_id"] = row["id"]
    session["username"] = row["username"]
    return redirect(url_for("auth.settings"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

## User Registration
@auth_bp.route("/register", methods=["GET","POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    username = request.form["username"].strip()
    email    = request.form["email"].strip()
    phone    = request.form.get("phone","").strip()
    dob      = request.form.get("date_of_birth","")
    pw       = request.form["password"]


    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username=? OR email=?", (username, email)
        ).fetchone()
        if exists:
            flash("Username or email already exists.", "error")
            return render_template("register.html"), 400
        conn.execute(
            """INSERT INTO users (username,email,phone,password_hash,date_of_birth,created_at)
               VALUES (?,?,?,?,?,?)""",
            (username, email, phone, bcrypt.hash(pw), dob, datetime.utcnow().isoformat())
        )
        conn.commit()
    return redirect(url_for("auth.login"))


@auth_bp.route("/settings")
@login_required
def settings():
    user = current_user()
    with get_db() as conn:
        locs = conn.execute(
            "SELECT id,label,latitude,longitude,is_primary "
            "FROM locations WHERE user_id=? "
            "ORDER BY is_primary DESC, id DESC",
            (user["id"],)
        ).fetchall()
    return render_template("settings.html", user=user, locations=locs)


@auth_bp.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    user = current_user()
    cur_pw = request.form["current_password"]
    if not bcrypt.verify(cur_pw, user["password_hash"]):
        flash("Current password incorrect.", "error")
        return redirect(url_for("auth.settings"))

    email = request.form.get("email","").strip()
    phone = request.form.get("phone","").strip()
    new_pw = request.form.get("new_password","")
    with get_db() as conn:
        if new_pw:
            conn.execute("UPDATE users SET email=?, phone=?, password_hash=? WHERE id=?",
                         (email, phone, bcrypt.hash(new_pw), user["id"]))
        else:
            conn.execute("UPDATE users SET email=?, phone=? WHERE id=?",
                         (email, phone, user["id"]))
        conn.commit()
    flash("Profile updated.", "ok")
    return redirect(url_for("auth.settings"))


@auth_bp.route("/add_location", methods=["POST"])
@login_required
def add_location():
    user = current_user()
    label = request.form["label"].strip()          # e.g., "Home Stop 01012"
    lat   = request.form.get("latitude") or None
    lon   = request.form.get("longitude") or None
    with get_db() as conn:
        conn.execute(
            "INSERT INTO locations (user_id,label,latitude,longitude,is_primary) VALUES (?,?,?,?,0)",
            (user["id"], label, lat, lon)
        )
        conn.commit()
    return redirect(url_for("auth.settings"))

@auth_bp.route("/delete_location/<int:loc_id>", methods=["POST"])
@login_required
def delete_location(loc_id):
    user = current_user()
    with get_db() as conn:
        conn.execute(
            "DELETE FROM locations WHERE id=? AND user_id=? AND is_primary=0",
            (loc_id, user["id"])
        )
        conn.commit()
    return redirect(url_for("auth.settings"))


@auth_bp.route("/delete_locations", methods=["POST"])
@login_required
def delete_locations():
    user = current_user()
    ids = request.form.getlist("delete_ids")
    if ids:
        qmarks = ",".join("?" for _ in ids)
        with get_db() as conn:
            conn.execute(
                f"DELETE FROM locations WHERE id IN ({qmarks}) AND user_id=? AND is_primary=0",
                (*ids, user["id"])
            )
            conn.commit()
    return redirect(url_for("auth.settings"))


@auth_bp.route("/primary_location/<int:loc_id>", methods=["POST"])
@login_required
def primary_location(loc_id):
    user = current_user()
    with get_db() as conn:
        conn.execute("UPDATE locations SET is_primary=0 WHERE user_id=?", (user["id"],))
        conn.execute("UPDATE locations SET is_primary=1 WHERE id=? AND user_id=?", (loc_id, user["id"]))
        conn.commit()
    return redirect(url_for("auth.settings"))