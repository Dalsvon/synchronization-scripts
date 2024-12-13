Sync Manager - Municipality of Ořechov
This is a web application that manages synchronization scripts for the Municipality of Ořechov. 
It provides a web interface for managing and scheduling various synchronization tasks between different systems (mobile app, citizen portal, etc.).

Prerequisites
- Debian based Linux distribution
- Python 3.8 or higher
- Apache2, Nginx or another web server
- System packages for PostgreSQL and Python development

Installation Steps
 1. Install required system packages:
   sudo apt-get update
   sudo apt-get install postgresql-server-dev-all python3-dev python3.8-venv

 2. Create and activate virtual environment:
    python3.8 -m venv venv
    source venv/bin/activate

 3.Upgrade pip and install dependencies:
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt

 4.Create .env file in the project root with the following variables:
    FLASK_SECRET_KEY=your_secret_key_here
    ADMIN_USERNAME=your_admin_username
    ADMIN_PASSWORD=your_admin_password

 5. Set up your web server configuration with use of wsgi modules

Permissions
The application looks for synchronization scripts based on the configuration in scripts_config.json.
Ensure all scripts are placed in their respective folders as defined in the configuration.

Permissions
Set proper permissions for your web server to access this app (example for Nginx and Apache2):
sudo chown -R www-data:www-data /path/to/project
sudo chmod -R 750 /path/to/project

Troubleshooting
Check logs at:
/var/log/sync_manager/sync_app.log for application logs
Apache2 or Nginx error logs for server issues
Individual script logs in their respective directories
