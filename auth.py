# auth.py
import os
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from passlib.hash import bcrypt

# Import from database.py
from database import get_db_connection, IS_PRODUCTION

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")

# Remove these lines - no longer needed:
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# USERS_DB = os.path.join(BASE_DIR, "users.db")

# REMOVED: get_db() function - now using get_db_connection() from database.py


# ---- helpers ----
def current_user():
    """Get current logged-in user"""
    uid = session.get("user_id")
    if not uid:
        return None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL
        cursor.execute("SELECT * FROM users WHERE id=%s", (uid,))
    else:
        # SQLite
        cursor.execute("SELECT * FROM users WHERE id=?", (uid,))
    
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


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
    
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if IS_PRODUCTION:
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    else:
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row or not bcrypt.verify(password, row["password_hash"]):
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401
    
    session.clear()
    session.permanent = True 
    session["user_id"] = row["id"]
    session["username"] = row["username"]
    
    print(f"✅ Login successful for {username}")
    print(f"   User ID: {session.get('user_id')}")
    
    return redirect("/bus")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    
    username = request.form["username"].strip()
    email = request.form["email"].strip()
    phone = request.form.get("phone", "").strip()
    dob = request.form.get("date_of_birth", "")
    pw = request.form["password"]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if user exists
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                "SELECT 1 FROM users WHERE username=%s OR email=%s",
                (username, email)
            )
        else:
            # SQLite
            cursor.execute(
                "SELECT 1 FROM users WHERE username=? OR email=?",
                (username, email)
            )
        
        exists = cursor.fetchone()
        
        if exists:
            flash("Username or email already exists.", "error")
            cursor.close()
            conn.close()
            return render_template("register.html"), 400
        
        # Insert new user
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                """INSERT INTO users (username, email, phone, password_hash, date_of_birth, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (username, email, phone, bcrypt.hash(pw), dob, datetime.utcnow())
            )
        else:
            # SQLite
            cursor.execute(
                """INSERT INTO users (username, email, phone, password_hash, date_of_birth, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, email, phone, bcrypt.hash(pw), dob, datetime.utcnow().isoformat())
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("auth.login"))
        
    except Exception as e:
        print(f"Registration error: {e}")
        flash("Registration failed. Please try again.", "error")
        cursor.close()
        conn.close()
        return render_template("register.html"), 500


@auth_bp.route("/settings")
@login_required
def settings():
    user = current_user()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if IS_PRODUCTION:
        # PostgreSQL
        cursor.execute(
            """SELECT id, label, latitude, longitude, address, postal_code, is_favourite
               FROM locations WHERE user_id=%s
               ORDER BY is_primary DESC, id DESC""",
            (user["id"],)
        )
    else:
        # SQLite
        cursor.execute(
            """SELECT id, label, latitude, longitude, address, postal_code, is_favourite
               FROM locations WHERE user_id=?
               ORDER BY is_primary DESC, id DESC""",
            (user["id"],)
        )
    
    locs = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template("settings.html", user=user, locations=locs)


@auth_bp.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    user = current_user()
    cur_pw = request.form["current_password"]
    
    if not bcrypt.verify(cur_pw, user["password_hash"]):
        flash("Current password incorrect.", "error")
        return redirect(url_for("auth.settings"))
    
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    new_pw = request.form.get("new_password", "")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL
            if new_pw:
                cursor.execute(
                    "UPDATE users SET email=%s, phone=%s, password_hash=%s WHERE id=%s",
                    (email, phone, bcrypt.hash(new_pw), user["id"])
                )
            else:
                cursor.execute(
                    "UPDATE users SET email=%s, phone=%s WHERE id=%s",
                    (email, phone, user["id"])
                )
        else:
            # SQLite
            if new_pw:
                cursor.execute(
                    "UPDATE users SET email=?, phone=?, password_hash=? WHERE id=?",
                    (email, phone, bcrypt.hash(new_pw), user["id"])
                )
            else:
                cursor.execute(
                    "UPDATE users SET email=?, phone=? WHERE id=?",
                    (email, phone, user["id"])
                )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Profile updated.", "success")
    except Exception as e:
        print(f"Update profile error: {e}")
        flash("Profile update failed.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/add_location", methods=["POST"])
