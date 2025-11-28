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
* `GOOGLE_MAPS_API_KEY` – Google Maps JavaScript + Places API key (used on the Settings page for address autocomplete)

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

### Google Maps API key (Settings page)

The **User Settings** page uses the Google Maps JavaScript API + Places Autocomplete to let users search for an address/postal code and save the corresponding latitude/longitude, full address and postal code.

To use this feature:

1. In the **Google Cloud Console**, create an API key.
2. Enable the following APIs for the project:
   - **Maps JavaScript API**
   - **Places API**
3. Under **API key restrictions**:
   - Set **Application restrictions** to **HTTP referrers (web sites)**.
   - Add at least these referrers for local development:
     - `http://localhost:5000/*`
     - `http://127.0.0.1:5000/*`
4. Set the key in your environment (for example in `.env`):

   ```env
   GOOGLE_MAPS_API_KEY=YOUR_ACTUAL_KEY_HERE

## ☁️ Production Deployment (AWS Overview)

The application is deployed on AWS using a highly available, scalable cloud architecture:

### Core Infrastructure

#### **Amazon EC2** - Application Hosting
* **Instance Type**: t2.micro (1 vCPU, 1GB RAM)
* **AMI**: Amazon Linux 2023
* **Storage**: 8GB gp3 EBS volume
* **Configuration Steps**:
  1. Launched instance in public subnet with auto-assign public IP
  2. Connected via SSH: `ssh -i your-key.pem ec2-user@<public-ip>`
  3. Updated system: `sudo yum update -y`
  4. Installed Python 3.11: `sudo yum install python3.11 -y`
  5. Installed PostgreSQL client: `sudo yum install postgresql15 -y`
  6. Created application directory: `sudo mkdir -p /var/www/transport-app`
  7. Cloned repository and set up virtual environment
  8. Installed dependencies: `pip install -r requirements.txt`
  9. Created `.env` file with database credentials and API keys
  10. Configured systemd service for automatic startup:
```ini
      [Unit]
      Description=Transport Buddy Flask Application
      After=network.target

      [Service]
      User=ec2-user
      WorkingDirectory=/var/www/transport-app
      ExecStart=/var/www/transport-app/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 app:app
      Restart=always

      [Install]
      WantedBy=multi-user.target
