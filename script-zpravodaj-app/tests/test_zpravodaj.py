import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
import json
from pathlib import Path
import firebase_admin
from firebase_admin import credentials, db
import logging
import sys
import os
from bs4 import BeautifulSoup
import requests
from datetime import datetime
from io import StringIO

# We need to import files from parent directory
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

from newspapers_to_app_sync import NewspaperUpdater, NewspaperItem

class TestNewspapers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure logging to use a null handler
        logging.getLogger('newspapers_sync').addHandler(logging.NullHandler())

    def setUp(self):
        # Mock config content
        self.mock_config = {
            'Database': {
                'database_url': 'mock://database.url',
                'credentials_path': 'mock_credentials.json'
            },
            'Application': {
                'url': 'https://test.url',
                'firebase_route': 'newspapers',
                'scrape_element': 'li'
            },
            'Logging': {
                'directory': 'logs',
                'filename': 'test.log'
            }
        }

        # Sample HTML content for testing
        self.sample_html = """
        <ul>
            <li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj 1/2024</a></li>
            <li><a href="/zpravodaj2023_12.pdf">Ořechovský zpravodaj 12/2023</a></li>
            <li><a href="/zpravodaj_brezen_2023.pdf">Ořechovský zpravodaj březen 2023</a></li>
            <li><a href="/other.pdf">Some other document</a></li>
        </ul>
        """

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

        # Setup logging mock
        self.logging_patcher = patch('logging.FileHandler')
        mock_handler = self.logging_patcher.start()
        mock_handler.return_value = logging.NullHandler()

        # Setup firebase mock
        self.firebase_patcher = patch('firebase_admin.initialize_app')
        self.firebase_patcher.start()

        # Mock credentials
        self.cred_patcher = patch('firebase_admin.credentials.Certificate')
        self.cred_patcher.start()
        
        self.makedirs_patcher = patch('os.makedirs')
        self.makedirs_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        self.path_exists_patcher.stop()
        self.mkdir_patcher.stop()
        self.logging_patcher.stop()
        self.firebase_patcher.stop()
        self.cred_patcher.stop()
        self.makedirs_patcher.stop()

    def test_parse_newspaper_item_valid_numeric(self):
        updater = NewspaperUpdater()
        soup = BeautifulSoup('<li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj 1/2024</a></li>', 'html.parser')
        item = updater._parse_newspaper_item(soup.li)
        
        self.assertIsNotNone(item)
        self.assertEqual(item.year, 2024)
        self.assertEqual(item.release, 1)
        self.assertEqual(item.id, 202401)
        self.assertEqual(item.link, 'https://www.orechovubrna.cz/zpravodaj2024_01.pdf')

    def test_parse_newspaper_item_valid_month(self):
        updater = NewspaperUpdater()
        soup = BeautifulSoup('<li><a href="/zpravodaj_brezen_2023.pdf">Ořechovský zpravodaj březen 2023</a></li>', 'html.parser')
        item = updater._parse_newspaper_item(soup.li)
        
        self.assertIsNotNone(item)
        self.assertEqual(item.year, 2023)
        self.assertEqual(item.release, 3)  # March = 3
        self.assertEqual(item.id, 202303)
        self.assertEqual(item.link, 'https://www.orechovubrna.cz/zpravodaj_brezen_2023.pdf')

    def test_parse_newspaper_item_invalid(self):
        updater = NewspaperUpdater()
        soup = BeautifulSoup('<li><a href="/other.pdf">Some other document</a></li>', 'html.parser')
        item = updater._parse_newspaper_item(soup.li)
        
        self.assertIsNone(item)
        
    def test_parse_newspaper_item_alternative_formats(self):
        """Test various date format variations"""
        updater = NewspaperUpdater()
        test_cases = [
            ('<li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj leden 2024</a></li>', (2024, 1)),
            ('<li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj ledna 2024</a></li>', (2024, 1)),
            ('<li><a href="/zpravodaj2024_03.pdf">Ořechovský zpravodaj březen 2024</a></li>', (2024, 3)),
            ('<li><a href="/zpravodaj2024_03.pdf">Ořechovský zpravodaj března 2024</a></li>', (2024, 3))
        ]
        
        for html, expected in test_cases:
            soup = BeautifulSoup(html, 'html.parser')
            item = updater._parse_newspaper_item(soup.li)
            
            self.assertIsNotNone(item, f"Failed to parse: {html}")
            self.assertEqual(item.year, expected[0], f"Wrong year for: {html}")
            self.assertEqual(item.release, expected[1], f"Wrong release for: {html}")

    def test_parse_newspaper_item_invalid_month(self):
        """Test invalid month names"""
        updater = NewspaperUpdater()
        soup = BeautifulSoup('<li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj - invalidmonth 2024</a></li>', 'html.parser')
        item = updater._parse_newspaper_item(soup.li)
        
        self.assertIsNone(item)

    @patch('requests.get')
    def test_fetch_newspapers_empty_response(self, mock_get):
        """Test handling of empty response from website"""
        mock_response = Mock()
        mock_response.text = ""
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNone(results)

    @patch('requests.get')
    def test_fetch_newspapers_encoding(self, mock_get):
        """Test handling of different text encodings"""
        mock_response = Mock()
        mock_response.text = '<li><a href="/zpravodaj2024_01.pdf">Ořechovský zpravodaj 1/2024</a></li>'
        mock_response.encoding = 'iso-8859-2'  # Test different encoding
        mock_get.return_value = mock_response

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)

    @patch('firebase_admin.db.reference')
    def test_compare_and_update_no_changes(self, mock_db_ref):
        """Test when no changes are detected"""
        mock_ref = Mock()
        mock_db_ref.return_value = mock_ref
        
        link = "https://www.orechovubrna.cz/test.pdf"
        new_items = [
            NewspaperItem(202401, link, 1, 2024, logging.getLogger('test'))
        ]
        existing_data = {
            202401: {"id": 202401, "year": 2024, "release": 1, "link": link}
        }
        
        updater = NewspaperUpdater()
        updater.compare_and_update(new_items, existing_data)
        
        mock_ref.child().set.assert_not_called()
        mock_ref.child().child().set.assert_not_called()

    def test_invalid_config_missing_required_field(self):
        """Test handling of missing required configuration fields"""
        invalid_config = self.mock_config.copy()
        del invalid_config['Application']['firebase_route']
        
        with patch.dict(self.mock_config, invalid_config):
            with self.assertRaises(KeyError):
                NewspaperUpdater()


    @patch('requests.get')
    def test_fetch_newspapers_success(self, mock_get):
        mock_response = Mock()
        mock_response.text = self.sample_html
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 3)  # Should find 3 valid newspapers
        self.assertIsInstance(results[0], NewspaperItem)

    @patch('requests.get')
    def test_fetch_newspapers_request_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Network error")

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNone(results)

    def test_get_existing_data_success(self):
        mock_ref = Mock()
        mock_ref.get.return_value = {
            "202401": {"id": 202401, "year": 2024, "release": 1, "link": "test.pdf"},
            "202312": {"id": 202312, "year": 2023, "release": 12, "link": "test2.pdf"}
        }

        with patch('firebase_admin.db.reference', return_value=mock_ref):
            updater = NewspaperUpdater()
            data = updater.get_existing_data()

            self.assertEqual(len(data), 2)
            self.assertIn(202401, data)
            self.assertIn(202312, data)

    def test_get_existing_data_empty(self):
        mock_ref = Mock()
        mock_ref.get.return_value = None

        with patch('firebase_admin.db.reference', return_value=mock_ref):
            updater = NewspaperUpdater()
            data = updater.get_existing_data()

            self.assertEqual(data, {})

    @patch('firebase_admin.db.reference')
    def test_compare_and_update_new_items(self, mock_db_ref):
        mock_ref = Mock()
        mock_db_ref.return_value = mock_ref
        
        new_items = [
            NewspaperItem(202401, "test.pdf", 1, 2024, logging.getLogger('test'))
        ]
        existing_data = {}
        
        updater = NewspaperUpdater()
        updater.compare_and_update(new_items, existing_data)
        
        mock_ref.child.assert_called_with("202401")
        mock_ref.child().set.assert_called_once()

    @patch('firebase_admin.db.reference')
    def test_compare_and_update_modified_link(self, mock_db_ref):
        mock_ref = Mock()
        mock_db_ref.return_value = mock_ref
        
        # Use complete URL in new_items
        new_items = [
            NewspaperItem(202401, "new_link.pdf", 1, 2024, logging.getLogger('test'))
        ]
        existing_data = {
            202401: {"id": 202401, "year": 2024, "release": 1, "link": "https://www.orechovubrna.cz/old_link.pdf"}
        }
        
        updater = NewspaperUpdater()
        updater.compare_and_update(new_items, existing_data)
        
        mock_ref.child.assert_called_with("202401")
        mock_ref.child().child.assert_called_with("link")
        # Test with complete URL
        mock_ref.child().child().set.assert_called_with("https://www.orechovubrna.cz/new_link.pdf")

    def test_newspaper_item_validation(self):
        """Test NewspaperItem validation with various inputs"""
        # Create a logger that writes to a StringIO buffer
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger('test_validation')
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        
        # Test valid input
        item = NewspaperItem(202401, "test.pdf", 1, 2024, logger)
        self.assertEqual(item.id, 202401)
        
        # Test invalid year
        with self.assertRaises(ValueError):
            NewspaperItem(202401, "test.pdf", 1, 2050, logger)
        
        # Test invalid release number
        with self.assertRaises(ValueError):
            NewspaperItem(202413, "test.pdf", 13, 2024, logger)
        
        # Test invalid link format
        with self.assertRaises(ValueError):
            NewspaperItem(202401, "test.doc", 1, 2024, logger)
        
        # Clean up
        logger.removeHandler(handler)
        handler.close()

    def test_config_loader_missing_config(self):
        with patch.object(Path, 'exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                NewspaperUpdater('nonexistent/config.txt')

    @patch('requests.get')
    def test_fetch_newspapers_no_valid_items(self, mock_get):
        mock_response = Mock()
        mock_response.text = "<ul><li><a href='/other.pdf'>Not a newspaper</a></li></ul>"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNone(results)

    @patch('requests.get')
    def test_fetch_newspapers_malformed_html(self, mock_get):
        mock_response = Mock()
        mock_response.text = "Invalid HTML content"
        mock_response.encoding = 'utf-8'
        mock_get.return_value = mock_response

        updater = NewspaperUpdater()
        results = updater.fetch_newspapers()

        self.assertIsNone(results)

if __name__ == '__main__':
    os.chdir(current_dir)
    unittest.main()