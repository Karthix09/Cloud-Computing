# 🚀 Smart Transport Intelligence Hub (STIH)

A cloud-based Singapore transport analytics platform that combines **real-time bus arrivals**, **traffic incidents**, **historical delay analytics**, and an **AI-powered assistant** into a single web application.

---

## 🌟 Key Features

- 🚌 **Real-time Bus Arrivals**  
  Live bus timings from **LTA DataMall**, displayed on an interactive Singapore map.

- 🚧 **Traffic Monitoring**  
  Current traffic incidents visualised on a map and summarised in charts.

- 📊 **Bus Delay Analytics**  
  Historical bus arrival snapshots aggregated with **Spark on AWS EMR** into datasets such as:
  - Average ETA by hour  
  - Median ETA by service  
  - Drift / volatility metrics and Top-10 “worst” services  

- 🤖 **AI Assistant (Chatbot)**  
  AWS Lex–backed chatbot that can:
  - Check bus arrivals at a stop  
  - Find nearby bus stops based on a location  
  - Use your saved locations in natural language queries  
  (A prototype route-planning flow is included and may be extended in future work.)

- 👤 **User Accounts & Personalisation**  
  Login / registration, saved locations (e.g. “Home”, “School”) and favourite bus stops for quick access.

---

## 🧱 Tech Stack

- **Backend**
  - Python 3.10+  
  - Flask (web framework)  
  - Gunicorn (production WSGI server)  
  - SQLite (development & bus data cache)  
  - PostgreSQL on Amazon RDS (production user data)

- **Frontend**
  - HTML5, CSS3, JavaScript  
  - Leaflet.js + MarkerCluster for interactive maps  
  - Leaflet Routing Machine + OSRM for bus route visualisation  
  - Chart.js / Plotly for analytics and traffic visualisations  

- **Cloud & Data**
  - Amazon EC2, Application Load Balancer, VPC, Security Groups  
  - Amazon RDS (PostgreSQL)  
  - Amazon EMR + Spark for batch analytics  
  - Amazon S3 for raw and processed datasets  
  - Amazon CloudWatch for logs and metrics  
  - Amazon Lex V2 for the chatbot  
  - External APIs: LTA DataMall, OneMap, OpenStreetMap tiles  

---

## 📂 Project Structure

```text
Cloud-Computing/
├── app.py               # Main Flask application (dashboards, APIs)
├── auth.py              # Authentication (login, register, bcrypt)
├── chatbot.py           # Chatbot blueprint + Lex integration
├── charts.py            # Analytics dashboard blueprint
├── config.py            # App configuration (dev/production)
├── data_collector.py    # Standalone bus-arrivals collector (optional)
├── database.py          # DB abstraction (SQLite vs PostgreSQL + schema)
├── gunicorn_config.py   # Gunicorn production config
├── M2-bigdata/          # Spark notebooks and EMR analytics scripts
├── templates/           # Jinja2 templates (bus, traffic, charts, chatbot, auth)
├── static/              # CSS, JS, images, and pre-computed CSV datasets
├── requirements.txt     # Python dependencies
└── wsgi.py              # WSGI entrypoint for Gunicorn / ALB
````

---

## 🛠️ Local Development

### 1. Clone the repository

```bash
git clone https://github.com/Karthix09/Cloud-Computing.git
cd Cloud-Computing
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file (or update the existing one) with values for:

* `API_KEY` – LTA DataMall API key
* `BASE_URL`, `TRAFFIC_API_URL` – LTA endpoints
* `SECRET_KEY` – Flask secret key

For production with PostgreSQL on RDS, also set:

* `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

For the chatbot (if used):

* `LEX_BOT_ID`
* `LEX_BOT_ALIAS_ID`
* `LEX_LOCALE_ID`
* `AWS_REGION`

For local development you can run entirely on SQLite; RDS is only needed for a full cloud deployment.

### 5. Initialise databases

```bash
python -c "from database import init_users_db, init_bus_db; init_users_db(); init_bus_db()"
```

This creates the required tables in the local SQLite databases.

### 6. Run the application (development)

```bash
# Windows
set FLASK_ENV=development

# macOS / Linux
export FLASK_ENV=development

python app.py
# or
flask run
```

By default the app listens on `http://127.0.0.1:5000/`.

---

## ☁️ Production Deployment (AWS Overview)

A typical production deployment uses:

* **EC2** instances running the Flask app via Gunicorn
* An **Application Load Balancer (ALB)** in front of EC2
* **RDS PostgreSQL** for user-related data
* **S3** for raw and processed bus-arrival datasets
* **EMR** for Spark-based analytics
* **Lex V2** for chatbot intents and fulfilment
* **CloudWatch** for logs and metrics

See the project report or Appendix A (if applicable) for full architecture diagrams and cost breakdown.

---

## 📜 License

This project is currently for academic purposes (INF2006 Cloud Computing & Big Data, Singapore Institute of Technology).
If you plan to publish or open-source it, add a proper license (e.g. MIT) here.

---

## 🙏 Acknowledgements

* **LTA DataMall** – public transport data
* **OpenStreetMap** & OSRM – mapping and routing
* **OneMap** – Singapore geocoding and mapping
* **AWS** – cloud infrastructure for compute, storage and analytics
