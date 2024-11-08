import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import requests
import json
import logging
import os
import sys
import importlib.util
import configparser
from pathlib import Path
from datetime import datetime

"""
Class for loading the configuration of the program from file named config.txt.
"""
class ConfigLoader:
    def __init__(self, config_path='config.txt'):
        # Convert to Path object if it's a string
        config_path = Path(config_path)
        
        # Get the directory where the script is located
        self.script_dir = Path(__file__).parent.absolute()
        
        # If config_path is relative, make it relative to script directory
        if not config_path.is_absolute():
            config_path = self.script_dir / config_path

        # Check if file exists before trying to read it
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

        self.config = configparser.ConfigParser()
        # Convert Path to string for configparser
        self.config.read(str(config_path))
        self.base_path = config_path.parent
        self._load_configurations()

    def _resolve_path(self, path_str):
        # Helper method to resolve paths based on whether they're absolute or relative
        if path_str.startswith('/'):
            return Path(path_str)
        return self.base_path / path_str

    def _load_configurations(self):
        # Database and credentials configurations
        self.database_url = self.config['Database']['database_url']
        self.credentials_path = self._resolve_path(self.config['Database']['credentials_path'])

        # File paths for configurations and parsers
        self.data_config_path = self._resolve_path(self.config['Files']['data_config'])
        self.parsers_module_path = self._resolve_path(self.config['Files']['parsers_module'])

        # Logs directory and main log file path
        self.logs_directory = self._resolve_path(self.config['Logs']['directory'])
        
        self.main_log = self.logs_directory / self.config['Logs']['main']
        
        self.main_log.parent.mkdir(parents=True, exist_ok=True)

        # Load contact configurations for each type of contact in use for App
        with open(self.data_config_path) as f:
            self.data_config = json.load(f)

        # Load contact parsers
        self.parser_functions = self._load_parser_functions()

    def _load_parser_functions(self):
        # Load parser functions used to parse each of contacts categories
        spec = importlib.util.spec_from_file_location("parsers", self.parsers_module_path)
        parsers_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parsers_module)
        return parsers_module.PARSER_FUNCTIONS


