import requests
import psycopg2
from datetime import datetime
import re
from typing import Dict, List, Optional, TypedDict
import os
from dotenv import load_dotenv
import logging
import json
from pathlib import Path
import configparser
import sys

from validators import (
    validate_email,
    validate_phone,
    validate_ic,
    validate_dic,
    validate_data_box,
)

"""
Class representing contact for one employee of the municipality.
"""
class Employee(TypedDict):
    name: str
    position: Optional[str]
    phone: Optional[str]
    email: Optional[str]

"""
Class representing days and time when municipality is open.
"""
class OfficeHours(TypedDict):
    days: str
    time: str
    
"""
Class representing contact on municipality itself.
"""
class Contact(TypedDict):
    name: str
    address: Optional[str]
    phone: Optional[str]
    mobile: Optional[str]
    email: Optional[str]
    maintenance: Optional[str]
    data_id: Optional[str]
    ic: Optional[str]
    dic: Optional[str]
    bank_account: Optional[str]
    office_hours: List[OfficeHours]
    employees: List[Employee]

"""
Class that updates contacts for Portal Obcana from API of Orechov website. 
"""
class ContactUpdater:
    def __init__(self, config_path='config.txt'):
        # Convert to Path object if it's a string
        config_path = Path(config_path)
        
        # Get the directory where the script is located
        self.script_dir = Path(__file__).parent.absolute()
        
        # If path is not absolute, make it relative to script directory
        if not config_path.is_absolute():
            config_path = self.script_dir / config_path
            
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")
            
        self.config = configparser.ConfigParser()
        self.config.read(str(config_path))
        
        self.base_path = self.script_dir
        self._load_configurations()
        self.logger = self._setup_logging()
        
        load_dotenv()
        
        # Database configuration from environment variables
        if self.uses_ssl == 'True':
            self.db_params = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT'),
                'sslmode': 'verify-full',
                'sslcert': os.getenv('SSL_CERT_FILE', str(self.client_crt_file)),
                'sslkey': os.getenv('SSL_KEY_FILE', str(self.client_key_file)),
                'sslrootcert': os.getenv('SSL_CA_FILE', str(self.ca_crt))
            }
            # Verify SSL files exist
            self._verify_ssl_files()
        else:
            self.db_params = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT'),
            }

        if not all(self.db_params.values()):
            self.logger.error("Missing required database configuration in environment variables")
            raise ValueError("Missing required database configuration")
        

    def _verify_ssl_files(self):
        # Verify that all required SSL files exist
        ssl_files = [
            self.db_params['sslcert'],
            self.db_params['sslkey'],
            self.db_params['sslrootcert']
        ]
        
        for file_path in ssl_files:
            if not self._resolve_path(file_path).is_file():
                raise FileNotFoundError(f"Required SSL file not found: {file_path}")
    
    def _resolve_path(self, path_str):
        # Helper method to resolve paths based on whether they're absolute or relative
        if path_str.startswith('/'):
            return Path(path_str)
        return self.base_path / path_str
        
    def _load_configurations(self):
        # API configuration
        self.api_url = self.config['API']['url']
        
        self.uses_ssl = self.config['SSL']['with_ssl']

        # Load directories, log and ssl file paths
        self.logs_directory = self._resolve_path(self.config['Logs']['directory'])
        self.ssl_directory = self._resolve_path(self.config['SSL']['directory'])
        
        
        self.log_file = self.logs_directory / self.config['Logs']['filename']
        self.client_crt_file = self.ssl_directory / Path('client.crt')
        self.client_key_file = self.ssl_directory / Path('client.key')
        self.ca_crt = self.ssl_directory / Path('ca.crt')
        
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _setup_logging(self) -> None:
        # Set up logging
        try:
            os.makedirs(self.logs_directory, exist_ok=True)
            
            logger = logging.getLogger('portal_contacts_sync')
            logger.setLevel(logging.INFO)
            logger.handlers = []
            
            handler = logging.FileHandler(
                self.log_file,
                encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            return logger
        except Exception as e:
            raise ValueError(f"Failure to set up logging for program: {e}")

    def parse_office_hours(self, content: str) -> List[OfficeHours]:
        # Extract office hours from the content
        try:
            self.logger.debug("Parsing office hours")
            office_hours: List[OfficeHours] = []
            
            office_hours_match = re.search(r'\*\*Úřední hodiny:\*\*\r\n([\s\S]*?)(?:\r\n\r\n\.\[stack\]|\r\n\r\n\*\*|$)', content)
            if not office_hours_match:
                self.logger.error("No office hours section found in content")
                return [] # If office hours are removed, the synchronization should still proceed

            hours_text = office_hours_match.group(1)
            
            for line in hours_text.split('\n'):
                line = line.strip()
                if not line or ':' not in line:
                    continue
                
                days, time = line.split(':', 1)
                office_hours.append({
                    'days': days.strip(),
                    'time': time.strip()
                })
            
            self.logger.info("Parsing of office hours was successful.")
            return office_hours
        except Exception as e:
            self.logger.error(f"Failed to parse town hall working hours: {str(e)}")
            raise

    def parse_employees(self, content: str) -> List[Employee]:
        # Extract employee information from the content
        try:
            employees: List[Employee] = []
            staff_data = re.findall(r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)', content)
            
            for name, position, phone, email in staff_data:
                contact = Employee(
                    name=name.strip(),
                    position=position.strip(),
                    phone=validate_phone(phone.strip(), self.logger),
                    email=validate_email(email.strip(), self.logger)
                )
                employees.append(contact)
            
            if employees == []:
                self.logger.error("No employees found. Format of contacts likely changed. Aborting synchronization.")
                raise ValueError("No employees found. Format of contacts likely changed. Aborting synchronization.")
            
            self.logger.info("Parsing of employee contacts was successful.")
            return employees
        except Exception as e:
            self.logger.error(f"Failed to parse employee contacts: {str(e)}")
            raise

    def parse_main_content(self, content: str) -> Dict[str, Optional[str]]:
        # Extract main contact information from the content
        try:
            main_section = content.split('**Úřední hodiny:**')[0]
            
            address_match = re.search(r'\*\*Obec Ořechov\*\*\r\n(.*?)(?=\r\n\r\nTel\.:|$)', main_section, re.DOTALL)
            address = address_match.group(1).strip() if address_match else None
            
            main_data = {
                'name': 'Obec Ořechov',
                'address': address,
                'phone': validate_phone(next((m.group(1) for m in re.finditer(r'Tel\.:\s*([^\n]+)', main_section)), None), self.logger),
                'mobile': validate_phone(next((m.group(1) for m in re.finditer(r'Mobil:\s*([^\n]+)', main_section)), None), self.logger),
                'email': validate_email(next((m.group(1) for m in re.finditer(r'E-mail:\s*([^\n]+)', main_section)), None), self.logger),
                'maintenance': validate_email(next((m.group(1) for m in re.finditer(r'Údržba obce:\s*([^\n]+)', main_section)), None), self.logger),
                'data_id': validate_data_box(next((m.group(1) for m in re.finditer(r'ID datové schránky:\s*([^\n]+)', main_section)), None), self.logger),
                'ic': validate_ic(next((m.group(1) for m in re.finditer(r'IČ:\s*([^\n]+)', main_section)), None), self.logger),
                'dic': validate_dic(next((m.group(1) for m in re.finditer(r'DIČ:\s*([^\n]+)', main_section)), None), self.logger),
                'bank_account': next((m.group(1) for m in re.finditer(r'č\.ú\.:\s*([^\n]+)', main_section)), None),
            }
            if all(value is None for key, value in main_data.items() if key != 'name'):
                self.logger.error("No main contact found. Format of contacts likely changed. Aborting synchronization.")
                raise ValueError("No main contact found. Format of contacts likely changed. Aborting synchronization.")
            
            self.logger.info("Parsing of main contact was successful.")
            return main_data
        except Exception as e:
            self.logger.error(f"Failed to parse main contact: {str(e)}")
            raise
        

    def fetch_and_parse_contact(self) -> Contact:
        # Fetch and parse contact information from the API.
        self.logger.info(f"Fetching contact data from {self.api_url}")
        
        try:
            response = requests.get(self.api_url)
            response.raise_for_status()
            content = response.json()['content']

            main_data = self.parse_main_content(content)
            office_hours = self.parse_office_hours(content)
            employees = self.parse_employees(content)

            self.logger.info("Successfully parsed all contact data")
            self.logger.info(f"Found {len(office_hours)} office hours and {len(employees)} employees")

            return {
                **main_data,
                'office_hours': office_hours,
                'employees': employees
            }
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch data from API because API request failed: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch data from API: {str(e)}")
            raise

    def ensure_tables_exist(self) -> None:
        # Check if all required tables exist
        self.logger.info("Checking if required database tables exist")
        required_tables = ['contact', 'office_hours', 'employees']
        missing_tables = []
        
        with psycopg2.connect(**self.db_params) as conn:
            with conn.cursor() as cur:
                try:
                    for table in required_tables:
                        cur.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = %s
                            );
                        """, (table,))
                        exists = cur.fetchone()[0]
                        
                        if not exists:
                            missing_tables.append(table)
                    
                    if missing_tables:
                        error_msg = f"Missing required tables: {', '.join(missing_tables)}"
                        self.logger.error(error_msg)
                        raise ValueError(error_msg)
                        
                    self.logger.info("All required database tables exist")
                    
                except psycopg2.Error as e:
                    error_msg = f"Database error while checking tables: {str(e)}"
                    self.logger.error(error_msg)
                    raise psycopg2.Error(error_msg)

    def update_database(self, contact_data: Contact) -> None:
        # Update or create contact information in the database.
        self.logger.info("Starting database update")
        
        with psycopg2.connect(**self.db_params) as conn:
            with conn.cursor() as cur:
                try:
                    # Check if contact exists
                    cur.execute('SELECT id FROM contact WHERE id = 1')
                    existing_contact = cur.fetchone()

                    if existing_contact:
                        # Update existing contact
                        cur.execute("""
                            UPDATE contact SET
                                name = %s,
                                address = %s,
                                phone = %s,
                                mobile = %s,
                                email = %s,
                                maintenence = %s,
                                "dataId" = %s,
                                ic = %s,
                                dic = %s,
                                "bankAccount" = %s,
                                "lastUpdated" = CURRENT_TIMESTAMP
                            WHERE id = 1
                        """, (
                            contact_data['name'],
                            contact_data['address'],
                            contact_data['phone'],
                            contact_data['mobile'],
                            contact_data['email'],
                            contact_data['maintenance'],
                            contact_data['data_id'],
                            contact_data['ic'],
                            contact_data['dic'],
                            contact_data['bank_account']
                        ))
                    else:
                        self.logger.info("Creating new contact record with ID 1")
                        cur.execute("""
                            INSERT INTO contact (
                                id,
                                name,
                                address,
                                phone,
                                mobile,
                                email,
                                maintenence,
                                "dataId",
                                ic,
                                dic,
                                "bankAccount",
                                "createdAt",
                                "lastUpdated"
                            )
                            VALUES (
                                1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                        """, (
                            contact_data['name'],
                            contact_data['address'],
                            contact_data['phone'],
                            contact_data['mobile'],
                            contact_data['email'],
                            contact_data['maintenance'],
                            contact_data['data_id'],
                            contact_data['ic'],
                            contact_data['dic'],
                            contact_data['bank_account']
                        ))

                    # Clear existing office hours
                    cur.execute('DELETE FROM office_hours WHERE "contactId" = 1')

                    # Insert new office hours
                    if contact_data['office_hours']:
                        office_hours_values = [(
                            h['days'],
                            h['time'],
                            1
                        ) for h in contact_data['office_hours']]
                        
                        cur.executemany("""
                            INSERT INTO office_hours (
                                days,
                                time,
                                "contactId"
                            )
                            VALUES (%s, %s, %s)
                        """, office_hours_values)

                    # Clear existing employees
                    cur.execute('DELETE FROM employees WHERE "contactId" = 1')

                    # Insert new employees
                    if contact_data['employees']:
                        employee_values = [(
                            e['name'],
                            e['position'],
                            e['phone'],
                            e['email'],
                            1
                        ) for e in contact_data['employees']]
                        
                        cur.executemany("""
                            INSERT INTO employees (
                                name,
                                position,
                                phone,
                                email,
                                "contactId"
                            )
                            VALUES (%s, %s, %s, %s, %s)
                        """, employee_values)

                    conn.commit()
                    self.logger.info("Successfully updated contact information")
                    self.logger.info(f"Updated or added {len(contact_data['office_hours'])} office hours "
                                   f"and {len(contact_data['employees'])} employees")

                except Exception as e:
                    conn.rollback()
                    self.logger.error(f"Database update failed: {str(e)}")
                    raise

    def update(self) -> None:
        self.logger.info("Starting contact data update process")
        try:
            self.ensure_tables_exist()
            contact_data = self.fetch_and_parse_contact()
            self.update_database(contact_data)
            self.logger.info("Contact data update completed successfully")
        except requests.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            raise
        except psycopg2.Error as e:
            self.logger.error(f"Database operation failed: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error occurred: {str(e)}")
            raise

def main():
    try:
        updater = ContactUpdater()
    except Exception as e:
        print(f"Synchronizace selhala. Konfigurační chyba: {str(e)}", file=sys.stderr)
        return 1
    try:
        updater.update()
        return 0
    except Exception as e:
        updater.logger.error(f"Update of contacts failed: {str(e)}")
        print(f"Synchronizace selhala. Pro více informací si přečtěte záznamový soubor na adrese {updater.log_file}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())