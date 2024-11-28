import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
import json
from pathlib import Path
import firebase_admin
import logging
import sys
import importlib.util
import re
from contacts_to_app_API import ConfigLoader, ContactDataUpdater, setup_main_logger
from contact_item import ContactItem
from parsers import *

class TestParsers(unittest.TestCase):
    def setUp(self):
        self.mock_main_logger = Mock(spec=logging.Logger)
        self.mock_logger = Mock(spec=logging.Logger)
        
        # Load sample API responses
        self.api_responses = {}
        api_files = [
            'hasiciApi.txt', 'knihovnaApi.txt', 'lekariApi.txt',
            'postaApi.txt', 'skolyApi.txt', 'generalApi.txt'
        ]
        
        for file in api_files:
            try:
                with open(f'api_samples/{file}', 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Extract content from JSON structure and decode Unicode sequences
                    match = re.search(r'{"content":"(.*?)"}$', content, re.DOTALL)
                    if match:
                        content = match.group(1)
                        content = content.replace('\\/', '/')  # Fix escape sequence warning
                        content = content.encode().decode('unicode_escape').replace('\\r\\n', '\r\n')
                        self.api_responses[file] = content
            except FileNotFoundError:
                print(f"Warning: Sample file {file} not found")

    def test_parse_school_data_valid(self):
        result = parse_school_data(self.api_responses['skolyApi.txt'], 
                                 self.mock_main_logger, 
                                 self.mock_logger)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Základní škola a Mateřská škola Ořechov")
        self.assertEqual(result[0].phone, "+420 547 225 121")
        self.assertEqual(result[0].mail, "zs_orechov@volny.cz")
        self.assertEqual(result[0].web, "www.zsorechov.cz")

    def test_parse_school_data_empty(self):
        with self.assertRaises(ValueError):
            parse_school_data("", self.mock_main_logger, self.mock_logger)

    def test_parse_school_data_invalid(self):
        with self.assertRaises(ValueError):
            parse_school_data("Invalid content", self.mock_main_logger, self.mock_logger)

    def test_parse_general_contact_valid(self):
        result = parse_general_contact(self.api_responses['generalApi.txt'],
                                     self.mock_main_logger,
                                     self.mock_logger)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Obec Ořechov")
        self.assertEqual(result[0].phone, "+420 547 225 131")
        self.assertEqual(result[0].phone2, "+420 731 414 473")
        self.assertEqual(result[0].mail, "obec@orechovubrna.cz")
        self.assertEqual(result[0].maintenance, "udrzba@orechovubrna.cz")

    def test_parse_general_contact_empty(self):
        with self.assertRaises(ValueError):
            parse_general_contact("", self.mock_main_logger, self.mock_logger)
    
    def test_parse_town_hall_contact_valid(self):
        result = parse_town_hall_contact(self.api_responses['generalApi.txt'],
                                       self.mock_main_logger,
                                       self.mock_logger)
        
        # Check that we got the expected number of contacts
        self.assertTrue(len(result) > 0, "Should have found at least one town hall contact")
        
        # Test for specific known contacts
        expected_contacts = {
            "DUDÍK Tomáš": {
                "subtitle": "starosta",
                "phone": "+420 736 537 231",
                "mail": "starosta@orechovubrna.cz"
            },
            "HRUBÁ Ivona": {
                "subtitle": "evidence obyvatel",
                "phone": "+420 547 225 131",
                "mail": "ekonom@orechovubrna.cz"
            }
        }
        
        # Create a dictionary of results for easier lookup
        result_dict = {contact.title: contact for contact in result}
        
        # Test each expected contact
        for name, expected_data in expected_contacts.items():
            self.assertIn(name, result_dict, f"Contact {name} should be present")
            contact = result_dict[name]
            self.assertEqual(contact.subtitle, expected_data["subtitle"],
                           f"Wrong subtitle for {name}")
            self.assertEqual(contact.phone, expected_data["phone"],
                           f"Wrong phone for {name}")
            self.assertEqual(contact.mail, expected_data["mail"],
                           f"Wrong email for {name}")

    def test_parse_town_hall_contact_empty(self):
        with self.assertRaises(ValueError):
            parse_town_hall_contact("", self.mock_main_logger, self.mock_logger)

    def test_parse_town_hall_contact_invalid(self):
        invalid_data = "**Some Title**\nInvalid content without proper structure"
        with self.assertRaises(ValueError):
            parse_town_hall_contact(invalid_data, self.mock_main_logger, self.mock_logger)

    def test_parse_town_hall_contact_malformed(self):
        malformed_data = "| **Name** | Position | Invalid phone Invalid email"
        with self.assertRaises(ValueError):
            parse_town_hall_contact(malformed_data, self.mock_main_logger, self.mock_logger)

    def test_parse_post_office_data_valid(self):
        result = parse_post_office_data(self.api_responses['postaApi.txt'],
                                      self.mock_main_logger,
                                      self.mock_logger)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Pošta Ořechov u Brna")
        self.assertEqual(result[0].phone, "+420 954 266 444")
        self.assertTrue("Zahradní" in result[0].address and "216/1" in result[0].address)

    def test_parse_firemen_data_valid(self):
        result = parse_firemen_data(self.api_responses['hasiciApi.txt'],
                                  self.mock_main_logger,
                                  self.mock_logger)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Sbor dobrovolných hasičů Ořechov")
        self.assertEqual(result[0].phone, "+420 777 283 527")
        self.assertEqual(result[0].mail, "sdhorechov@seznam.cz")
        self.assertEqual(result[0].web, "www.hasiciorechov.cz")

    def test_parse_library_data_valid(self):
        result = parse_library_data(self.api_responses['knihovnaApi.txt'],
                                  self.mock_main_logger,
                                  self.mock_logger)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Obecní knihovna Ořechov")
        self.assertEqual(result[0].phone, "+420 732 822 748")

    def test_parse_doctors_data_valid(self):
        result = parse_doctors_data(self.api_responses['lekariApi.txt'],
                                  self.mock_main_logger,
                                  self.mock_logger)
        
        self.assertTrue(len(result) > 0)
        for doctor in result:
            self.assertFalse("Lékárna" in doctor.title)
            self.assertTrue(doctor.title and doctor.subtitle)  # Ensure basic fields are present

    def test_parse_drug_store_data_valid(self):
        result = parse_drug_store_data(self.api_responses['lekariApi.txt'],
                                     self.mock_main_logger,
                                     self.mock_logger)
        
        self.assertEqual(len(result), 1)
        self.assertTrue("EUPHRASIA" in result[0].title)
        self.assertTrue(result[0].phone and result[0].address)  # Check essential fields

    def test_parser_error_handling_for_single_contact(self):
        """Test error handling in all parsers with invalid input"""
        invalid_inputs = [
            "",  # Empty input
            "Invalid Data",  # No proper structure
            "**Title**\nInvalid content",  # Missing required fields
        ]
        
        parsers_to_test = [
            ('parse_general_contact', parse_general_contact,),
        ]
        
        for parser_name, parser_func in parsers_to_test:
            for invalid_input in invalid_inputs:
                with self.subTest(parser=parser_name, input=invalid_input):
                    with self.assertRaises(
                        ValueError,
                        msg=f"{parser_name} should raise ValueError for invalid input: {invalid_input}"
                    ):
                        parser_func(invalid_input, self.mock_main_logger, self.mock_logger)
    
    def test_parser_error_handling_for_multiple_contacts(self):
        """Test error handling in all parsers with invalid input"""
        invalid_inputs = [
            "",  # Empty input
            "Invalid Data",  # No proper structure
        ]
        
        parsers_to_test = [
            ('parse_school_data', parse_school_data),
            ('parse_firemen_data', parse_firemen_data),
            ('parse_library_data', parse_library_data),
            ('parse_post_office_data', parse_post_office_data)
        ]
        
        for parser_name, parser_func in parsers_to_test:
            for invalid_input in invalid_inputs:
                with self.subTest(parser=parser_name, input=invalid_input):
                    with self.assertRaises(
                        ValueError,
                        msg=f"{parser_name} should raise ValueError for invalid input: {invalid_input}"
                    ):
                        parser_func(invalid_input, self.mock_main_logger, self.mock_logger)


class TestDataConfig(unittest.TestCase):
    def setUp(self):
        with open('config/data_config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def test_config_structure(self):
        required_keys = ['firebase_route', 'log_name', 'api_url', 'parser_function']
        
        for contact_type, settings in self.config.items():
            for key in required_keys:
                self.assertIn(key, settings, 
                            f"Missing required key '{key}' in {contact_type} configuration")

    def test_parser_functions_exist(self):
        for contact_type, settings in self.config.items():
            parser_name = settings['parser_function']
            self.assertIn(parser_name, PARSER_FUNCTIONS,
                         f"Parser function '{parser_name}' for {contact_type} not found")

    def test_firebase_routes_unique(self):
        routes = [settings['firebase_route'] for settings in self.config.values()]
        self.assertEqual(len(routes), len(set(routes)), 
                        "Firebase routes must be unique")

    def test_log_names_valid(self):
        for contact_type, settings in self.config.items():
            self.assertTrue(settings['log_name'].endswith('.log'),
                          f"Log name for {contact_type} must end with .log")

    def test_api_urls_valid(self):
        for contact_type, settings in self.config.items():
            self.assertTrue(settings['api_url'].startswith('https://'),
                          f"API URL for {contact_type} must be HTTPS")


class TestContactsToApp(unittest.TestCase):
    @patch('configparser.ConfigParser')
    @patch('firebase_admin.credentials')
    @patch('firebase_admin.initialize_app')
    @patch('importlib.util.spec_from_file_location')
    def setUp(self, mock_spec, mock_firebase_init, mock_cred, mock_config_parser):
        # Setup mock parser module
        mock_module = Mock()
        mock_module.PARSER_FUNCTIONS = PARSER_FUNCTIONS
        mock_spec_obj = Mock()
        mock_spec_obj.loader = Mock()
        mock_spec.return_value = mock_spec_obj
        mock_spec_obj.loader.exec_module = lambda x: None
        
        # Setup mock config
        mock_config = {
            'Database': {
                'database_url': 'mock://database.url',
                'credentials_path': 'mock_credentials.json'
            },
            'Files': {
                'data_config': 'data_config.json',
                'parsers_module': 'parsers.py'
            },
            'Logs': {
                'directory': 'logs',
                'main': 'main.log'
            }
        }
        
        # Mock ConfigParser
        mock_parser = mock_config_parser.return_value
        mock_parser.__getitem__.side_effect = mock_config.__getitem__
        mock_parser.read.return_value = None
        
        # Setup mock file operations
        mock_data_config = {
            'test_type': {
                'firebase_route': 'test/route',
                'log_name': 'test.log',
                'api_url': 'http://test.url',
                'parser_function': 'parse_school_data'
            }
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_data_config))):
            with patch.object(Path, 'exists', return_value=True):
                with patch.object(Path, 'mkdir'):
                    with patch('json.load', return_value=mock_data_config):
                        self.config_loader = ConfigLoader()
                        self.config_loader.parser_functions = PARSER_FUNCTIONS
                        self.config_loader.data_config = mock_data_config
        
        # Setup logger mocks
        self.mock_logger = Mock(spec=logging.Logger)
        self.updater = ContactDataUpdater(self.config_loader, self.mock_logger)
        self.updater.logger = Mock(spec=logging.Logger)  # Add logger to updater

    @patch('logging.FileHandler')
    def test_set_contact_type_valid(self, mock_handler):
        test_config = {
            'test_type': {
                'firebase_route': 'test/route',
                'log_name': 'test.log',
                'api_url': 'http://test.url',
                'parser_function': 'parse_school_data'
            }
        }
        self.config_loader.data_config = test_config
        self.updater.set_contact_type('test_type')
        # Verify that logger was set up
        self.assertIsNotNone(self.updater.logger)

    def test_set_contact_type_invalid(self):
        self.config_loader.data_config = {}
        result = self.updater.set_contact_type('nonexistent_type')
        self.assertFalse(result)

    @patch('requests.get')
    def test_fetch_contact_data_success(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {'content': 'test content'}
        mock_get.return_value = mock_response
        
        self.updater.data_config = {'api_url': 'http://test.url'}
        self.updater.logger = Mock(spec=logging.Logger)  # Ensure logger is set
        result = self.updater.fetch_contact_data()
        self.assertEqual(result, 'test content')

    @patch('requests.get')
    def test_fetch_contact_data_failure(self, mock_get):
        mock_get.side_effect = Exception('Network error')
        
        self.updater.data_config = {'api_url': 'http://test.url'}
        self.updater.logger = Mock(spec=logging.Logger)  # Ensure logger is set
        result = self.updater.fetch_contact_data()
        self.assertIsNone(result)
        self.updater.logger.error.assert_called_once()
    
    @patch('requests.get')
    def test_fetch_contact_data_missing_content(self, mock_get):
        # Setup mock response with missing 'content' field
        mock_response = Mock()
        mock_response.json.return_value = {'data': 'test data', 'status': 'ok'}
        mock_get.return_value = mock_response
        
        self.updater.data_config = {'api_url': 'http://test.url'}
        self.updater.logger = Mock(spec=logging.Logger)
        
        # Test the fetch_contact_data method
        result = self.updater.fetch_contact_data()
        
        # Verify results
        self.assertIsNone(result)
        self.updater.logger.error.assert_called_once()
        self.assertTrue(any('Failed to fetch contact data' in str(call) for call in self.updater.logger.error.call_args_list))

    @patch('requests.get')
    def test_fetch_contact_data_empty_response(self, mock_get):
        # Setup mock response with empty response
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response
        
        self.updater.data_config = {'api_url': 'http://test.url'}
        self.updater.logger = Mock(spec=logging.Logger)
        
        # Test the fetch_contact_data method
        result = self.updater.fetch_contact_data()
        
        # Verify results
        self.assertIsNone(result)
        self.updater.logger.error.assert_called_once()
        self.assertTrue(any('Failed to fetch contact data' in str(call) for call in self.updater.logger.error.call_args_list))

    @patch('requests.get')
    def test_fetch_contact_data_malformed_json(self, mock_get):
        # Setup mock response with malformed JSON
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError('Malformed JSON', '', 0)
        mock_get.return_value = mock_response
        
        self.updater.data_config = {'api_url': 'http://test.url'}
        self.updater.logger = Mock(spec=logging.Logger)
        
        # Test the fetch_contact_data method
        result = self.updater.fetch_contact_data()
        
        # Verify results
        self.assertIsNone(result)
        self.updater.logger.error.assert_called_once()
        self.assertTrue(any('Failed to fetch contact data' in str(call) for call in self.updater.logger.error.call_args_list))

    @patch('firebase_admin.db.reference')
    def test_update_contacts_new_data(self, mock_db_ref):
        mock_ref = Mock()
        mock_db_ref.return_value = mock_ref
        
        new_contacts = [
            ContactItem(title="Test Contact", phone="123456789")
        ]
        existing_contacts = [None]
        
        self.updater.data_config = {'firebase_route': 'test/route'}
        self.updater.logger = Mock(spec=logging.Logger)
        
        result = self.updater.update_contacts(new_contacts, existing_contacts)
        
        # Verify the operation succeeded
        self.assertTrue(result)
        
        # Verify set() was called once
        mock_ref.set.assert_called_once()
        
        # Get what was actually passed to set()
        actual_data = mock_ref.set.call_args[0][0]
        
        # Verify the structure and content
        self.assertIsInstance(actual_data, list)
        self.assertEqual(len(actual_data), 2)  # [None, contact_data]
        self.assertIsNone(actual_data[0])
        
        # Verify the contact data
        contact_data = actual_data[1]
        self.assertEqual(contact_data['title'], "Test Contact")
        self.assertEqual(contact_data['phone'], "123456789")

    @patch('firebase_admin.db.reference')
    def test_update_contacts_modified_data(self, mock_db_ref):
        mock_ref = Mock()
        mock_db_ref.return_value = mock_ref
        
        # New contact data with updated email
        new_contacts = [
            ContactItem(title="Test Contact", phone="123456789", mail="new@test.com")
        ]
        # Existing data in database
        existing_contacts = [None, {
            'title': "Test Contact",
            'phone': "123456789",
            'mail': "old@test.com"
        }]
        
        self.updater.data_config = {'firebase_route': 'test/route'}
        self.updater.logger = Mock(spec=logging.Logger)
        
        result = self.updater.update_contacts(new_contacts, existing_contacts)
        
        # Verify the operation succeeded
        self.assertTrue(result)
        
        # Verify set() was called once
        mock_ref.set.assert_called_once()
        
        # Get what was actually passed to set()
        actual_data = mock_ref.set.call_args[0][0]
        
        # Verify the structure
        self.assertIsInstance(actual_data, list)
        self.assertEqual(len(actual_data), 2)
        self.assertIsNone(actual_data[0])
        
        # Verify the contact data
        updated_contact = actual_data[1]
        self.assertEqual(updated_contact['title'], "Test Contact")
        self.assertEqual(updated_contact['phone'], "123456789")
        self.assertEqual(updated_contact['mail'], "new@test.com")
        
        # Verify the logger recorded the modification
        self.updater.logger.info.assert_any_call("Modified contact: Test Contact")

    def test_setup_main_logger(self):
        with patch('logging.FileHandler'):
            logger = setup_main_logger(Path('test.log'))
            self.assertIsInstance(logger, logging.Logger)

    def test_config_loader_invalid_path(self):
        with patch('pathlib.Path.exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                ConfigLoader('nonexistent/path/config.txt')


if __name__ == '__main__':
    unittest.main()