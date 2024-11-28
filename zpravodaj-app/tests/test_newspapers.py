import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import firebase_admin
import requests
from bs4 import BeautifulSoup
import configparser
import re
import logging
import os
from newspapers_to_app_API import NewspaperItem, NewspaperUpdater

class LoggerContext:
    """Context manager for handling logger setup and cleanup"""
    def __init__(self, log_dir, log_file):
        self.log_dir = log_dir
        self.log_file = log_file
        self.handler = None
        self.logger = None

    def __enter__(self):
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Set up logger
        self.logger = logging.getLogger('test_logger')
        self.logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        self.logger.handlers = []
        
        # Add file handler
        self.handler = logging.FileHandler(
            os.path.join(self.log_dir, self.log_file),
            encoding='utf-8'
        )
        self.handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(self.handler)
        
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up handler
        if self.handler:
            self.handler.close()
            self.logger.removeHandler(self.handler)

class TestNewspaperItem(unittest.TestCase):
    """Tests for the NewspaperItem class"""
    
    def test_newspaper_item_creation(self):
        """Test creation of NewspaperItem objects"""
        item = NewspaperItem(
            id=202301,
            link="https://example.com/zpravodaj/2023/01",
            release=1,
            year=2023
        )
        
        self.assertEqual(item.id, 202301)
        self.assertEqual(item.link, "https://example.com/zpravodaj/2023/01")
        self.assertEqual(item.release, 1)
        self.assertEqual(item.year, 2023)

    def test_to_dict_conversion(self):
        """Test conversion of NewspaperItem to dictionary"""
        item = NewspaperItem(
            id=202301,
            link="https://example.com/zpravodaj/2023/01",
            release=1,
            year=2023
        )
        
        expected_dict = {
            'id': 202301,
            'link': "https://example.com/zpravodaj/2023/01",
            'release': 1,
            'year': 2023
        }
        
        self.assertEqual(item.to_dict(), expected_dict)

class TestNewspaperUpdater(unittest.TestCase):
    """Tests for the NewspaperUpdater class"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.test_config = """
[Database]
database_url = https://test-db.example.com
credentials_path = test_credentials.json

[Application]
url = https://www.orechovubrna.cz/api/zpravodaj
firebase_route = newspapers
scrape_element = li