```
  11. Started service: `sudo systemctl enable transport-app && sudo systemctl start transport-app`
  12. Created custom AMI for Auto Scaling Group

#### **Application Load Balancer (ALB)** - Traffic Distribution
* **Type**: Internet-facing Application Load Balancer
* **Subnets**: Deployed across 2 availability zones (us-east-1a, us-east-1b)
* **Listener**: HTTP on port 80
* **Configuration**:
  1. Created Target Group with protocol HTTP:8000
  2. Configured health check path: `/health`
  3. Set health check interval: 30 seconds, timeout: 5 seconds
  4. Enabled sticky sessions (24 hours) for session persistence
  5. Attached Target Group to ALB listener

#### **Auto Scaling Group** - Dynamic Scaling
* **Capacity**: Min 2, Desired 2, Max 4 instances
* **Scaling Policy**: Target tracking based on CPU utilization (70% target)
* **Configuration**:
  1. Created Launch Template from custom AMI
  2. Selected VPC and both public subnets
  3. Attached to ALB Target Group
  4. Enabled ELB health checks with 300 second grace period
  5. Set up user data script to auto-start application on boot

#### **Amazon RDS PostgreSQL** - Managed Database
* **Engine**: PostgreSQL (latest stable version)
* **Instance Class**: db.t3.micro
* **Storage**: 20GB General Purpose SSD (gp3)
* **Configuration**:
  1. Created in private subnet group for security
  2. Disabled public accessibility
  3. Set master username and strong password
  4. Enabled automated backups (7-day retention)
  5. Configured security group to allow port 5432 from EC2 security group only
  6. Database tables auto-created on first application launch

#### **Amazon VPC** - Network Isolation
* **CIDR Block**: 10.0.0.0/16
* **Configuration**:
  1. Created 2 public subnets: 10.0.1.0/24 (us-east-1a), 10.0.2.0/24 (us-east-1b)
  2. Created 2 private subnets for RDS: 10.0.3.0/24, 10.0.4.0/24
  3. Attached Internet Gateway to VPC
  4. Updated route tables: public subnets route 0.0.0.0/0 to IGW

### AI & Serverless Components

#### **Amazon Lex V2** - Conversational Chatbot
* **Bot Name**: TransportBuddyChatbot
* **Locale**: English (US)
* **Configuration**:
  1. Created 4 intents: SearchBusStopIntent, GetBusArrivalsIntent, FindRouteIntent, HDBResalePredictionIntent
  2. Defined sample utterances and slot types for each intent
  3. Configured fulfillment to use Lambda function
  4. Built and published bot to TestBotAlias
  5. Integrated bot ID into web application frontend

#### **AWS Lambda** - Serverless Fulfillment
* **Function Name**: TransportBuddyLexFulfillment
* **Runtime**: Python 3.11
* **Memory**: 128MB, Timeout: 30 seconds
* **Configuration**:
  1. Created function with basic execution role
  2. Uploaded code to handle Lex intent fulfillment
  3. Added environment variables for database and API access
  4. Configured VPC settings to access RDS (if needed)
  5. Granted Lex permissions to invoke Lambda function

### Monitoring & Storage

#### **Amazon CloudWatch** - Monitoring & Logging
* **Configuration**:
  1. Created custom dashboard: transport-buddy-dashboard
  2. Added widgets for ALB requests, EC2 CPU, healthy hosts, RDS connections
  3. Set up 3 alarms:
     - High CPU (>80% for 5 minutes) → SNS notification
     - Unhealthy targets (>0 for 1 minute) → SNS notification
     - 5XX errors (>10 in 5 minutes) → SNS notification
  4. Enabled detailed monitoring for EC2 instances
  5. Configured log groups for application logs

#### **Amazon SNS** - Alert Notifications
* **Topic Name**: transport-buddy-alerts
* **Configuration**:
  1. Created SNS topic for CloudWatch alarms
  2. Added email subscription for notifications
  3. Confirmed subscription via email link

#### **Amazon S3** - Backup Storage
* **Bucket Name**: transport-buddy-exports
* **Configuration**:
  1. Created bucket with default encryption enabled
  2. Configured bucket policy for EC2 access via IAM role
  3. Enabled versioning for backup retention
  4. Used for application file exports and backups

### Security & Access

#### **Security Groups** - Network Firewall
* **ALB Security Group (transport-buddy-alb-sg)**:
  - Inbound: HTTP (80) from 0.0.0.0/0, HTTPS (443) from 0.0.0.0/0
  - Outbound: All traffic
  
* **EC2 Security Group**:
  - Inbound: Port 8000 from ALB-SG, SSH (22) from your IP
  - Outbound: All traffic
  
* **RDS Security Group (transport-db-sg)**:
  - Inbound: PostgreSQL (5432) from EC2-SG only
  - Outbound: None required

* **Lambda Security Group**:
  - Inbound: None
  - Outbound: HTTPS (443) to external APIs

#### **IAM Roles** - Secure Access
* **EC2-S3-Access Role**:
  1. Created IAM role for EC2 service
  2. Attached policies: AmazonS3FullAccess, CloudWatchAgentServerPolicy
  3. Assigned role to EC2 instances for S3 and CloudWatch access without hardcoded credentials

#### **Network Isolation**
* Database deployed in private subnets with no internet access
* Application in public subnets with controlled access via security groups
* All inter-service communication through private IPs within VPC

### Deployment Features

#### **Custom AMI** - Reusable Image
* **Name**: transport-buddy-v1
* **Configuration**:
  1. Configured initial EC2 instance with all dependencies
  2. Stopped transport-app service temporarily
  3. Created AMI from Actions → Image and templates → Create image
  4. Used AMI in Launch Template for consistent deployments

#### **Launch Template** - Instance Configuration
* **Name**: transport-buddy-lt
* **Configuration**:
  1. Selected custom AMI (transport-buddy-v1)
  2. Set instance type: t2.micro
  3. Attached EC2 security group
  4. Added IAM instance profile: EC2-S3-Access
  5. Included user data script:
```bash
     #!/bin/bash
     systemctl start transport-app
     systemctl enable transport-app
```

#### **Target Group** - Health-based Routing
* **Name**: transport-buddy-tg
* **Configuration**:
  1. Protocol: HTTP, Port: 8000
  2. Health check path: `/health`
  3. Health check interval: 30s, timeout: 5s
  4. Healthy threshold: 2, unhealthy threshold: 3
  5. Enabled stickiness (load balancer cookie, 24-hour duration)
  6. Success codes: 200

#### **Multi-AZ Deployment** - High Availability
* Deployed across us-east-1a and us-east-1b availability zones
* Auto Scaling Group launches instances in both zones
* RDS configured with Multi-AZ option for automatic failover (optional)
* Load balancer distributes traffic across both zones

This architecture provides automatic scaling, load distribution, comprehensive monitoring, and follows AWS best practices for production-grade web applications with an estimated cost of ~$58-63/month.

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
