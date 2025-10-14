from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from passlib.hash import bcrypt
import datetime
from typing import Optional
from database import get_db_connection, init_db

# JWT Secret and Config
SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"

# FastAPI App Setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize DB
init_db()

# -------------------------------
# Helper Functions
# -------------------------------
def create_token(user_id: int):
    """Generate JWT token"""
    return jwt.encode(
        {"user_id": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=3)},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

def get_current_user(request: Request):
    """Return logged-in user from JWT cookie"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        return user
    except JWTError:
        return None

# -------------------------------
# ROUTES
# -------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse("/settings")
    return RedirectResponse("/login")

# ----------- REGISTER -----------
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register_user(
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    date_of_birth: str = Form(...)
):
    conn = get_db_connection()
    c = conn.cursor()
    hashed_pw = bcrypt.hash(password)
    try:
        c.execute(
            "INSERT INTO users (username, email, phone, password_hash, date_of_birth) VALUES (?, ?, ?, ?, ?)",
            (username, email, phone, hashed_pw, date_of_birth)
        )
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    conn.close()
    return RedirectResponse("/login", status_code=303)

# ----------- LOGIN / LOGOUT -----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_user(username: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not user or not bcrypt.verify(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token(user["id"])
    response = RedirectResponse("/settings", status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return response

@app.get("/logout")
def logout_user():
    response = RedirectResponse("/login")
    response.delete_cookie("access_token")
    return response

# ----------- SETTINGS PAGE -----------
@app.get("/settings", response_class=HTMLResponse)
def user_settings(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    conn = get_db_connection()
    locations = conn.execute("SELECT * FROM locations WHERE user_id=?", (user["id"],)).fetchall()
    conn.close()

    return templates.TemplateResponse("settings.html", {"request": request, "user": user, "locations": locations})

# ----------- UPDATE PROFILE -----------
@app.post("/update_profile")
def update_profile(
    request: Request,
    current_password: str = Form(...),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    # Verify password
    if not bcrypt.verify(current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect current password")

    conn = get_db_connection()
    c = conn.cursor()

    if email:
        c.execute("UPDATE users SET email=? WHERE id=?", (email, user["id"]))
    if phone:
        c.execute("UPDATE users SET phone=? WHERE id=?", (phone, user["id"]))
    if new_password:
        hashed_pw = bcrypt.hash(new_password)
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed_pw, user["id"]))

    conn.commit()
    conn.close()
    return RedirectResponse("/settings", status_code=303)

# ----------- ADD LOCATION -----------
@app.post("/add_location")
def add_location(
    request: Request,
    label: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(...),
    postal_code: str = Form(...)
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO locations (user_id, label, latitude, longitude, address, postal_code)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user["id"], label, latitude, longitude, address, postal_code)
    )
    conn.commit()
    conn.close()

    return RedirectResponse("/settings", status_code=303)

# ----------- SET FAVOURITE LOCATION -----------
@app.post("/favourite_location/{loc_id}")
def favourite_location(request: Request, loc_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    conn = get_db_connection()
    c = conn.cursor()

    # Reset all favourites first
    c.execute("UPDATE locations SET is_favourite=0 WHERE user_id=?", (user["id"],))
    # Set the chosen one
    c.execute("UPDATE locations SET is_favourite=1 WHERE id=? AND user_id=?", (loc_id, user["id"]))

    conn.commit()
    conn.close()

    return RedirectResponse("/settings", status_code=303)

# ----------- DELETE SINGLE LOCATION -----------
@app.post("/delete_location/{loc_id}")
def delete_location(request: Request, loc_id: int):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login")

    conn = get_db_connection()
    c = conn.cursor()
    # Ensure user owns the location and it's not the favourite one
    c.execute("DELETE FROM locations WHERE id=? AND user_id=? AND is_favourite=0", (loc_id, user["id"]))
    conn.commit()
    conn.close()
    return RedirectResponse("/settings", status_code=303)

# ----------- DELETE MULTIPLE LOCATIONS -----------
@app.post("/delete_locations")
def delete_multiple_locations(request: Request, delete_ids: Optional[list[int]] = Form(None)):
    user = get_current_user(request)
    if not user or not delete_ids:
        return RedirectResponse("/settings")

    conn = get_db_connection()
    c = conn.cursor()

    # Delete only non-favourite ones
    for loc_id in delete_ids:
        c.execute("DELETE FROM locations WHERE id=? AND user_id=? AND is_favourite=0", (loc_id, user["id"]))

    conn.commit()
    conn.close()
    return RedirectResponse("/settings", status_code=303)
