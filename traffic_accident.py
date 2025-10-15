import threading
import time
import re
from datetime import datetime
import os
import requests
import pandas as pd
import folium
from flask import Flask, render_template, request
from dotenv import load_dotenv
from sqlalchemy import create_engine, Table, Column, String, Float, MetaData, DateTime

# --- Load from .env ---
load_dotenv()
API_KEY = os.getenv("TRAFFIC_API_KEY") or os.getenv("API_KEY")
API_URL = os.getenv("TRAFFIC_API_URL", "https://datamall2.mytransport.sg/ltaodataservice/TrafficIncidents")
HEADERS = {"AccountKey": API_KEY, "accept": "application/json"}

# --- Flask app ---
app = Flask(__name__)

# --- Global state ---
last_update = ""

# --- SQLite setup ---
engine = create_engine("sqlite:///database/TrafficIncidents.db", future=True)
metadata = MetaData()
incidents_table = Table(
    "incidents", metadata,
    Column("Id", String, primary_key=True),
    Column("Type", String),
    Column("Latitude", Float),
    Column("Longitude", Float),
    Column("Message", String),
    Column("FetchedAt", DateTime)
)
metadata.create_all(engine)


# ---------- HELPERS ----------
def extract_road(msg: str) -> str:
    """Extract clean, likely road name (e.g., 'PIE', 'CTE', 'ECP', 'Bukit Timah Road')."""
    if pd.isna(msg) or not msg:
        return ""

    # 1️⃣ First, detect expressway short codes and return them in uppercase
    exp_match = re.search(r"\b(PIE|CTE|AYE|ECP|SLE|TPE|KPE|MCE|BKE)\b", msg, flags=re.IGNORECASE)
    if exp_match:
        return exp_match.group(1).upper()

    # 2️⃣ Otherwise, look for full road names
    road_match = re.search(
        r"([A-Z][a-z]+(?:\s(?:Road|Rd|Avenue|Ave|Street|St|Boulevard|Drive|Dr|Lane|Expressway|Exit|Entrance)))",
        msg,
        flags=re.IGNORECASE
    )
    if road_match:
        return road_match.group(1).strip().title()

    # 3️⃣ Fallback for anything else after 'on/at/along/near'
    m = re.search(r"(?:on|at|along|near)\s+([A-Z][^,.\-]*)", msg, flags=re.IGNORECASE)
    return m.group(1).strip().title() if m else ""


# ---------- BACKGROUND FETCH ----------
def fetch_and_store_loop(poll_seconds: int = 60):
    """Fetch latest incidents every 60 seconds."""
    global last_update
    while True:
        try:
            now = datetime.now()
            r = requests.get(API_URL, headers=HEADERS, timeout=20)
            r.raise_for_status()
            payload = r.json()
            incidents = payload.get("value", [])
            df = pd.DataFrame(incidents)

            if df.empty:
                print(f"ℹ️ No active incidents at {now}")
                time.sleep(poll_seconds)
                continue

            df["FetchedAt"] = now

            # Ensure unique IDs
            if "IncidentID" not in df.columns:
                df["IncidentID"] = df.apply(
                    lambda r: f"{r.get('Type','Unknown')}_{r.get('Latitude','')}_{r.get('Longitude','')}",
                    axis=1
                )

            new_records = []
            for _, row in df.iterrows():
                new_records.append({
                    "Id": str(row["IncidentID"]),
                    "Type": row.get("Type"),
                    "Latitude": row.get("Latitude"),
                    "Longitude": row.get("Longitude"),
                    "Message": row.get("Message"),
                    "FetchedAt": now
                })

            with engine.begin() as conn:
                # Replace existing incidents
                conn.execute(incidents_table.delete())
                conn.execute(incidents_table.insert(), new_records)

            last_update = now.strftime("%d %b %Y, %I:%M %p")
            print(f"✅ Updated {len(df)} active incidents at {last_update}")

        except Exception as e:
            print("❌ Fetch error:", e)

        time.sleep(poll_seconds)


