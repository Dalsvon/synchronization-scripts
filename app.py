from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, session
import os
import subprocess
from crontab import CronTab
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
import sys
from functools import wraps
from dotenv import load_dotenv, dotenv_values
from datetime import timedelta

@dataclass
class ScriptInfo:
    name: str
    subfolder: str
    display_name: str
    status: str = "Synchronizační skript nebyl nalezen"
    enabled: bool = False

class SyncManager:
    SCHEDULE_OPTIONS = {
        "Nikdy": "",
        "Každou hodinu": "0 * * * *",
        "Jednou denně": "0 0 * * *",
        "Jednou týdně": "0 0 * * 0",
        "Jednou měsíčně": "0 0 1 * *",
        "Jednou ročně": "0 0 1 1 *"
    }

    def __init__(self):
        self.logger = self._setup_logging()
        self.scripts_folder = str(Path(__file__).parent)
        
        self.config_folder = os.path.join(self.scripts_folder, 'config')
        os.makedirs(self.config_folder, exist_ok=True)
        self.config_file = os.path.join(self.config_folder, 'plan_config.json')
        self.scripts_config_file = Path(os.path.join(self.config_folder, 'scripts_config.json'))
        
        # Load scripts configuration
        self.SCRIPTS = self._load_scripts_config()
        
        if not os.path.exists(self.config_file):
            self.config = self._remove_old_cron_commands()
            self.save_config()
        else:
            self.config = self._load_plan_config()
    
    def _load_scripts_config(self) -> List[ScriptInfo]:
        # Loads script names, folders and files
        try:
            if not self.scripts_config_file.exists():
                self.logger.error(f"Konfigurační soubor skriptů nebyl nalezen: {self.scripts_config_file}")
                raise FileNotFoundError(f"Konfigurační soubor skriptů nebyl nalezen: {self.scripts_config_file}")
        
            # Explicitly specify UTF-8 encoding
            with open(self.scripts_config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            if not isinstance(config_data, dict) or 'scripts' not in config_data:
                raise ValueError("Neplatný formát konfiguračního souboru: chybí klíč 'scripts'")
                
            scripts = []
            for script_data in config_data['scripts']:
                required_fields = ['name', 'subfolder', 'display_name']
                if not all(field in script_data for field in required_fields):
                    missing_fields = [field for field in required_fields if field not in script_data]
                    raise ValueError(f"V konfiguraci skriptu chybí povinná pole: {', '.join(missing_fields)}")
                    
                scripts.append(ScriptInfo(
                    name=script_data['name'],
                    subfolder=script_data['subfolder'],
                    display_name=script_data['display_name']
                    ))
                
            return scripts
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse scripts configuration file: {e}")
            raise ValueError(f"Chyba načítaní skriptů. Nevalidní JSON soubor: {e}")
        except Exception as e:
            self.logger.error(f"Error loading scripts configuration: {e}")
            raise ValueError(f"Chyba načítaní skriptů: {e}")
        
    def _load_plan_config(self) -> dict:
        # Loads schedule plans for scripts
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise ValueError(f"Chyba při hledání konfigurace: {e}.")

    def _setup_logging(self) -> logging.Logger:
        # Sets up logging
        logger = logging.getLogger('sync_manager')
        logger.setLevel(logging.INFO)
        logger.handlers = []
        
        log_dir = '/var/log/sync_manager'
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'sync_app.log')
        
        handler = logging.StreamHandler()
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addHandler(file_handler)
        
        return logger
    
    def _remove_old_cron_commands(self) -> dict:
        # Creates a new config and resets cron jobs
        self.logger.info("Config file not found. Creating new configuration with no schedules")
        config = {}
        
        try:
            cron = CronTab(user=True)
            for script in self.SCRIPTS:
                script_path = os.path.abspath(os.path.join(
                    self.scripts_folder,
                    script.subfolder,
                    script.name
                ))
                self.logger.info(f"Checking for cron jobs with path: {script_path}")
                
                # Remove any existing jobs for this script
                for job in cron:
                    if script_path in str(job.command) and "sync_manager" in str(job.comment):
                        self.logger.info(f"Found matching job: {job.command}")
                        cron.remove(job)
                        self.logger.info(f"Removed existing cron job for {script.name}")
                
                config[f'schedule_{script.name}'] = ""
                self.logger.info(f"Setting no schedule for {script.name}")
            
            cron.write()
            self.logger.info("Created new config file with no schedules and cleared existing cron jobs")
            return config
            
        except Exception as e:
            self.logger.error(f"Error while creating initial config: {str(e)}")
            raise ValueError(f"Chyba inicializace konfigurace: {e}.")

    def save_config(self) -> None:
        # Saves new schedules for the scripts in config
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            raise ValueError(f"Chyba při ukádání konfigurace {e}.")

    def get_script_path(self, script: ScriptInfo) -> Tuple[str, bool]:
        # Returns absolute path to a script
        full_path = os.path.abspath(os.path.join(
            self.scripts_folder,
            script.subfolder,
            script.name
        ))
        exists = os.path.exists(full_path)
        return full_path, exists

    def validate_folder(self) -> Dict:
        # Validates if script foders and scripts themselves exist
        try:
            scripts_status = []
            missing_scripts = []
            
            
            for script in self.SCRIPTS:
                script_path, exists = self.get_script_path(script)
                status = "Synchronizační skript nalezen" if exists else "Synchronizační skript nebyl nalezen"
                enabled = exists
                
                scripts_status.append(
                    ScriptInfo(
                        name=script.name,
                        subfolder=script.subfolder,
                        display_name=script.display_name,
                        status=status,
                        enabled=enabled
                    )
                )
                
                if not exists:
                    missing_scripts.append(f"{script.name} (očekáváno v složce {script.subfolder})")
                    self.logger.error(f"Missing {script.name} in {script.subfolder}")
                    

            return {
                'valid': not missing_scripts,
                'message': ("Všechny skripty byly nalezeny" if not missing_scripts else 
                           f"Chybějící skripty:\n" + "\n".join(missing_scripts)),
                'scripts': scripts_status
            }
        
        except Exception as e:
            self.logger.error(f"Error during validation of folder: {e}")
            raise ValueError(f"Chyba při validaci složky.")

    def get_current_schedule(self, script_name: str) -> str:
        # Returns readable name for schedule of a script
        saved_cron = self.config.get(f'schedule_{script_name}', '')
        for name, expr in self.SCHEDULE_OPTIONS.items():
            if expr == saved_cron:
                return name
        return "Nikdy"

    def run_script(self, script_name: str) -> Dict:
        # Runs given script as subprocess
        script = next((s for s in self.SCRIPTS if s.name == script_name), None)
        if not script:
            self.logger.error(f"Script with name {script_name} does not exist")
            raise ValueError(f"Skript tohto jména nebyl nalezen: {script_name}.")

        script_path, exists = self.get_script_path(script)
        if not exists:
            self.logger.error(f"Script with name {script_name} couldn't be found")
            raise ValueError(f"Skript nebyl nalezen: {script_path}. Skuste skontrolovat existenci skriptů.")

        try:
            script_dir = os.path.dirname(script_path)

            env = os.environ.copy()
            env['PYTHONPATH'] = f"{script_dir}:{env.get('PYTHONPATH', '')}"
            
            venv_python = str(Path(self.scripts_folder) / 'venv' / 'bin' / 'python3')
            
            # Load .env file from script directory
            dotenv_path = os.path.join(script_dir, '.env')
            if os.path.exists(dotenv_path):
                env_vars = dotenv_values(dotenv_path)
                env.update(env_vars)
                
            for ssl_var in ['SSL_CERT_FILE', 'SSL_KEY_FILE', 'SSL_CA_FILE']:
                if ssl_var in os.environ:
                    ssl_path = Path(os.environ[ssl_var])
                    if not ssl_path.is_absolute():
                        env[ssl_var] = str(Path(script_dir) / os.environ[ssl_var])
                    else:
                        env[ssl_var] = str(ssl_path)
            
            process = subprocess.run(
                [f"{venv_python}", script_path],
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            
            # Truncates too long messages
            output = process.stdout[:200] + "..." if len(process.stdout) > 200 else process.stdout
            message = f"Synchronizace proběhla úspěšne: {script.display_name}."
                
            return {'success': True, 'message': message}
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Unknown error {e} durning the run of {script_name}")
            raise RuntimeError(f"Nastala neznámá chyba během provádění skriptu {script_name}.")
        
        except Exception as e:
            self.logger.error(f"Unknown error {e} durning the run of {script_name}")
            raise RuntimeError("Nastala neznámá chyba.")
        

    def save_schedule(self, script_name: str, schedule_name: str) -> Dict:
        # Saves cron schedule for a script
        if schedule_name not in self.SCHEDULE_OPTIONS:
            self.logger.error(f"Invalid schedule plan.")
            raise ValueError(f"Nevalidní plán.")

        script = next((s for s in self.SCRIPTS if s.name == script_name), None)
        if not script:
            self.logger.error(f"Script not found: {script_name}")
            raise ValueError(f"Skript {script_name} nebyl nalezen.")

        script_path, exists = self.get_script_path(script)
        if not exists:
            self.logger.error("Cannot set schedule: Script file not found")
            raise ValueError(f"Skript nebyl nalezen: {script_path}. Skuste prohledat souborový system.")

        try:
            cron = CronTab(user=True)
            schedule = self.SCHEDULE_OPTIONS[schedule_name]
            
            venv_python = str(Path(self.scripts_folder) / 'venv' / 'bin' / 'python3')
            
            for job in cron:
                if script_path in str(job.command):
                    cron.remove(job)
            
            if schedule:
                job = cron.new(
                    command=f"{venv_python} {script_path}",
                    comment=f"sync_manager_{script_name}"
                )
                job.setall(schedule)
            
            cron.write()
            
            self.config[f'schedule_{script_name}'] = schedule
            self.save_config()
            
            message = (f"Plán synchronizace nastaven na {schedule_name.lower()}" if schedule else
                      "Plán synchronizace odstraněn") + f" pro úlohu {script.display_name}"
            
            return {'success': True, 'message': message}
            
        except Exception as e:
            self.logger.error("Couldn't set schedule: {e}")
            raise RuntimeError(f"Nepodařilo sa uložit plán: {e}")

def get_sync_manager():
    # Returns singleton instance of SyncManager
    if not hasattr(get_sync_manager, 'instance'):
        get_sync_manager.instance = SyncManager()
    return get_sync_manager.instance

def create_app():
    # Creates the app and loads SyncManager
    load_dotenv()
    
    app = Flask(__name__)
    
    app.config.update(
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY'),
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    )
    
    # Initialize SyncManager at app startup
    with app.app_context():
        get_sync_manager()
    
    return app

app = create_app()

def check_credentials(username: str, password: str) -> bool:
    # Verify username and password against environment variables.
    stored_username = os.getenv('ADMIN_USERNAME')
    stored_password = os.getenv('ADMIN_PASSWORD')
    
    if not stored_username or not stored_password:
        app.logger.error("Admin credentials not found in environment variables")
        return False
    
    if username != stored_username or password != stored_password:
        return False
    
    return True

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Function that redirects user to login if they are not logged in admin
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Handles login of admin user
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if check_credentials(username, password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('Nesprávné přihlašovací údaje', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Handles logout of admin user
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # Returns validatidated scripts and current schedules for them
    sync_manager = get_sync_manager()
    validation = sync_manager.validate_folder()
    return render_template('index.html',
        validation=validation,
        schedule_options=SyncManager.SCHEDULE_OPTIONS.keys(),
        current_schedules={
            script.name: sync_manager.get_current_schedule(script.name)
            for script in validation['scripts']
        }
    )

@app.route('/api/refresh', methods=['POST'])
@login_required
def refresh():
    # Revalidates if scripts can be run
    try:
        sync_manager = get_sync_manager()
        validation = sync_manager.validate_folder()
        return jsonify({
            'success': True,
            **validation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/run-script/<script_name>', methods=['POST'])
@login_required
def run_script(script_name):
    # Runs one of the scripts as subprocess
    try:
        sync_manager = get_sync_manager()
        result = sync_manager.run_script(script_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/save-schedule/<script_name>', methods=['POST'])
@login_required
def save_schedule(script_name):
    # Saves a cron schedule for given script
    try:
        sync_manager = get_sync_manager()
        schedule_name = request.json.get('schedule')
        if not schedule_name:
            return jsonify({'success': False, 'message': 'Nebyl zadán plán pro synchronizaci.'}), 400
            
        result = sync_manager.save_schedule(script_name, schedule_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    # In production, we'll use gunicorn instead of this
    app.run(host='0.0.0.0', port=3002)