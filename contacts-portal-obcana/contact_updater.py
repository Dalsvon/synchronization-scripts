
import requests
import psycopg2
from datetime import datetime
import re
from typing import Dict, List, Optional, TypedDict
import os
from dotenv import load_dotenv

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
    API_URL = "https://www.orechovubrna.cz/api/kontakt/"

    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Database configuration
        self.db_params = {
            'dbname': os.getenv('DB_NAME', 'your_db_name'),
            'user': os.getenv('DB_USER', 'your_db_user'),
            'password': os.getenv('DB_PASSWORD', 'your_db_password'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432')
        }

    def parse_office_hours(self, content: str) -> List[OfficeHours]:
        """Extract office hours from the content."""
        office_hours: List[OfficeHours] = []
        
        # Find office hours section
        office_hours_match = re.search(r'\*\*Úřední hodiny:\*\*(.*?)(?:\.\[stack\]|$)', content, re.DOTALL)
        if not office_hours_match:
            return office_hours

        hours_text = office_hours_match.group(1)
        
        # Process each line
        for line in hours_text.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            
            # Split on first colon
            days, time = line.split(':', 1)
            office_hours.append({
                'days': days.strip(),
                'time': time.strip()
            })

        return office_hours

    def parse_employees(self, content: str) -> List[Employee]:
        """Extract employee information from the content."""
        employees: List[Employee] = []
        
        stack_section = content.split('.[stack]')
        if len(stack_section) < 2:
            return employees

        employee_rows = stack_section[1].strip().split('\n')
        
        for row in employee_rows:
            if '|' not in row:
                continue
            
            parts = [part.strip() for part in row.split('|')]
            if len(parts) < 5:
                continue

            name = parts[1].replace('**', '').strip()
            if not name:
                continue

            employees.append({
                'name': name,
                'position': parts[2].strip() or None,
                'phone': parts[3].strip() or None,
                'email': parts[4].strip() or None
            })

        return employees

    def parse_main_content(self, content: str) -> Dict[str, Optional[str]]:
        """Extract main contact information from the content."""
        main_section = content.split('**Úřední hodiny:**')[0]
        
        return {
            'name': 'Obec Ořechov',
            'address': next((m.group(0) for m in re.finditer(r'Zahradní[^\n]+', main_section)), None),
            'phone': next((m.group(1) for m in re.finditer(r'Tel\.:\s*([^\n]+)', main_section)), None),
            'mobile': next((m.group(1) for m in re.finditer(r'Mobil:\s*([^\n]+)', main_section)), None),
            'email': next((m.group(1) for m in re.finditer(r'E-mail:\s*([^\n]+)', main_section)), None),
            'maintenance': next((m.group(1) for m in re.finditer(r'Údržba obce:\s*([^\n]+)', main_section)), None),
            'data_id': next((m.group(1) for m in re.finditer(r'ID datové schránky:\s*([^\n]+)', main_section)), None),
            'ic': next((m.group(1) for m in re.finditer(r'IČ:\s*([^\n]+)', main_section)), None),
            'dic': next((m.group(1) for m in re.finditer(r'DIČ:\s*([^\n]+)', main_section)), None),
            'bank_account': next((m.group(1) for m in re.finditer(r'č\.ú\.:\s*([^\n]+)', main_section)), None),
        }

    def fetch_and_parse_contact(self) -> Contact:
        """Fetch and parse contact information from the API."""
        response = requests.get(self.API_URL)
        response.raise_for_status()
        content = response.json()['content']

        main_data = self.parse_main_content(content)
        office_hours = self.parse_office_hours(content)
        employees = self.parse_employees(content)

        # Debug output
        print("\nParsed content:")
        print(f"Main data: {main_data}")
        print("\nOffice hours:")
        for hours in office_hours:
            print(f"  {hours['days']}: {hours['time']}")
        print("\nEmployees:")
        for emp in employees:
            print(f"  {emp['name']} - {emp['position']}")

        return {
            **main_data,
            'office_hours': office_hours,
            'employees': employees
        }

    def ensure_tables_exist(self) -> None:
        """Ensure all required database tables exist."""
        with psycopg2.connect(**self.db_params) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'contact'
                    );
                """)
                tables_exist = cur.fetchone()[0]

                if not tables_exist:
                    print("Creating necessary tables...")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS contact (
                            id SERIAL PRIMARY KEY,
                            "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            name TEXT NOT NULL,
                            address TEXT,
                            phone TEXT,
                            mobile TEXT,
                            email TEXT,
                            maintenence TEXT,
                            data_id TEXT,
                            ic TEXT,
                            dic TEXT,
                            bank_account TEXT,
                            last_updated TIMESTAMP WITH TIME ZONE NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS "OfficeHours" (
                            id SERIAL PRIMARY KEY,
                            days TEXT NOT NULL,
                            time TEXT NOT NULL,
                            "contactId" INTEGER NOT NULL,
                            CONSTRAINT "OfficeHours_contactId_fkey"
                                FOREIGN KEY("contactId")
                                REFERENCES contact(id)
                                ON DELETE RESTRICT
                                ON UPDATE CASCADE
                        );

                        CREATE TABLE IF NOT EXISTS employees (
                            id SERIAL PRIMARY KEY,
                            name TEXT NOT NULL,
                            position TEXT,
                            phone TEXT,
                            email TEXT,
                            "contactId" INTEGER NOT NULL,
                            CONSTRAINT "employees_contactId_fkey"
                                FOREIGN KEY("contactId")
                                REFERENCES contact(id)
                                ON DELETE RESTRICT
                                ON UPDATE CASCADE
                        );
                    """)
                    conn.commit()
                    print("Tables created successfully!")

    def update_database(self, contact_data: Contact) -> None:
        """Update the database with new contact information."""
        with psycopg2.connect(**self.db_params) as conn:
            with conn.cursor() as cur:
                try:
                    # Check if contact exists
                    cur.execute("SELECT id FROM contact WHERE id = 1")
                    contact_exists = cur.fetchone() is not None

                    if contact_exists:
                        # Update existing contact
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
                        # Insert new contact
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
                    print(f"Updated contact with ID {contact_id}")
                    print(f"Inserted {len(contact_data['office_hours'])} office hours records")
                    print(f"Inserted {len(contact_data['employees'])} employee records")

                except Exception as e:
                    conn.rollback()
                    raise e

    def run(self) -> None:
        """Run the contact update process."""
        try:
            print("Starting contact data update...")
            self.ensure_tables_exist()
            contact_data = self.fetch_and_parse_contact()
            self.update_database(contact_data)
            print("Contact data updated successfully!")
        except requests.RequestException as e:
            print(f"Error fetching data from API: {e}")
        except psycopg2.Error as e:
            print(f"Database error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

def main():
    updater = ContactUpdater()
    updater.run()

if __name__ == "__main__":
    main()
