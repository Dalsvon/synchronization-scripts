import sys
import os

# Get application directory
app_dir = os.path.dirname(os.path.abspath(__file__))

# Add application directory to Python path
sys.path.insert(0, app_dir)

# Add virtual environment site-packages to Python path
venv_site_packages = os.path.join(app_dir, 'venv', 'lib', 'python3.8', 'site-packages')
sys.path.insert(0, venv_site_packages)

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(app_dir, '.env')
    load_dotenv(env_path)
except ImportError:
    if os.path.exists(os.path.join(app_dir, '.env')):
        with open(os.path.join(app_dir, '.env')) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value.strip("'").strip('"')

# Import the Flask application
from app import app as application

# Only run the development server if this file is run directly
if __name__ == "__main__":
    application.run()