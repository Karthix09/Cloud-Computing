# 🚀 Transport Analytics Application

A comprehensive Singapore transport analytics platform providing real-time bus arrivals, traffic incidents, and intelligent route planning.

## Features

- 🚌 **Real-time Bus Arrivals**: Live bus timing from LTA DataMall
- 🚧 **Traffic Monitoring**: Current traffic incidents across Singapore
- 🤖 **AI Chatbot**: Intelligent bus timing assistant
- 📊 **Analytics**: Historical bus delay patterns
- 👤 **User Profiles**: Save favorite locations and bus stops

## Tech Stack

- **Backend**: Flask (Python 3.10+)
- **Database**: PostgreSQL (Production), SQLite (Development)
- **Frontend**: HTML, CSS, JavaScript
- **APIs**: LTA DataMall, Google Maps
- **Deployment**: AWS (EC2, RDS, ALB, Auto Scaling)

## Local Development Setup

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Installation

1. **Clone the repository**
```bash
   git clone <your-repo-url>
   cd PROJECTV1
```

2. **Create virtual environment**
```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
   pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
```

5. **Initialize database**
```bash
   python database.py
```

6. **Run the application**
```bash
   python app.py
```

7. **Access the application**
   - Open browser: `http://localhost:5000`
   - Default account: Register a new user

## Production Deployment (AWS)

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed AWS deployment instructions.

### Quick Deploy Steps

1. Set up RDS PostgreSQL database
2. Launch EC2 instance(s)
3. Configure Application Load Balancer
4. Set up Auto Scaling Group
5. Configure environment variables
6. Deploy application code

## Project Structure
```
PROJECTV1/
├── app.py                  # Main Flask application
├── auth.py                 # Authentication module
├── chatbot.py              # Chatbot functionality
├── database.py             # Database connections
├── config.py               # Configuration management
├── wsgi.py                 # WSGI entry point
├── requirements.txt        # Python dependencies
├── static/                 # CSS, JS, images
├── templates/              # HTML templates
└── database/               # Local database files
```

## Environment Variables

Required environment variables:

- `SECRET_KEY`: Flask secret key
- `API_KEY`: LTA DataMall API key
- `DB_HOST`: Database host (RDS endpoint for production)
- `DB_PASSWORD`: Database password

## API Endpoints

### Bus Module
- `GET /bus` - Bus dashboard
- `GET /bus_stops` - Search bus stops
- `GET /bus_arrivals/<code>` - Get bus arrivals

### Traffic Module
- `GET /traffic` - Traffic dashboard
- `GET /traffic_pie_chart` - Traffic analytics

### Authentication
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## License

This project is licensed under the MIT License.

## Contact

Project Link: [https://github.com/your-username/transport-analytics](https://github.com/your-username/transport-analytics)

## Acknowledgments

- LTA DataMall for public transport data
- Google Maps Platform
- AWS for cloud infrastructure