@login_required
def add_location():
    user = current_user()
    label = request.form["label"].strip()
    lat = request.form.get("latitude") or None
    lon = request.form.get("longitude") or None
    address = request.form.get("address", "").strip()
    postal_code = request.form.get("postal_code", "").strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                """INSERT INTO locations (user_id, label, latitude, longitude, address, postal_code, is_favourite)
                   VALUES (%s, %s, %s, %s, %s, %s, FALSE)""",
                (user["id"], label, lat, lon, address, postal_code)
            )
        else:
            # SQLite
            cursor.execute(
                """INSERT INTO locations (user_id, label, latitude, longitude, address, postal_code, is_favourite)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (user["id"], label, lat, lon, address, postal_code)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Location added successfully.", "success")
    except Exception as e:
        print(f"Add location error: {e}")
        flash("Failed to add location.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/delete_location/<int:loc_id>", methods=["POST"])
@login_required
def delete_location(loc_id):
    user = current_user()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                "DELETE FROM locations WHERE id=%s AND user_id=%s AND is_favourite=FALSE",
                (loc_id, user["id"])
            )
        else:
            # SQLite
            cursor.execute(
                "DELETE FROM locations WHERE id=? AND user_id=? AND is_favourite=0",
                (loc_id, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Location deleted.", "success")
    except Exception as e:
        print(f"Delete location error: {e}")
        flash("Failed to delete location.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/delete_locations", methods=["POST"])
@login_required
def delete_locations():
    user = current_user()
    ids = request.form.getlist("delete_ids")
    
    if not ids:
        return redirect(url_for("auth.settings"))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL - use ANY for array comparison
            cursor.execute(
                """DELETE FROM locations 
                   WHERE id = ANY(%s) AND user_id=%s AND is_favourite=FALSE""",
                (ids, user["id"])
            )
        else:
            # SQLite - use IN with placeholders
            qmarks = ",".join("?" for _ in ids)
            cursor.execute(
                f"""DELETE FROM locations 
                    WHERE id IN ({qmarks}) AND user_id=? AND is_favourite=0""",
                (*ids, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"{len(ids)} location(s) deleted.", "success")
    except Exception as e:
        print(f"Delete locations error: {e}")
        flash("Failed to delete locations.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/primary_location/<int:loc_id>", methods=["POST"])
@login_required
def primary_location(loc_id):
    user = current_user()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                "UPDATE locations SET is_primary=FALSE WHERE user_id=%s",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_primary=TRUE WHERE id=%s AND user_id=%s",
                (loc_id, user["id"])
            )
        else:
            # SQLite
            cursor.execute(
                "UPDATE locations SET is_primary=0 WHERE user_id=?",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_primary=1 WHERE id=? AND user_id=?",
                (loc_id, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Primary location updated.", "success")
    except Exception as e:
        print(f"Primary location error: {e}")
        flash("Failed to update primary location.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/favourite_location/<int:loc_id>", methods=["POST"])
@login_required
def favourite_location(loc_id):
    user = current_user()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if IS_PRODUCTION:
            # PostgreSQL
            cursor.execute(
                "UPDATE locations SET is_favourite=FALSE WHERE user_id=%s",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_favourite=TRUE WHERE id=%s AND user_id=%s",
                (loc_id, user["id"])
            )
        else:
            # SQLite
            cursor.execute(
                "UPDATE locations SET is_favourite=0 WHERE user_id=?",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_favourite=1 WHERE id=? AND user_id=?",
                (loc_id, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        flash("Default location updated.", "success")
    except Exception as e:
        print(f"Favourite location error: {e}")
        flash("Failed to update default location.", "error")
        cursor.close()
        conn.close()
    
    return redirect(url_for("auth.settings"))