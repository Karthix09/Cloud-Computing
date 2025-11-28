# auth.py - FIXED for bcrypt issues
import os
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import bcrypt  # Use bcrypt directly instead of passlib
import traceback

# Import from database.py
from database import get_db_connection, IS_PRODUCTION

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")

# ---- Password hashing helpers ----
def hash_password(password):
    """Hash a password using bcrypt"""
    # Truncate to 72 bytes (bcrypt limit)
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')

def verify_password(password, hashed):
    """Verify a password against a hash"""
    password_bytes = password.encode('utf-8')[:72]
    return bcrypt.checkpw(password_bytes, hashed.encode('utf-8'))

# ---- helpers ----
def current_user():
    """Get current logged-in user"""
    uid = session.get("user_id")
    if not uid:
        return None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute("SELECT * FROM users WHERE id=%s", (uid,))
        else:
            cursor.execute("SELECT * FROM users WHERE id=?", (uid,))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    except Exception as e:
        print(f"❌ Error fetching current user: {e}")
        return None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login to access this page.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


# ---- routes ----
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    
    try:
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Please enter both username and password.", "error")
            return render_template("login.html"), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        else:
            cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            flash("Invalid username or password.", "error")
            return render_template("login.html"), 401
        
        if not verify_password(password, row["password_hash"]):
            flash("Invalid username or password.", "error")
            return render_template("login.html"), 401
        
        # Set session
        session["user_id"] = row["id"]
        session["username"] = row["username"]
        
        flash(f"Welcome back, {username}!", "success")
        return redirect("/traffic")
        
    except Exception as e:
        print(f"❌ Login error: {e}")
        traceback.print_exc()
        flash("An error occurred during login. Please try again.", "error")
        return render_template("login.html"), 500