[Logging]
directory = test_logs
filename = test_newspaper_sync.log
"""
        # Set up test directories
        cls.test_dir = Path("test_newspaper_sync")
        cls.test_dir.mkdir(exist_ok=True)
        
        cls.config_path = cls.test_dir / "test_config.ini"
        with open(cls.config_path, "w") as f:
            f.write(cls.test_config)
            
        # Set up logging directory
        cls.log_dir = cls.test_dir / "test_logs"
        cls.log_dir.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures"""
        # Remove test configuration
        if cls.config_path.exists():
            cls.config_path.unlink()
            
        # Remove log files
        if cls.log_dir.exists():
            for file in cls.log_dir.iterdir():
                file.unlink()
            cls.log_dir.rmdir()
            
        # Remove test directory
        if cls.test_dir.exists():
            cls.test_dir.rmdir()

    def setUp(self):
        """Set up test case"""
        self.patcher = patch('firebase_admin.credentials.Certificate')
        self.mock_cert = self.patcher.start()
        self.mock_cert.return_value = MagicMock()

    def tearDown(self):
        """Clean up after test case"""
        self.patcher.stop()

    def test_initialization(self):
        """Test proper initialization of NewspaperUpdater"""
        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                self.assertEqual(updater.newspapers_url, "https://www.orechovubrna.cz/api/zpravodaj")
                self.assertEqual(updater.firebase_route, "newspapers")

    @patch('requests.get')
    def test_fetch_newspapers(self, mock_get):
        """Test fetching newspapers from website"""
        mock_html = """
        <html><body><ul>
            <li><a href="/zpravodaj/2024/02">Ořechovský zpravodaj 2/2024</a></li>
            <li><a href="/zpravodaj/2024/01">Ořechovský zpravodaj 1/2024</a></li>
        </ul></body></html>
        """.encode('utf8').decode('latin1')
        
        mock_response = Mock()
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                with patch.object(updater, '_parse_newspaper_item') as mock_parse:
                    mock_parse.return_value = NewspaperItem(
                        id=202401,
                        link="https://example.com/zpravodaj/2024/01",
                        release=1,
                        year=2024
                    )
                    
                    newspapers = updater.fetch_newspapers()
                    self.assertIsNotNone(newspapers)
                    self.assertGreater(len(newspapers), 0)

    @patch('requests.get')
    def test_fetch_newspapers_error_handling(self, mock_get):
        """Test error handling when fetching newspapers fails"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")
        
        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                result = updater.fetch_newspapers()
                self.assertIsNone(result)

    def test_parse_newspaper_item_with_different_formats(self):
        """Test parsing newspaper items with different date formats"""
        test_cases = [
            {
                'html': '<li><a href="/zpravodaj/2024/01">Ořechovský zpravodaj 1/2024</a></li>',
                'expected': {'year': 2024, 'release': 1}
            },
            {
                'html': '<li><a href="/zpravodaj/2023/03">Ořechovský zpravodaj březen 2023</a></li>',
                'expected': {'year': 2023, 'release': 3}
            },
            {
                'html': '<li><a href="/zpravodaj/2023/06">Ořechovský zpravodaj červen 2023</a></li>',
                'expected': {'year': 2023, 'release': 6}
            }
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                for case in test_cases:
                    encoded_html = case['html'].encode('utf-8').decode('latin1')
                    soup = BeautifulSoup(encoded_html, 'html.parser')
                    li_element = soup.find('li')
                    
                    item = updater._parse_newspaper_item(li_element)
                    self.assertIsNotNone(item, f"Failed to parse: {case['html']}")
                    self.assertEqual(item.year, case['expected']['year'])
                    self.assertEqual(item.release, case['expected']['release'])

    @patch('firebase_admin.db.reference')
    def test_get_existing_data_error_handling(self, mock_ref):
        """Test error handling when fetching existing data fails"""
        mock_ref.return_value.get.side_effect = firebase_admin.exceptions.FirebaseError(
            code='PERMISSION_DENIED',
            message="Database error"
        )

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                existing_data = updater.get_existing_data()
                self.assertEqual(existing_data, {})
    
    @patch('firebase_admin.db.reference')
    def test_link_updates(self, mock_ref):
        """Test updating links for existing newspaper items"""
        existing_data = {
            202401: {
                'id': 202401,
                'link': 'https://www.orechovubrna.cz/old/zpravodaj/2024/01',
                'release': 1,
                'year': 2024
            }
        }
        
        new_items = [
            NewspaperItem(
                id=202401,
                link='https://www.orechovubrna.cz/new/zpravodaj/2024/01',
                release=1,
                year=2024
            )
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                # Mock the child and set methods
                mock_child = Mock()
                mock_ref.return_value.child.return_value = mock_child
                
                updater.compare_and_update(new_items, existing_data)
                
                # Verify that child method was called with correct ID
                mock_ref.return_value.child.assert_called_with("202401")
                # Verify that the link was updated
                mock_child.child.assert_called_with('link')
                mock_child.child().set.assert_called_with(
                    'https://www.orechovubrna.cz/new/zpravodaj/2024/01'
                )

    @patch('firebase_admin.db.reference')
    def test_preserve_existing_entries(self, mock_ref):
        """Test that update preserves existing entries not present in new data"""
        existing_data = {
            202401: {
                'id': 202401,
                'link': 'https://www.orechovubrna.cz/zpravodaj/2024/01',
                'release': 1,
                'year': 2024
            },
            202402: {
                'id': 202402,
                'link': 'https://www.orechovubrna.cz/zpravodaj/2024/02',
                'release': 2,
                'year': 2024
            }
        }
        
        new_items = [
            NewspaperItem(
                id=202401,
                link='https://www.orechovubrna.cz/zpravodaj/2024/01',
                release=1,
                year=2024
            ),
            NewspaperItem(
                id=202403,
                link='https://www.orechovubrna.cz/zpravodaj/2024/03',
                release=3,
                year=2024
            )
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                # Create a mock for the database reference
                mock_db_ref = Mock()
                mock_ref.return_value = mock_db_ref
                
                # Track the updates
                updates = {}
                
                def mock_child_set(key):
                    child_mock = Mock()
                    def set_value(value):
                        updates[key] = value
                    child_mock.set = Mock(side_effect=set_value)
                    return child_mock
                
                mock_db_ref.child = Mock(side_effect=mock_child_set)
                
                # Perform the update
                updater.compare_and_update(new_items, existing_data)
                
                # Verify that both old and new entries are preserved
                # We expect either set calls for new/modified items or the items to remain unchanged
                
                # Check that existing item 202401 is preserved
                self.assertTrue(
                    202401 in existing_data,
                    "Existing item 202401 should be preserved"
                )
                
                # Check that existing item 202402 is preserved
                self.assertTrue(
                    202402 in existing_data,
                    "Existing item 202402 should be preserved"
                )
                
                # Check that new item 202403 was added
                self.assertTrue(
                    any(call[0][0] == '202403' for call in mock_db_ref.child.call_args_list),
                    "New item 202403 should be added"
                )
                
                # Verify no entries were incorrectly removed
                all_calls = [call[0][0] for call in mock_db_ref.child.call_args_list]
                self.assertNotIn('202402', all_calls, 
                    "Existing item 202402 should not be modified")

    def test_parse_newspaper_invalid_formats_extended(self):
        """Test parsing newspaper items with various invalid formats"""
        invalid_cases = [
            # Empty li element
            '<li></li>',
            # Missing href
            '<li><a>Ořechovský zpravodaj 1/2024</a></li>',
            # Completely wrong format
            '<li><a href="/random">Some random text</a></li>',
            # Missing year
            '<li><a href="/zpravodaj">Ořechovský zpravodaj 1</a></li>',
            # Invalid year format
            '<li><a href="/zpravodaj">Ořechovský zpravodaj 1/ABC</a></li>',
            # Invalid month name
            '<li><a href="/zpravodaj">Ořechovský zpravodaj invalid_month 2024</a></li>',
            # Extra text
            '<li><a href="/zpravodaj">Extra text Ořechovský zpravodaj 1/2024 more text</a></li>',
            # Invalid characters in numbers
            '<li><a href="/zpravodaj">Ořechovský zpravodaj 1a/2024b</a></li>',
            # Multiple numbers
            '<li><a href="/zpravodaj">Ořechovský zpravodaj 1/2024/3</a></li>'
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                for html in invalid_cases:
                    soup = BeautifulSoup(html, 'html.parser')
                    li_element = soup.find('li')
                    item = updater._parse_newspaper_item(li_element)
                    self.assertIsNone(item, f"Should return None for invalid format: {html}")

    @patch('requests.get')
    def test_nonexistent_site(self, mock_get):
        """Test handling of nonexistent website"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                result = updater.fetch_newspapers()
                self.assertIsNone(result)

    @patch('requests.get')
    def test_site_without_li_elements(self, mock_get):
        """Test handling of website without li elements"""
        # Test various HTML structures without li elements
        test_cases = [
            # Empty HTML
            "",
            # Basic HTML without li
            "<html><body><p>Some text</p></body></html>",
            # Similar structure but no li
            "<html><body><ul><div>Item 1</div><div>Item 2</div></ul></body></html>",
            # Malformed HTML
            "<html><body><ul><</>></body></html>"
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                for html in test_cases:
                    mock_response = Mock()
                    mock_response.text = html
                    mock_response.raise_for_status = Mock()
                    mock_get.return_value = mock_response
                    
                    result = updater.fetch_newspapers()
                    self.assertIsNone(result, f"Should return None for HTML without li elements: {html}")

    @patch('requests.get')
    def test_invalid_http_responses(self, mock_get):
        """Test handling of various HTTP error responses"""
        error_cases = [
            (404, "Not Found"),
            (500, "Internal Server Error"),
            (403, "Forbidden"),
            (502, "Bad Gateway"),
            (504, "Gateway Timeout")
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                for status_code, error_msg in error_cases:
                    mock_get.return_value.raise_for_status.side_effect = (
                        requests.exceptions.HTTPError(f"{status_code} Client Error: {error_msg}")
                    )
                    
                    result = updater.fetch_newspapers()
                    self.assertIsNone(result, 
                        f"Should return None for HTTP {status_code} error")

    @patch('firebase_admin.db.reference')
    def test_compare_and_update_with_empty_data(self, mock_ref):
        """Test comparison and update with empty existing data"""
        existing_data = {}
        
        new_items = [
            NewspaperItem(
                id=202401,
                link="https://example.com/zpravodaj/2024/01",
                release=1,
                year=2024
            )
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                updater.compare_and_update(new_items, existing_data)
                mock_ref.return_value.child.assert_called_with("202401")

    def test_parse_newspaper_invalid_format(self):
        """Test parsing newspaper item with invalid format"""
        invalid_cases = [
            '<li><a href="/invalid.pdf">Invalid format</a></li>',
            '<li><a href="/zpravodaj.pdf">Ořechovský zpravodaj</a></li>',
            '<li><a href="/zpravodaj.pdf">Ořechovský zpravodaj invalid/2024</a></li>'
        ]

        with LoggerContext(self.log_dir, "test_newspaper_sync.log") as logger:
            with patch('firebase_admin.initialize_app'):
                updater = NewspaperUpdater(config_path=self.config_path)
                updater.logger = logger
                
                for html in invalid_cases:
                    soup = BeautifulSoup(html, 'html.parser')
                    li_element = soup.find('li')
                    item = updater._parse_newspaper_item(li_element)
                    self.assertIsNone(item, f"Should return None for invalid format: {html}")

if __name__ == '__main__':
    unittest.main(verbosity=2)