"""
Class that initializes database access and logging. After that by calling update the class can get new data from provided API,
parse and compare them to the data in database and then change the database if necessary.
"""
class ContactDataUpdater:
    def __init__(self, config_loader, main_logger):
        self.config_loader = config_loader
        self.main_logger = main_logger
        self.logger = None
        self.data_config = None
        self.initialize_firebase()

    def initialize_firebase(self):
        # Initialize Firebase connection
        if not firebase_admin._apps:
            try:
                # Load credentials
                cred = credentials.Certificate(str(self.config_loader.credentials_path))
                
                # Initialize Firebase
                firebase_admin.initialize_app(cred, {
                    'databaseURL': self.config_loader.database_url
                })
                
            except ValueError as e:
                raise FirebaseInitializationError(
                    f"Invalid credentials format: {str(e)}"
                ) from e
                
            except (firebase_admin.exceptions.FirebaseError,
                   firebase_admin.exceptions.UnavailableError) as e:
                raise FirebaseInitializationError(
                    f"Firebase initialization failed: {str(e)}"
                ) from e

    def setup_logging(self, log_name):
        # Set up logging for the current contact type.
        os.makedirs(self.config_loader.logs_directory, exist_ok=True)
        logger = logging.getLogger(log_name)
        logger.setLevel(logging.INFO)
        logger.handlers = []
        
        handler = logging.FileHandler(
            self.config_loader.logs_directory / log_name,
            encoding='utf-8'
        )
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger

    def set_contact_type(self, contact_type):
        # Set the contact type for subsequent operations.
        required_attr = ['firebase_route', 'log_name', 'api_url', 'parser_function']
        try:
            if contact_type not in self.config_loader.data_config:
                raise ValueError(f"Contact type not in config file: {contact_type}")
            
            data_config = self.config_loader.data_config[contact_type].copy()
            
            for attr in required_attr:
                if attr not in data_config:
                    raise ValueError(f"Data config file missing attribute: {attr}")
            parser_name = data_config['parser_function']
            
            if parser_name not in self.config_loader.parser_functions:
                raise ValueError(f"Parser function not in config file: {parser_name}")
            
            data_config['parser'] = self.config_loader.parser_functions[parser_name]
            self.data_config = data_config
            self.logger = self.setup_logging(self.data_config['log_name'])
            return True
            
        except Exception as e:
            self.main_logger.error(f"Configuration error for {contact_type}: {str(e)}")
            return False

    def fetch_contact_data(self):
        # Fetch contact data from API endpoint.
        try:
            response = requests.get(self.data_config['api_url'])
            response.raise_for_status()
            response_content = response.json()['content']
            return response_content
        except Exception as e:
            self.logger.error(f"Failed to fetch contact data from API: {e}")
            self.main_logger.error(f"Failed to fetch contact data  from API: {e}")
            return None

    def get_existing_contacts(self):
        # Retrieve existing contacts from database.
        try:
            ref = db.reference(self.data_config['firebase_route'])
            return ref.get()
        except Exception as e:
            self.logger.error(f"Failed to fetch existing contacts: {e}")
            raise ValueError(f"Failed to fetch existing contacts: {e}")

    def update_contacts(self, new_contacts, existing_contacts):
        """
        Update contacts in Firebase, preserving additional fields for existing contacts
        but removing contacts that are not in the API response.
        """
        ref = db.reference(self.data_config['firebase_route'])
        new_data_list = [contact.to_dict() for contact in new_contacts]
        
        # Create dictionaries with title as key
        existing_dict = {item.get('title'): item for item in (existing_contacts[1:] if existing_contacts else [])}
        new_dict = {item.get('title'): item for item in new_data_list}
        
        changes = {
            'detected': False, # If there where any changes made during update
            'updates': [None],  # Initialize with None as first element
            'added': [], # Added contacts
            'modified': [], # Contacts with changes
            'removed': [] # Contacts with titles not in contacts from API 
        }
        
        # Process all contacts from API
        for title, new_item in new_dict.items():
            if title not in existing_dict:
                # New contact
                changes['added'].append(title)
                changes['detected'] = True
                self.logger.info(f"New contact added: {title}")
                changes['updates'].append(new_item)
            else:
                # Existing contact - merge with existing data
                existing_item = existing_dict[title]
                merged_item = existing_item.copy()
                
                # Track modifications
                item_changes = {}
                
                # Update fields from new data
                for key, new_value in new_item.items():
                    if key not in existing_item:
                        item_changes[key] = {'added': new_value}
                        changes['detected'] = True
                    elif existing_item[key] != new_value:
                        item_changes[key] = {'old': existing_item[key], 'new': new_value}
                        changes['detected'] = True
                    merged_item[key] = new_value
                
                if item_changes:
                    changes['modified'].append(title)
                    self.logger.info(f"Modified contact: {title}")
                    self.logger.debug(f"Changes: {json.dumps(item_changes, indent=2, ensure_ascii=False)}")
                
                changes['updates'].append(merged_item)
        
        # Log removed contacts
        for title in existing_dict:
            if title not in new_dict:
                changes['removed'].append(title)
                changes['detected'] = True
                self.logger.info(f"Removed contact: {title}")

        if changes['detected']:
            
            # Log changes summary
            self.log_changes_summary(changes)
            
            # Update Firebase
            try:
                ref.set(changes['updates'])
                self.logger.info(f"Successfully updated contacts at {datetime.now().isoformat()}")
                self.main_logger.info(f"Successfully updated {self.data_config['firebase_route']} with changes")
                return True
            except Exception as e:
                error_msg = f"Failed to update contacts: {str(e)}"
                self.logger.error(error_msg)
                self.main_logger.error(f"Error updating {self.data_config['firebase_route']}: {str(e)}")
                return False
        else:
            self.logger.info("No changes detected in contacts")
            self.main_logger.info(f"Successfully updated {self.data_config['firebase_route']} (no changes)")
            return True

    def log_changes_summary(self, changes):
        """Log detailed changes summary to type-specific log."""
        self.logger.info("Changes summary:")
        if changes['added']:
            self.logger.info(f"Added contacts: {json.dumps(changes['added'], ensure_ascii=False)}")
        if changes['modified']:
            self.logger.info(f"Modified contacts: {json.dumps(changes['modified'], ensure_ascii=False)}")
        if changes['removed']:
            self.logger.info(f"Removed contacts: {json.dumps(changes['removed'], ensure_ascii=False)}")
        self.logger.info(f"Updated data structure: {json.dumps(changes['updates'], indent=2, ensure_ascii=False)}")

    def update(self):
        # Update the database for previously set contact type
        if not self.data_config:
            self.main_logger.error("No contact type set. Call set_contact_type() before updating.")
            return False

        self.logger.info(f"Starting contact update process for {self.data_config['firebase_route']}")
        raw_data = self.fetch_contact_data()
        if raw_data:
            try:
                parsed_data = self.data_config['parser'](raw_data, self.main_logger, self.logger)
                existing_data = self.get_existing_contacts()
                return self.update_contacts(parsed_data, existing_data)
            except Exception as e:
                error_msg = f"Error during contact update: {str(e)}"
                self.logger.error(error_msg)
                self.main_logger.error(f"Error updating {self.data_config['firebase_route']}: {str(e)}")
                return False
        else:
            error_msg = "Failed to fetch contact data"
            self.logger.error(error_msg)
            self.main_logger.error(f"Error updating {self.data_config['firebase_route']}: {error_msg}")
            return False

def setup_main_logger(main_log_path):
    # Set up the main logger for high-level program status.
    logger = logging.getLogger('main')
    logger.setLevel(logging.INFO)
    logger.handlers = []
    
    handler = logging.FileHandler(main_log_path, encoding='utf-8')
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def main():
    try:
        config_loader = ConfigLoader()
        main_logger = setup_main_logger(config_loader.main_log)
    except Exception as e:
        print(f"Synchronizace selhala. Konfigurační chyba: {str(e)}", file=sys.stderr)
        return 1

    try:
        updater = ContactDataUpdater(config_loader, main_logger)
        
        for contact_type in config_loader.data_config.keys():
            if updater.set_contact_type(contact_type):
                if not updater.update():
                    main_logger.error(f"The contacts from {contact_type} could not be updated.")
        return 0
                
    except Exception as e:
        main_logger.error(f"Error during update of database: {str(e)}")
        print(f"Synchronizace selhala. Pro více informací si přečtěte log na adrese {config_loader.main_log}", file=sys.stderr)
        return 1
        

if __name__ == "__main__":
    sys.exit(main())