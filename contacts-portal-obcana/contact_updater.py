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

class Employee(TypedDict):
    name: str
    position: Optional[str]
    phone: Optional[str]
    email: Optional[str]

class OfficeHours(TypedDict):
    days: str
    time: str

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

class ContactUpdater:
    def __init__(self, config_path='config/postgres_config.ini'):
        load_dotenv()
    
        self.script_dir = Path(__file__).parent.absolute()
        
        # Convert to Path object if string
        config_path = Path(config_path)
        
        # If path is not absolute, make it relative to script directory
        if not config_path.is_absolute():
            config_path = self.script_dir / config_path
            
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")
            
        self.config = configparser.ConfigParser()
        self.config.read(str(config_path))
        
        # Setup logging
        self.setup_logging()
        
        # API configuration
        self.api_url = self.config['API']['url']
        
        # Database configuration from environment variables
        self.db_params = {
            'dbname': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT')
        }

        if not all(self.db_params.values()):
            self.logger.error("Missing required database configuration in environment variables")
            raise ValueError("Missing required database configuration")

    def setup_logging(self) -> None:
        try:
            # Configure logging for the application.
            log_dir = Path('logs')  # Use fixed logs directory
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / 'postgres_contact_updater.log'  # Use fixed log filename
            
            logging.basicConfig(
                level=logging.INFO,  # Use fixed logging level
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, encoding='utf-8')
                ]
            )
            
            self.logger = logging.getLogger(__name__)
        except Exception as e:
            print(f"Error setting up logging: {str(e)}", file=sys.stderr)
            raise

    def parse_office_hours(self, content: str) -> List[OfficeHours]:
        # Extract office hours from the content.
        try:
            self.logger.debug("Parsing office hours")
            office_hours: List[OfficeHours] = []
            
            office_hours_match = re.search(r'\*\*Úřední hodiny:\*\*(.*?)(?:\.\[stack\]|$)', content, re.DOTALL)
            if not office_hours_match:
                self.logger.error("No office hours section found in content")
                raise ValueError(f"No office hours section found in content")

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

            self.logger.debug(f"Found {len(office_hours)} office hours entries")
            return office_hours
        except Exception as e:
            self.logger.error(f"Failed to parse town hall working hours: {str(e)}")
            raise

    def parse_employees(self, content: str) -> List[Employee]:
        # Extract employee information from the content.
        self.logger.debug("Parsing employee information")
        try:
            employees: List[Employee] = []
            staff_data = re.findall(r'\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)', content)
            
            for name, position, phone, email in staff_data:
                contact = Employee(
                    name=name.strip(),
                    position=position.strip(),
                    phone=phone.strip(),
                    email=email.strip()
                )
                employees.append(contact)
            
            self.logger.debug(f"Found {len(employees)} employees")
            return employees
        except Exception as e:
            self.logger.error(f"Failed to parse employee contacts: {str(e)}")
            raise

    def parse_main_content(self, content: str) -> Dict[str, Optional[str]]:
        # Extract main contact information from the content.
        self.logger.debug("Parsing main contact information")
        try:
            main_section = content.split('**Úřední hodiny:**')[0]
            
            address_match = re.search(r'\*\*Obec Ořechov\*\*\r\n(.*?)(?=\r\n\r\nTel\.:|$)', main_section, re.DOTALL)
            address = address_match.group(1).strip() if address_match else None
            
            main_data = {
                'name': 'Obec Ořechov',
                'address': address,
                'phone': next((m.group(1) for m in re.finditer(r'Tel\.:\s*([^\n]+)', main_section)), None),
                'mobile': next((m.group(1) for m in re.finditer(r'Mobil:\s*([^\n]+)', main_section)), None),
                'email': next((m.group(1) for m in re.finditer(r'E-mail:\s*([^\n]+)', main_section)), None),
                'maintenance': next((m.group(1) for m in re.finditer(r'Údržba obce:\s*([^\n]+)', main_section)), None),
                'data_id': next((m.group(1) for m in re.finditer(r'ID datové schránky:\s*([^\n]+)', main_section)), None),
                'ic': next((m.group(1) for m in re.finditer(r'IČ:\s*([^\n]+)', main_section)), None),
                'dic': next((m.group(1) for m in re.finditer(r'DIČ:\s*([^\n]+)', main_section)), None),
                'bank_account': next((m.group(1) for m in re.finditer(r'č\.ú\.:\s*([^\n]+)', main_section)), None),
            }
            
            self.logger.debug(f"Parsed main data: {json.dumps(main_data, ensure_ascii=False)}")
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
            self.logger.error(f"Failed to fetch data from API: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to fetch data from API: {str(e)}")
            raise

    def ensure_tables_exist(self) -> None:
        # Check if all required tables exist
        self.logger.info("Checking if required database tables exist")
        required_tables = ['contact', 'OfficeHours', 'employees']
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
                            self.logger.error(f"Required table '{table}' does not exist")
                    
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
        # Update the database with new contact information.
        self.logger.info("Starting database update")
        
        with psycopg2.connect(**self.db_params) as conn:
            with conn.cursor() as cur:
                try:
                    # Check if contact exists
                    cur.execute("SELECT id FROM contact WHERE id = 1")
                    contact_exists = cur.fetchone() is not None

                    if contact_exists:
                        cur.execute("""
                            UPDATE contact SET
                                name = %s,
                                address = %s,
                                phone = %s,
                                mobile = %s,
                                email = %s,
                                maintenence = %s,
                                data_id = %s,
                                ic = %s,
                                dic = %s,
                                bank_account = %s,
                                last_updated = %s
                            WHERE id = 1
                            RETURNING id
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
                            contact_data['bank_account'],
                            datetime.now()
                        ))
                    else:
                        self.logger.info("New contact record created.")
                        cur.execute("""
                            INSERT INTO contact (
                                id, name, address, phone, mobile, email, maintenence,
                                data_id, ic, dic, bank_account, last_updated
                            )
                            VALUES (
                                1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            RETURNING id
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
                            contact_data['bank_account'],
                            datetime.now()
                        ))

                    contact_id = cur.fetchone()[0]

                    # Clear existing office hours and employees
                    cur.execute('DELETE FROM "OfficeHours" WHERE "contactId" = %s', (contact_id,))
                    cur.execute('DELETE FROM employees WHERE "contactId" = %s', (contact_id,))

                    # Insert new office hours
                    if contact_data['office_hours']:
                        cur.executemany("""
                            INSERT INTO "OfficeHours" (days, time, "contactId")
                            VALUES (%s, %s, %s)
                        """, [(h['days'], h['time'], contact_id) for h in contact_data['office_hours']])

                    # Insert new employees
                    if contact_data['employees']:
                        cur.executemany("""
                            INSERT INTO employees (name, position, phone, email, "contactId")
                            VALUES (%s, %s, %s, %s, %s)
                        """, [(
                            e['name'],
                            e['position'],
                            e['phone'],
                            e['email'],
                            contact_id
                        ) for e in contact_data['employees']])

                    conn.commit()
                    self.logger.info(f"Successfully updated contacts")
                    self.logger.info(f"Updated or added {len(contact_data['office_hours'])} office hours and {len(contact_data['employees'])} employees")

                except Exception as e:
                    conn.rollback()
                    self.logger.error(f"Database update failed: {str(e)}")
                    raise

    def synchronize(self) -> None:
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
        print(f"Configuration error in updating contacts for Portal obcana: {str(e)}", file=sys.stderr)
        return
    try:
        updater.synchronize()
    except Exception as e:
        updater.logging.error(f"Update of contacts failed: {str(e)}")

if __name__ == "__main__":
    main()