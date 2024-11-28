sudo apt-get install postgresql-server-dev-all python3-dev

python3.8 -m venv venv
source venv/bin/activate

# Upgrade pip and setuptools first
pip install --upgrade pip setuptools wheel

# Install the rest
pip install -r requirements.txt

gunicorn --bind 0.0.0.0:3003 --workers 3 wsgi:application