# ---------- PIE CHART ----------
@app.route("/traffic_pie_chart")
def traffic_pie_chart():
    """Interactive pie chart showing traffic incidents by type."""
    import plotly.express as px
    import plotly.io as pio

    with engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM incidents", conn)

    if df.empty:
        return "<h3>No data available for pie chart yet.</h3>"

    # Extract area name
    def extract_area(msg):
        if not msg:
            return ""
        m = re.search(r"(?:on|at|along|near|before|after)\s+([^,().-]+)", msg, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    df["Area"] = df["Message"].apply(extract_area).fillna("Unknown")

    # Prepare data
    type_groups = df.groupby("Type")
    type_list, count_list, hover_texts = [], [], []

    for incident_type, group in type_groups:
        count = len(group)
        areas = sorted(set(group["Area"].dropna()) - {""})
        area_lines = "<br>".join(f"• {a}" for a in areas[:10])
        hover_text = (
            f"<b>{incident_type}</b><br>"
            f"Incidents: {count}<br>"
            f"<b>Areas involved:</b><br>{area_lines}"
        )
        type_list.append(incident_type)
        count_list.append(count)
        hover_texts.append(hover_text)

    fig = px.pie(
        names=type_list,
        values=count_list,
        title="Traffic Incidents by Type (Hover for Details)",
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    fig.update_traces(
        hoverinfo="text",
        hovertemplate="%{customdata}",
        textinfo="percent+label",
        customdata=hover_texts
    )
    fig.update_layout(width=800, height=450, showlegend=True)

    chart_html = pio.to_html(fig, full_html=False)

    return f"""
    <html>
    <head>
        <title>Traffic Pie Chart</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; background:#f4f6f9; text-align:center; padding:20px; }}
            .back {{ display:inline-block; margin-top:20px; background:#0078d7; color:white;
                     padding:10px 20px; border-radius:6px; text-decoration:none; font-weight:bold; }}
        </style>
    </head>
    <body>
        <h2>Traffic Incidents by Type</h2>
        <div style="display:flex; justify-content:center;">{chart_html}</div>
        <p>🕒 Last updated: {last_update}</p>
        <a href="/" class="back">⬅ Back to Dashboard</a>
    </body>
    </html>
    """


# ---------- MAP ----------
def build_map_from_df(df: pd.DataFrame) -> str:
    """Generate a folium map with all incidents."""
    sg_bounds = [[1.1304753, 103.6920359], [1.4504753, 104.0120359]]
    sg_map = folium.Map(location=[1.3521, 103.8198], zoom_start=12, control_scale=True)

    if not df.empty:
        for _, row in df.iterrows():
            lat, lon = row.get("Latitude"), row.get("Longitude")
            if pd.notna(lat) and pd.notna(lon):
                msg = row.get("Message") or "No description"
                type_info = row.get("Type") or "Incident"

                # Extract embedded time in brackets like (13/10)20:45
                match = re.search(r"\((\d{1,2}/\d{1,2})\)(\d{2}:\d{2})", msg)
                reported_time = f"({match.group(1)}) {match.group(2)}" if match else None

                # Remove that time part from the main message
                clean_msg = re.sub(r"\(\d{1,2}/\d{1,2}\)\d{2}:\d{2}", "", msg).strip()

                popup_html = f"""
                <div style='font-size:14px; width:260px; line-height:1.4;'>
                    <b>{type_info}</b><br>{clean_msg}
                    {f"<br>🕒 Reported at: {reported_time}" if reported_time else ""}
                </div>
                """

                folium.Marker(
                    [lat, lon],
                    popup=folium.Popup(popup_html, max_width=300, min_width=250),
                    icon=folium.Icon(color="red", icon="info-sign"),
                ).add_to(sg_map)

    sg_map.fit_bounds(sg_bounds)
    return sg_map._repr_html_()


# ---------- MAIN DASHBOARD ----------
@app.route("/", methods=["GET", "POST"])
def home():
    search_query = request.form.get("search", "").strip()
    selected_type = request.form.get("type", "").strip()
    selected_road = request.form.get("road", "").strip()
    clear_filter = request.form.get("clear")

    with engine.connect() as conn:
        df = pd.read_sql("SELECT * FROM incidents", conn)

    if not df.empty:
        df["RoadCategory"] = df["Message"].apply(extract_road)
    else:
        df["RoadCategory"] = ""

    road_options = sorted([r for r in df["RoadCategory"].dropna().unique() if r])
    type_options = sorted([t for t in df["Type"].dropna().unique() if t])

    if clear_filter:
        search_query = selected_type = selected_road = ""

    filtered = df.copy()
    if search_query:
        mask = filtered["Message"].str.contains(search_query, case=False, na=False) | \
               filtered["RoadCategory"].str.contains(search_query, case=False, na=False)
        filtered = filtered[mask]
    if selected_type:
        filtered = filtered[filtered["Type"] == selected_type]
    if selected_road:
        filtered = filtered[filtered["RoadCategory"] == selected_road]

    total_incidents = len(filtered)
    most_road = filtered["RoadCategory"].value_counts().idxmax() if not filtered.empty and not filtered["RoadCategory"].dropna().empty else "N/A"
    most_type = filtered["Type"].value_counts().idxmax() if not filtered.empty and not filtered["Type"].dropna().empty else "N/A"
    type_counts = filtered["Type"].value_counts().to_dict() if not filtered.empty else {}
    no_results = filtered.empty

    filtered_html = build_map_from_df(filtered)

    return render_template(
        "traffic_main.html",
        filtered_html=filtered_html,
        last_update=last_update,
        total_incidents=total_incidents,
        most_road=most_road,
        most_type=most_type,
        type_options=type_options,
        road_options=road_options,
        search_query=search_query,
        type_query=selected_type,
        road_query=selected_road,
        type_counts=type_counts,
        no_results=no_results
    )


# ---------- RUN ----------
if __name__ == "__main__":
    threading.Thread(target=fetch_and_store_loop, daemon=True).start()
    print("🌐 Serving http://localhost:5001 — fetching every 60s")
    app.run(debug=False, port=5001)
















