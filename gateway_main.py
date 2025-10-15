
## Fast API entry point 

# gateway_main.py
import os, sqlite3
from datetime import datetime
from passlib.hash import bcrypt
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from starlette.middleware.wsgi import WSGIMiddleware

# --- import your existing Flask apps ---
from bus_app import app as bus_flask_app
from traffic_accident import app as traffic_flask_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB = os.path.join(BASE_DIR, "users.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-.env")

# --------- helpers ----------
def get_db():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE,
          email TEXT UNIQUE,
          phone TEXT,
          date_of_birth TEXT,
          password_hash TEXT NOT NULL,
          created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS locations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          label TEXT NOT NULL,
          address TEXT,
          postal_code TEXT,
          latitude REAL,
          longitude REAL,
          is_favourite INTEGER DEFAULT 0,
          FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """)
        conn.commit()

def current_user(request: Request) -> Optional[sqlite3.Row]:
    uid = request.session.get("user_id")
    if not uid:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return row

# --------- FastAPI app ----------
app = FastAPI(title="Analytics Hub – Gateway")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Static & templates (for auth pages and shared assets)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Make user available to templates
@app.middleware("http")
async def inject_user(request: Request, call_next):
    request.state.user = current_user(request)
    response = await call_next(request)
    return response

def require_login(request: Request) -> Optional[RedirectResponse]:
    """Call this dependency on routes you want protected."""
    if not current_user(request):
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    return None

# ---------- Auth routes ----------
@app.get("/login", response_class=HTMLResponse)
def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def post_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not bcrypt.verify(password, row["password_hash"]):
        # Re-render with an error message (if your template expects it)
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid username or password."}, status_code=401
        )
    request.session["user_id"] = row["id"]
    request.session["username"] = row["username"]
    return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)

@app.get("/register", response_class=HTMLResponse)
def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def post_register(
    request: Request,
    username: str       = Form(...),
    email: str          = Form(...),
    phone: str          = Form(""),
    date_of_birth: str  = Form(""),
    password: str       = Form(...)
):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username=? OR email=?", (username, email)
        ).fetchone()
        if exists:
            return templates.TemplateResponse(
                "register.html", {"request": request, "error": "Username or email already exists."}, status_code=400
            )
        conn.execute(
            """INSERT INTO users(username,email,phone,date_of_birth,password_hash,created_at)
               VALUES(?,?,?,?,?,?)""",
            (username, email, phone, date_of_birth, bcrypt.hash(password), datetime.utcnow().isoformat())
        )
        conn.commit()
    return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, redirect: Optional[RedirectResponse] = Depends(require_login)):
    if isinstance(redirect, RedirectResponse):  # not authenticated
        return redirect
    user = current_user(request)
    with get_db() as conn:
        locs = conn.execute(
            """SELECT id,label,address,postal_code,latitude,longitude,is_favourite
               FROM locations WHERE user_id=?
               ORDER BY is_favourite DESC, id DESC""",
            (user["id"],)
        ).fetchall()
    return templates.TemplateResponse("settings.html", {"request": request, "user": user, "locations": locs})

@app.post("/update_profile")
def update_profile(
    request: Request,
    current_password: str = Form(...),
    email: str            = Form(""),
    phone: str            = Form(""),
    new_password: str     = Form("")
):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    if not bcrypt.verify(current_password, user["password_hash"]):
        return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

    with get_db() as conn:
        if new_password:
            conn.execute("UPDATE users SET email=?, phone=?, password_hash=? WHERE id=?",
                         (email, phone, bcrypt.hash(new_password), user["id"]))
        else:
            conn.execute("UPDATE users SET email=?, phone=? WHERE id=?", (email, phone, user["id"]))
        conn.commit()
    return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

@app.post("/add_location")
def add_location(
    request: Request,
    label: str        = Form(...),
    address: str      = Form(None),
    postal_code: str  = Form(None),
    latitude: float   = Form(None),
    longitude: float  = Form(None),
):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    with get_db() as conn:
        conn.execute("""INSERT INTO locations (user_id,label,address,postal_code,latitude,longitude,is_favourite)
                        VALUES (?,?,?,?,?,?,0)""",
                     (user["id"], label, address, postal_code, latitude, longitude))
        conn.commit()
    return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

@app.post("/delete_location/{loc_id}")
def delete_location(request: Request, loc_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    with get_db() as conn:
        conn.execute("DELETE FROM locations WHERE id=? AND user_id=? AND is_favourite=0", (loc_id, user["id"]))
        conn.commit()
    return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

@app.post("/favourite_location/{loc_id}")
def favourite_location(request: Request, loc_id: int):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)
    with get_db() as conn:
        conn.execute("UPDATE locations SET is_favourite=0 WHERE user_id=?", (user["id"],))
        conn.execute("UPDATE locations SET is_favourite=1 WHERE id=? AND user_id=?", (loc_id, user["id"]))
        conn.commit()
    return RedirectResponse(url="/settings", status_code=HTTP_302_FOUND)

# ---------- Mount the Flask dashboards ----------
# IMPORTANT: your Flask templates must use relative paths (no leading "/")
app.mount("/bus",     WSGIMiddleware(bus_flask_app))
app.mount("/traffic", WSGIMiddleware(traffic_flask_app))

# ---------- Home: send users somewhere sensible ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # If logged in, you can redirect to /bus or /traffic
    return RedirectResponse(url="/bus", status_code=HTTP_302_FOUND)

# init DB on import
ensure_schema()