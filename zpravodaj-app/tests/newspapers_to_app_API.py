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

"""
Newspaper class representing a release of Orechovsky zpravodaj.
"""
class NewspaperItem:
    def __init__(self, id, link, release, year):
        self.id = int(id)
        self.link = link # String link to website of Orechov where the releases are stored
        self.release = int(release)
        self.year = int(year)

    def to_dict(self):
        return {
            'id': self.id,
            'link': self.link,
            'release': self.release,
            'year': self.year
        }

"""
Class used for synchronizing Orechov app database with releases of Orechovsky zpravodaj from
website of Orechov with use of provided API.
"""
class NewspaperUpdater:
    def __init__(self, config_path='config.txt'):
        try:
            self.script_dir = Path(__file__).parent.absolute()
            
            # Convert to Path object and make relative to script directory if not absolute
            config_path = Path(config_path)
            if not config_path.is_absolute():
                config_path = self.script_dir / config_path

            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found at: {config_path}")

            self.config = configparser.ConfigParser()
            self.config.read(str(config_path))
            self._load_configurations()
            self.logger = self._setup_logging()
            self._initialize_firebase()
        except Exception as e:
            raise

    def _resolve_path(self, path_str):
        # Helper method to resolve paths based on whether they're absolute or relative
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self.script_dir / path

    def _load_configurations(self):
        # Database configurations
        self.database_url = self.config['Database']['database_url']
        self.credentials_path = self._resolve_path(self.config['Database']['credentials_path'])

        # Application configurations
        self.newspapers_url = self.config['Application']['url']
        self.firebase_route = self.config['Application']['firebase_route']
        self.scrape_element = self.config['Application']['scrape_element']

        # Logs directory and file
        self.logs_directory = self._resolve_path(self.config['Logging']['directory'])
        self.log_filename = self.config['Logging']['filename']

    def _initialize_firebase(self):
        # Function that initializes firebase service access
        try:
            if not firebase_admin._apps:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(f"Credentials file not found at: {self.credentials_path}")
                
                cred = credentials.Certificate(str(self.credentials_path))
                firebase_admin.initialize_app(cred, {
                    'databaseURL': self.database_url
                })
        except Exception as e:
            raise ValueError(f"Failure to initialize database connection: {str(e)}")

    def _setup_logging(self):
        try:
            os.makedirs(self.logs_directory, exist_ok=True)
            
            logger = logging.getLogger('newspapers_sync')
            logger.setLevel(logging.INFO)
            logger.handlers = []
            
            handler = logging.FileHandler(
                self.logs_directory / self.log_filename,
                encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            return logger
        except Exception as e:
            raise ValueError(f"Failure to set up logging for program: {e}")

    def _parse_newspaper_item(self, li_element):
        # Parse a single newspaper item from an HTML li element.
        try:
            link = li_element.find('a')['href']
            if not link.startswith('http'):
                link = 'https://www.orechovubrna.cz' + link
                
            # Czech month names mapping
            month_mapping = {
                'leden': 1, 'ledna': 1, 'únor': 2, 'února': 2,
                'březen': 3, 'března': 3, 'duben': 4, 'dubna': 4,
                'květen': 5, 'května': 5, 'červen': 6, 'června': 6,
                'červenec': 7, 'července': 7, 'srpen': 8, 'srpna': 8,
                'září': 9, 'říjen': 10, 'října': 10,
                'listopad': 11, 'listopadu': 11, 'prosinec': 12, 'prosince': 12
            }
                
            
            raw_text = li_element.text
            text = raw_text.encode('latin1').decode('utf8').lower()
            
            # Extract release number and year from the link text
            match = re.search(r'zpravodaj (\d+)/(\d{4})', text, re.IGNORECASE)
            if match:
                release = int(match.group(1))
                year = int(match.group(2))
                
                # Create ID in format YYYYRR as integer
                id = (year * 100) + release
                
                return NewspaperItem(id, link, release, year)
            
            # Try second pattern: "zpravodaj MONTH YYYY" used in older publications
            for month_name, month_num in month_mapping.items():
                # Using word boundaries \b to match whole words
                pattern = rf'zpravodaj\s+{month_name}\s+(\d{{4}})'
                match = re.search(pattern, text)
                if match:
                    year = int(match.group(1))
                    release = month_num  # Use month number as release number
                    id = (year * 100) + release
                    return NewspaperItem(id, link, release, year)
            
            self.logger.error(f"Couldn't parse {li_element.text}")
            
        except Exception as e:
            self.logger.error(f"Error parsing newspaper item {li_element.text}: {str(e)}")
            return None
        
        return None

    def fetch_newspapers(self):
        # Fetch and parse newspapers from the website.
        try:
            self.logger.info(f"Fetching newspapers from {self.newspapers_url}")
            response = requests.get(self.newspapers_url)
            response.raise_for_status()
            
            # Parses website html so it is possible to find all newspaper entries
            soup = BeautifulSoup(response.text, 'html.parser')
            newspaper_items = []
            
            # Find all li elements containing newspaper links
            for li in soup.find_all(self.scrape_element):
                # Take only newspaper items
                if 'oåechovskã½ zpravodaj ' in li.text.lower() or 'ořechovský zpravodaj ' in li.text.lower():
                    item = self._parse_newspaper_item(li)
                    if item:
                        newspaper_items.append(item)
            
            self.logger.info(f"Found {len(newspaper_items)} newspaper items")
            if len(newspaper_items) == 0:
                return None
            return newspaper_items
            
        except requests.RequestException as e:
            self.logger.error(f"Error fetching newspapers: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error while fetching newspapers: {str(e)}")
            return None

    def get_existing_data(self):
        # Retrieve existing newspaper data from Firebase.
        try:
            ref = db.reference(self.firebase_route)
            data = ref.get()
            
            # Convert string keys to integers if they exist
            return {int(k): v for k, v in data.items()} if data else {}
            
        except Exception as e:
            self.logger.error(f"Error fetching existing data: {str(e)}")
            return {}

    def compare_and_update(self, new_items, existing_data):
        # Compare and update newspaper data in Firebase.
        try:
            ref = db.reference(self.firebase_route)
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
        except Exception as e:
            self.logger.error(f"Unexpected error during data comparison: {str(e)}")
            raise

    def update(self):
        # Updates newspapers in app to match those on municipality website
        try:
            self.logger.info(f"Starting synchronization process for {self.firebase_route}")
            
            new_items = self.fetch_newspapers()
            if new_items:
                existing_data = self.get_existing_data()
                self.compare_and_update(new_items, existing_data)
                self.logger.info("Synchronization completed successfully")
            else:
                self.logger.error("Failed to fetch newspapers data")
                raise RuntimeError(f"No newspaper data could be parsed from website: {str(e)}")
                
        except Exception as e:
            self.logger.error(f"Error during synchronization: {str(e)}")
            raise
        

def main():
    try:
        updater = NewspaperUpdater()
    except Exception as e:
        print(f"Synchronizace selhala. Konfigurační chyba: {str(e)}", file=sys.stderr)
        return 1
    
    try:
        updater.update()
        return 0
    except Exception as e:
        updater.logger.error(f"Synchronization error: {str(e)}")
        print(f"Synchronizace selhala. Pro více informací si přečtěte log soubor na adrese {updater.logs_directory / updater.log_filename}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
