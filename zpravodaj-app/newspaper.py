import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import requests
from bs4 import BeautifulSoup
import re
import logging
import os
from datetime import datetime
from pathlib import Path
import configparser
import sys

class NewspaperItem:
    def __init__(self, id, link, release, year):
        # Convert id to integer
        self.id = int(id)
        self.link = link
        self.release = int(release)
        self.year = int(year)

    def to_dict(self):
        return {
            'id': self.id,
            'link': self.link,
            'release': self.release,
            'year': self.year
        }

class NewspaperSynchronizer:
    def __init__(self, config_path='newspaper_config.txt'):
        try:
            self.config = self._load_config(config_path)
            self.logger = self._setup_logging()
            self._initialize_firebase()
        except Exception as e:
            print(f"Initialization error: {str(e)}")
            raise

    def _load_config(self, config_path):
        """Load and validate configuration from file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

        config = configparser.ConfigParser()
        config.read(config_path)
        
        required_sections = ['Database', 'Application', 'Logging']
        missing_sections = [section for section in required_sections if section not in config.sections()]
        if missing_sections:
            raise ValueError(f"Missing required sections in config file: {', '.join(missing_sections)}")
        
        # Convert config to dictionary with path objects where needed
        base_path = Path(config_path).parent
        return {
            'database_url': config['Database']['database_url'],
            'credentials_path': base_path / config['Database']['credentials_path'],
            'logs_directory': base_path / config['Logging']['directory'],
            'log_filename': config['Logging']['filename'],
            'newspapers_url': config['Application']['url'],
            'firebase_route': config['Application']['firebase_route'],
            'scrape_element': config['Application']['scrape_element']
        }

    def _setup_logging(self):
        """Set up logging to both file and console."""
        try:
            os.makedirs(self.config['logs_directory'], exist_ok=True)
            
            logger = logging.getLogger('newspapers_sync')
            logger.setLevel(logging.INFO)
            
            # Remove existing handlers
            logger.handlers = []
            
            # Add file handler
            handler = logging.FileHandler(
                self.config['logs_directory'] / self.config['log_filename'],
                encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            # Add console handler
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            return logger
        except Exception as e:
            print(f"Error setting up logging: {str(e)}")
            raise

    def _initialize_firebase(self):
        """Initialize Firebase connection."""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(self.config['credentials_path']))
                firebase_admin.initialize_app(cred, {
                    'databaseURL': self.config['database_url']
                })
        except Exception as e:
            self.logger.error(f"Firebase initialization error: {str(e)}")
            raise

    def _parse_newspaper_item(self, li_element):
        """Parse a single newspaper item from an HTML li element."""
        try:
            link = li_element.find('a')['href']
            if not link.startswith('http'):
                link = 'https://www.orechovubrna.cz' + link
                
            # Extract release number and year from the link text
            text = li_element.text
            match = re.search(r'zpravodaj (\d+)/(\d{4})', text, re.IGNORECASE)
            if match:
                release = int(match.group(1))
                year = int(match.group(2))
                
                # Create ID in format YYYYRR as integer
                id = (year * 100) + release
                
                return NewspaperItem(id, link, release, year)
            
        except Exception as e:
            self.logger.error(f"Error parsing newspaper item: {str(e)}")
            return None
        
        return None

    def fetch_newspapers(self):
        """Fetch and parse newspapers from the website."""
        try:
            self.logger.info(f"Fetching newspapers from {self.config['newspapers_url']}")
            response = requests.get(self.config['newspapers_url'])
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            newspaper_items = []
            
            # Find all li elements containing newspaper links
            for li in soup.find_all(self.config['scrape_element']):
                if 'zpravodaj' in li.text.lower():
                    item = self._parse_newspaper_item(li)
                    if item:
                        newspaper_items.append(item)
            
            self.logger.info(f"Found {len(newspaper_items)} newspaper items")
            return newspaper_items
            
        except requests.RequestException as e:
            self.logger.error(f"Error fetching newspapers: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching newspapers: {str(e)}")
            return None

    def get_existing_data(self):
        """Retrieve existing newspaper data from Firebase."""
        try:
            ref = db.reference(self.config['firebase_route'])
            data = ref.get() or {}
            
            # Convert string keys to integers if they exist
            return {int(k): v for k, v in data.items()} if data else {}
            
        except Exception as e:
            self.logger.error(f"Error fetching existing data: {str(e)}")
            return {}

    def compare_and_update(self, new_items, existing_data):
        """Compare and update newspaper data in Firebase, only checking for link changes."""
        if not new_items:
            self.logger.error("No new items to process")
            return

        ref = db.reference(self.config['firebase_route'])
        
        # Convert new items to dictionary format
        new_dict = {item.id: item.to_dict() for item in new_items}
        
        changes_detected = False
        link_updates = []
        new_items_added = []
        
        # Check each new item
        for id, new_item in new_dict.items():
            if id in existing_data:
                # Check only for link changes in existing items
                if existing_data[id]['link'] != new_item['link']:
                    self.logger.info(f"Link change detected for newspaper {id}")
                    self.logger.info(f"Old link: {existing_data[id]['link']}")
                    self.logger.info(f"New link: {new_item['link']}")
                    ref.child(str(id)).child('link').set(new_item['link'])
                    changes_detected = True
                    link_updates.append(id)
            else:
                # Add new item to database
                self.logger.info(f"New newspaper detected: {id}")
                ref.child(str(id)).set(new_item)
                changes_detected = True
                new_items_added.append(id)
        
        if changes_detected:
            self.logger.info("Summary of changes:")
            if link_updates:
                self.logger.info(f"Updated links for newspapers: {link_updates}")
            if new_items_added:
                self.logger.info(f"Added new newspapers: {new_items_added}")
        else:
            self.logger.info("No changes detected in newspapers data")

    def synchronize(self):
        """Main synchronization process."""
        try:
            self.logger.info(f"Starting newspaper synchronization process for {self.config['firebase_route']}")
            
            new_items = self.fetch_newspapers()
            if new_items:
                existing_data = self.get_existing_data()
                self.compare_and_update(new_items, existing_data)
                self.logger.info("Synchronization completed successfully")
            else:
                self.logger.error("Failed to fetch newspapers data")
                
        except Exception as e:
            self.logger.error(f"Error during synchronization: {str(e)}")
            raise

def main():
    try:
        synchronizer = NewspaperSynchronizer()
        synchronizer.synchronize()
    except Exception as e:
        logging.error(f"Synchronization error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
