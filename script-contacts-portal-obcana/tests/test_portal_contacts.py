import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
import json
from pathlib import Path
import psycopg2
import logging
import sys
import os
from datetime import datetime
import requests

# We need to import files from parent directory
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

from contacts_to_portal_obcana_sync import ContactUpdater, Employee, OfficeHours, Contact

class TestPortalContacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure logging to use a null handler instead of file handler
        logging.getLogger('portal_contacts_sync').addHandler(logging.NullHandler())

    def setUp(self):
        # Load sample API response
        try:
            with open('api_samples/generalApi.txt', 'r', encoding='utf-8') as f:
                content = f.read()
                self.api_response = content
        except FileNotFoundError:
            print("Warning: Sample file generalApi.txt not found")
            self.api_response = ""

        # Mock config content
        self.mock_config = {
            'API': {
                'url': 'https://test.url'
            },
            'SSL': {
                'with_ssl': 'False',
                'directory': 'ssl'
            },
            'Logs': {
                'directory': 'logs',
                'filename': 'test.log'
            }
        }

        # Setup environment variables
        self.env_vars = {
            'DB_NAME': 'test_db',
            'DB_USER': 'test_user',
            'DB_PASSWORD': 'test_pass',
            'DB_HOST': 'localhost',
            'DB_PORT': '5432'
        }

        # Create patcher for environment variables
        self.env_patcher = patch.dict('os.environ', self.env_vars)
        self.env_patcher.start()

        # Setup config parser mock
        self.config_patcher = patch('configparser.ConfigParser')
        self.mock_config_parser = self.config_patcher.start()
        mock_parser = self.mock_config_parser.return_value
        mock_parser.__getitem__.side_effect = self.mock_config.__getitem__
        mock_parser.read.return_value = None

        # Setup path exists mock
        self.path_exists_patcher = patch.object(Path, 'exists', return_value=True)
        self.path_exists_patcher.start()

        # Setup mkdir mock
        self.mkdir_patcher = patch.object(Path, 'mkdir')
        self.mkdir_patcher.start()

        # Setup complete mock for logging
        self.logging_patcher = patch('logging.FileHandler')
        mock_handler = self.logging_patcher.start()
        mock_handler.return_value = logging.NullHandler()
        
        self.makedirs_patcher = patch('os.makedirs')
        self.makedirs_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        self.config_patcher.stop()
        self.path_exists_patcher.stop()
        self.mkdir_patcher.stop()
        self.logging_patcher.stop()
        self.makedirs_patcher.stop()

    def test_parse_office_hours_valid(self):
        updater = ContactUpdater()
        content = """**Úřední hodiny:**\r\n Pondělí a středa: 8:00 - 12:00 hod., 13:00 - 17:00 hod.\r\n Úterý a čtvrtek: 8:00 - 12:00 hod., 13:00 - 15:00 hod.\r\n Pátek: ZAVŘENO\r\n\r\n.[stack]"""

        result = updater.parse_office_hours(content)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['days'], 'Pondělí a středa')
        self.assertEqual(result[0]['time'], '8:00 - 12:00 hod., 13:00 - 17:00 hod.')
        self.assertEqual(result[1]['days'], 'Úterý a čtvrtek')
        self.assertEqual(result[1]['time'], '8:00 - 12:00 hod., 13:00 - 15:00 hod.')
        self.assertEqual(result[2]['days'], 'Pátek')
        self.assertEqual(result[2]['time'], 'ZAVŘENO')

    def test_parse_office_hours_empty(self):
        updater = ContactUpdater()
        result = updater.parse_office_hours("")
        self.assertEqual(result, [])

    def test_parse_employees_valid(self):
        updater = ContactUpdater()
        content = """| **DUDÍK Tomáš** | starosta | +420 736 537 231 | starosta@orechovubrna.cz
            | **SMIŠTÍK Pavel** | místostarosta obce | +420 731 521 787 | mistostarosta@orechovubrna.cz"""

        result = updater.parse_employees(content)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'DUDÍK Tomáš')
        self.assertEqual(result[0]['position'], 'starosta')
        self.assertEqual(result[0]['phone'], '+420 736 537 231')
        self.assertEqual(result[0]['email'], 'starosta@orechovubrna.cz')

    def test_parse_employees_invalid(self):
        updater = ContactUpdater()
        with self.assertRaises(ValueError):
            updater.parse_employees("")

    def test_parse_main_content_valid(self):
        updater = ContactUpdater()
        content = """**Obec Ořechov**
            Zahradní 216/1
            664 44 Ořechov

            Tel.: +420 547 225 131
            Mobil: +420 731 414 473
            E-mail: obec@orechovubrna.cz
            Údržba obce: udrzba@orechovubrna.cz
            ID datové schránky: bmbbcae
            IČ: 00282278
            DIČ: CZ00282278
            č.ú.: FIO banka 2502224783/2010

            **Úřední hodiny:**"""

        result = updater.parse_main_content(content)

        self.assertEqual(result['name'], 'Obec Ořechov')
        self.assertEqual(result['phone'], '+420 547 225 131')
        self.assertEqual(result['mobile'], '+420 731 414 473')
        self.assertEqual(result['email'], 'obec@orechovubrna.cz')
        self.assertEqual(result['maintenance'], 'udrzba@orechovubrna.cz')
        self.assertEqual(result['ic'], '00282278')

    def test_parse_main_content_invalid(self):
        updater = ContactUpdater()
        with self.assertRaises(ValueError):
            updater.parse_main_content("")

    @patch('requests.get')
    def test_fetch_and_parse_contact_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {'content': self.api_response}
        mock_get.return_value = mock_response

        updater = ContactUpdater()
        result = updater.fetch_and_parse_contact()

        self.assertIsInstance(result, dict)
        self.assertIn('name', result)
        self.assertIn('office_hours', result)
        self.assertIn('employees', result)

    @patch('requests.get')
    def test_fetch_and_parse_contact_api_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("API Error")
        
        updater = ContactUpdater()
        with self.assertRaises(requests.RequestException):
            updater.fetch_and_parse_contact()

    @patch('psycopg2.connect')
    def test_ensure_tables_exist_success(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [True]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        updater = ContactUpdater()
        updater.ensure_tables_exist()

        # Verify that cursor.execute was called for each table check
        self.assertEqual(mock_cursor.execute.call_count, 3)

    @patch('psycopg2.connect')
    def test_ensure_tables_exist_missing_table(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [False]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        updater = ContactUpdater()
        with self.assertRaises(ValueError):
            updater.ensure_tables_exist()

    @patch('psycopg2.connect')
    def test_update_database_new_contact(self, mock_connect):
        mock_cursor = MagicMock()
        # First fetchone for checking if contact exists
        mock_cursor.fetchone.side_effect = [
            None,  # First call returns None (no existing contact)
            [1],   # Second call returns [1] (new contact ID)
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        test_contact: Contact = {
            'name': 'Test Contact',
            'address': 'Test Address',
            'phone': '123456789',
            'mobile': '987654321',
            'email': 'test@test.com',
            'maintenance': 'maintenance@test.com',
            'data_id': 'TEST123',
            'ic': '12345',
            'dic': 'CZ12345',
            'bank_account': '123456789/0000',
            'office_hours': [{'days': 'Monday', 'time': '8-16'}],
            'employees': [{
                'name': 'John Doe',
                'position': 'Manager',
                'phone': '123123123',
                'email': 'john@test.com'
            }]
        }

        updater = ContactUpdater()
        updater.update_database(test_contact)

        # Verify the cursor executed the correct SQL statements
        execute_calls = mock_cursor.execute.call_args_list
        
        # Verify INSERT INTO contact was called
        insert_calls = [call for call in execute_calls if 'INSERT INTO contact' in str(call)]
        self.assertGreaterEqual(len(insert_calls), 1)
        
        # Verify DELETE operations were called before inserts for office_hours and employees
        delete_calls = [call for call in execute_calls if 'DELETE FROM' in str(call)]
        self.assertEqual(len(delete_calls), 2)  # One for office_hours, one for employees
        
        # Verify executemany was called for office_hours and employees
        executemany_calls = mock_cursor.executemany.call_args_list
        self.assertEqual(len(executemany_calls), 2)  # One for office_hours, one for employees

    @patch('psycopg2.connect')
    def test_update_database_existing_contact(self, mock_connect):
        mock_cursor = MagicMock()
        # Mock the fetchone call to indicate an existing contact
        mock_cursor.fetchone.return_value = [1]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        test_contact: Contact = {
            'name': 'Test Contact',
            'address': 'Test Address',
            'phone': '123456789',
            'mobile': '987654321',
            'email': 'test@test.com',
            'maintenance': 'maintenance@test.com',
            'data_id': 'TEST123',
            'ic': '12345',
            'dic': 'CZ12345',
            'bank_account': '123456789/0000',
            'office_hours': [{'days': 'Monday', 'time': '8-16'}],
            'employees': [{
                'name': 'John Doe',
                'position': 'Manager',
                'phone': '123123123',
                'email': 'john@test.com'
            }]
        }

        updater = ContactUpdater()
        updater.update_database(test_contact)

        # Verify the UPDATE statement was executed
        update_calls = [call for call in mock_cursor.execute.call_args_list 
                       if 'UPDATE contact' in str(call)]
        self.assertGreaterEqual(len(update_calls), 1)

    def test_ssl_verification(self):
        self.mock_config['SSL']['with_ssl'] = 'True'
        
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaises(FileNotFoundError):
                ContactUpdater()

    def test_config_loader_missing_config(self):
        with patch.object(Path, 'exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                ContactUpdater('nonexistent/config.txt')

if __name__ == '__main__':
    os.chdir(current_dir)
    unittest.main()