@auth_bp.route("/logout")
def logout():
    username = session.get("username", "User")
    session.clear()
    flash(f"Goodbye, {username}!", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    
    try:
        # Get form data
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        dob = request.form.get("date_of_birth", "")
        
        # Validation
        if not username:
            flash("Username is required.", "error")
            return render_template("register.html"), 400
        
        if not email:
            flash("Email is required.", "error")
            return render_template("register.html"), 400
        
        if not password:
            flash("Password is required.", "error")
            return render_template("register.html"), 400
        
        if not confirm_password:
            flash("Please confirm your password.", "error")
            return render_template("register.html"), 400
        
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html"), 400
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("register.html"), 400
        
        if len(password) > 72:
            flash("Password cannot be longer than 72 characters.", "error")
            return render_template("register.html"), 400
        
        # Database operations
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user exists
        if IS_PRODUCTION:
            cursor.execute(
                "SELECT 1 FROM users WHERE username=%s OR email=%s",
                (username, email)
            )
        else:
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
        
        # Hash password
        password_hash = hash_password(password)
        
        # Insert new user
        if IS_PRODUCTION:
            cursor.execute(
                """INSERT INTO users (username, email, phone, password_hash, date_of_birth, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (username, email, phone or None, password_hash, dob or None, datetime.utcnow())
            )
        else:
            cursor.execute(
                """INSERT INTO users (username, email, phone, password_hash, date_of_birth, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (username, email, phone or None, password_hash, dob or None, datetime.utcnow().isoformat())
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("auth.login"))
        
    except Exception as e:
        print(f"❌ Registration error: {e}")
        traceback.print_exc()
        flash("Registration failed. Please try again.", "error")
        return render_template("register.html"), 500


@auth_bp.route("/settings")
@login_required
def settings():
    user = current_user()
    if not user:
        flash("Session expired. Please login again.", "error")
        return redirect(url_for("auth.login"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                """SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                   FROM locations WHERE user_id=%s
                   ORDER BY is_primary DESC, id DESC""",
                (user["id"],)
            )
        else:
            cursor.execute(
                """SELECT id, label, latitude, longitude, address, postal_code, is_favourite
                   FROM locations WHERE user_id=?
                   ORDER BY is_primary DESC, id DESC""",
                (user["id"],)
            )
        
        locs = cursor.fetchall()
        cursor.close()
        conn.close()

        # NEW: read key from environment
        import os
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

        return render_template(
            "settings.html",
            user=user,
            locations=locs,
            google_maps_api_key=google_maps_api_key,
        )
    except Exception as e:
        print(f"❌ Settings error: {e}")
        traceback.print_exc()
        flash("Error loading settings.", "error")
        return redirect("/traffic")


@auth_bp.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        cur_pw = request.form.get("current_password", "")
        
        if not verify_password(cur_pw, user["password_hash"]):
            flash("Current password incorrect.", "error")
            return redirect(url_for("auth.settings"))
        
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        new_pw = request.form.get("new_password", "")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            if new_pw:
                cursor.execute(
                    "UPDATE users SET email=%s, phone=%s, password_hash=%s WHERE id=%s",
                    (email, phone, hash_password(new_pw), user["id"])
                )
            else:
                cursor.execute(
                    "UPDATE users SET email=%s, phone=%s WHERE id=%s",
                    (email, phone, user["id"])
                )
        else:
            if new_pw:
                cursor.execute(
                    "UPDATE users SET email=?, phone=?, password_hash=? WHERE id=?",
                    (email, phone, hash_password(new_pw), user["id"])
                )
            else:
                cursor.execute(
                    "UPDATE users SET email=?, phone=? WHERE id=?",
                    (email, phone, user["id"])
                )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Profile updated successfully.", "success")
    except Exception as e:
        print(f"❌ Update profile error: {e}")
        traceback.print_exc()
        flash("Profile update failed.", "error")
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/add_location", methods=["POST"])
@login_required
def add_location():
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        label = request.form.get("label", "").strip()
        lat = request.form.get("latitude")
        lon = request.form.get("longitude")
        address = request.form.get("address", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        
        if not label:
            flash("Location label is required.", "error")
            return redirect(url_for("auth.settings"))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                """INSERT INTO locations (user_id, label, latitude, longitude, address, postal_code, is_favourite)
                   VALUES (%s, %s, %s, %s, %s, %s, FALSE)""",
                (user["id"], label, lat, lon, address, postal_code)
            )
        else:
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
        print(f"❌ Add location error: {e}")
        traceback.print_exc()
        flash("Failed to add location.", "error")
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/delete_location/<int:loc_id>", methods=["POST"])
@login_required
def delete_location(loc_id):
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                "DELETE FROM locations WHERE id=%s AND user_id=%s",
                (loc_id, user["id"])
            )
        else:
            cursor.execute(
                "DELETE FROM locations WHERE id=? AND user_id=?",
                (loc_id, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Location deleted.", "success")
    except Exception as e:
        print(f"❌ Delete location error: {e}")
        traceback.print_exc()
        flash("Failed to delete location.", "error")
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/delete_locations", methods=["POST"])
@login_required
def delete_locations():
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        ids = request.form.getlist("delete_ids")
        
        if not ids:
            return redirect(url_for("auth.settings"))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                "DELETE FROM locations WHERE id = ANY(%s) AND user_id=%s",
                (ids, user["id"])
            )
        else:
            qmarks = ",".join("?" for _ in ids)
            cursor.execute(
                f"DELETE FROM locations WHERE id IN ({qmarks}) AND user_id=?",
                (*ids, user["id"])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f"{len(ids)} location(s) deleted.", "success")
    except Exception as e:
        print(f"❌ Delete locations error: {e}")
        traceback.print_exc()
        flash("Failed to delete locations.", "error")
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/primary_location/<int:loc_id>", methods=["POST"])
@login_required
def primary_location(loc_id):
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                "UPDATE locations SET is_primary=FALSE WHERE user_id=%s",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_primary=TRUE WHERE id=%s AND user_id=%s",
                (loc_id, user["id"])
            )
        else:
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
        print(f"❌ Primary location error: {e}")
        traceback.print_exc()
        flash("Failed to update primary location.", "error")
    
    return redirect(url_for("auth.settings"))


@auth_bp.route("/favourite_location/<int:loc_id>", methods=["POST"])
@login_required
def favourite_location(loc_id):
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute(
                "UPDATE locations SET is_favourite=FALSE WHERE user_id=%s",
                (user["id"],)
            )
            cursor.execute(
                "UPDATE locations SET is_favourite=TRUE WHERE id=%s AND user_id=%s",
                (loc_id, user["id"])
            )
        else:
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
        print(f"❌ Favourite location error: {e}")
        traceback.print_exc()
        flash("Failed to update default location.", "error")
    
    return redirect(url_for("auth.settings"))