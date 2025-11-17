"""
WSGI entry point for Gunicorn
"""
import os
from app import app

# Load environment
if os.getenv('FLASK_ENV') == 'production':
    app.config.from_object('config.ProductionConfig')
else:
    app.config.from_object('config.DevelopmentConfig')

if __name__ == "__main__":
    app.run()