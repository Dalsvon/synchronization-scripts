import unittest
from unittest.mock import patch, Mock, MagicMock, mock_open
import json
from pathlib import Path
import psycopg2
import logging
import sys
import requests
from bs4 import BeautifulSoup
from documents_to_portal_obcana_sync import DocumentSyncUpdater, ConfigLoader, DocumentFile
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv
import logging
logging.getLogger('dotenv.main').setLevel(logging.ERROR)

class TestFoldersConfig(unittest.TestCase):
    def setUp(self):
        self.config_path = Path(__file__).parent / 'folders_config.json'
        with open(self.config_path, encoding='utf-8') as f:
            self.config = json.load(f)

    def test_config_structure(self):
        """Test basic structure of the config file"""
        self.assertIn('folders', self.config, 
                     "Configuration must have 'folders' key")
        self.assertIsInstance(self.config['folders'], list,
                            "'folders' must be a list")
        self.assertTrue(len(self.config['folders']) > 0,
                       "Configuration must have at least one folder")

    def test_required_fields(self):
        """Test that all folders have required fields"""
        required_keys = ['name', 'url', 'log_name']
        
        for folder in self.config['folders']:
            for key in required_keys:
                self.assertIn(key, folder, 
                            f"Missing required key '{key}' in folder configuration")
                self.assertIsNotNone(folder[key], 
                                   f"'{key}' cannot be None in folder configuration")
                self.assertNotEqual(folder[key], '', 
                                  f"'{key}' cannot be empty in folder configuration")

    def test_unique_names(self):
        """Test that folder names are unique"""
        names = [folder['name'] for folder in self.config['folders']]
        self.assertEqual(len(names), len(set(names)), 
                        "Folder names must be unique")

    def test_url_format(self):
        """Test URL format and structure"""
        for folder in self.config['folders']:
            url = folder['url']
            # Test HTTPS
            self.assertTrue(url.startswith('https://'),
                          f"URL must use HTTPS: {url}")
            # Test domain
            self.assertTrue('orechovubrna.cz' in url,
                          f"URL must be from orechovubrna.cz domain: {url}")
            # Test trailing slash
            self.assertTrue(url.endswith('/'),
                          f"URL must end with forward slash: {url}")
            # Test path structure
            path = url.replace('https://www.orechovubrna.cz/', '')
            self.assertTrue(path.startswith('obecni-urad/'),
                          f"URL path must start with 'obecni-urad/': {url}")

    def test_log_name_format(self):
        """Test log file naming format"""
        for folder in self.config['folders']:
            log_name = folder['log_name']
            # Test extension
            self.assertTrue(log_name.endswith('.log'),
                          f"Log name must end with .log: {log_name}")
            # Test valid characters
            base_name = log_name.replace('.log', '').replace(' ', '_')
            self.assertTrue(base_name.replace('_', '').isalnum(),
                          f"Log name should only contain alphanumeric chars and underscores: {log_name}")

    def test_url_paths(self):
        """Test URL path structure in detail"""
        valid_prefixes = {
            'obecni-urad/potrebuji-vyridit/',
            'obecni-urad/'
        }
        
        for folder in self.config['folders']:
            url = folder['url']
            path = url.replace('https://www.orechovubrna.cz/', '')
            
            self.assertTrue(
                any(path.startswith(prefix) for prefix in valid_prefixes),
                f"URL must start with valid prefix: {url}"
            )
            
            path_parts = path.rstrip('/').split('/')
            self.assertGreaterEqual(len(path_parts), 2,
                                  f"URL path must have at least 2 parts: {url}")

class TestDocumentsSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure logging to use a null handler
        logging.getLogger('documents_sync').addHandler(logging.NullHandler())

    def setUp(self):
        self.dotenv_patcher = patch('dotenv.load_dotenv')
        self.mock_load_dotenv = self.dotenv_patcher.start()
        self.mock_config = {
            'Application': {
                'folders_config': 'folders_config0.json',
                'file_size_limit_KB': '30000'
            },
            'SSL': {
                'with_ssl': 'False',
                'directory': 'ssl'
            },
            'Logs': {
                'directory': 'logs',
                'filename': 'test.log'
            },
            'Optimization': {
                'skip_unchanged': 'True'
            }
        }

        self.mock_folders_config = {
            "folders": [
                {
                    "name": "Test Folder",
                    "url": "https://test.url/docs",
                    "log_name": "test.log"
                }
            ]
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
        mock_parser.getint.return_value = 30000
        mock_parser.getboolean.side_effect = lambda section, option, fallback=False: str(self.mock_config[section][option]).lower() == 'true'

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

        # Setup file open mock
        self.open_patcher = patch('builtins.open', mock_open(read_data=json.dumps(self.mock_folders_config)))
        self.open_patcher.start()

        # Setup database mock
        self.db_patcher = patch('psycopg2.connect')
        self.mock_db = self.db_patcher.start()
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_db.return_value.__enter__.return_value = self.mock_connection
        self.mock_cursor.fetchone.return_value = [True]
        
        self.makedirs_patcher = patch('os.makedirs')
        self.makedirs_patcher.start()

    def tearDown(self):
        # Stop all patches
        self.env_patcher.stop()
        self.config_patcher.stop()
        self.path_exists_patcher.stop()
        self.mkdir_patcher.stop()
        self.logging_patcher.stop()
        self.open_patcher.stop()
        self.db_patcher.stop()
        self.dotenv_patcher.stop()
        self.makedirs_patcher.stop()

    def _create_test_updater(self):
        """Helper method to create a properly initialized updater with logger"""
        config_loader = ConfigLoader()
        updater = DocumentSyncUpdater(config_loader)
        logger = logging.getLogger('test')
        logger.addHandler(logging.NullHandler())
        updater.logger = logger
        updater.main_logger = logger
        updater._ensure_tables_exist()
        return updater

    def test_config_loader_initialization(self):
        """Test basic configuration loading"""
        config_loader = ConfigLoader()
        self.assertEqual(config_loader.size_limit, 30000)
        self.assertFalse(config_loader.uses_ssl)
        self.assertTrue(config_loader.optimize_updates)

    def test_config_loader_missing_config(self):
        """Test handling of missing config file"""
        with patch.object(Path, 'exists', return_value=False):
            with self.assertRaises(FileNotFoundError):
                ConfigLoader('nonexistent/config.txt')

    def test_document_file_creation(self):
        """Test DocumentFile object creation"""
        doc = DocumentFile(
            name="Test Document",
            url="https://test.url/doc.pdf",
            file_type="pdf",
            file_size=1024,
            folder_id="test-folder",
            mime_type="application/pdf"
        )
        self.assertEqual(doc.name, "Test Document")
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(doc.mime_type, "application/pdf")
        self.assertTrue(doc.from_website)

    def test_ensure_tables_exist_success(self):
        """Test successful table existence check"""
        updater = self._create_test_updater()
        table_check_calls = [call for call in self.mock_cursor.execute.call_args_list 
                           if 'SELECT EXISTS' in str(call)]
        self.assertEqual(len(table_check_calls), 4)

    def test_ensure_tables_exist_missing_table(self):
        """Test that _ensure_tables_exist raises ValueError when a required table is missing"""
        # Create a fresh config loader
        config_loader = ConfigLoader()
        
        # Create mock cursor response sequence - table exists, then doesn't exist
        self.mock_cursor.reset_mock()
        self.mock_cursor.fetchone.side_effect = [(True,), (False,)]
        
        # Create updater without running _ensure_tables_exist in __init__
        with patch.object(DocumentSyncUpdater, '_ensure_tables_exist'):
            updater = DocumentSyncUpdater(config_loader)
        
        # Set up proper logging
        logger = logging.getLogger('test_logger')
        logger.addHandler(logging.NullHandler())
        updater.logger = logger
        updater.main_logger = logger
        
        # Test the _ensure_tables_exist method
        with self.assertRaises(ValueError) as context:
            updater._ensure_tables_exist()
        
        # Verify error message mentions missing tables
        self.assertTrue('Missing required tables' in str(context.exception))
        
        # Verify correct number of table checks were made
        table_check_calls = [call for call in self.mock_cursor.execute.call_args_list 
                            if 'SELECT EXISTS' in str(call)]
        self.assertEqual(len(table_check_calls), 2)

    @patch('requests.head')
    def test_get_file_info_from_headers(self, mock_head):
        """Test basic file information retrieval from headers"""
        updater = self._create_test_updater()
        
        mock_response = Mock()
        mock_response.headers = {
            'content-length': '1024',
            'content-type': 'application/pdf'
        }
        mock_response.raise_for_status = Mock()
        mock_head.return_value = mock_response
        
        size, mime_type, file_type = updater._get_file_info_from_headers("https://test.url/doc.pdf")
        
        self.assertEqual(size, 1024)
        self.assertEqual(mime_type, 'application/pdf')
        self.assertEqual(file_type, 'pdf')
        mock_head.assert_called_once_with("https://test.url/doc.pdf", allow_redirects=True)

    @patch('requests.head')
    @patch('requests.get')
    def test_download_file_under_limit(self, mock_get, mock_head):
        """Test that files under size limit are downloaded"""
        updater = self._create_test_updater()
        test_size = (updater.config_loader.size_limit * 1000) - 1000  # Just under limit
        
        # Mock get request for the actual download
        mock_get_response = Mock()
        mock_get_response.content = b"test content"
        mock_get_response.raise_for_status = Mock()
        mock_get.return_value = mock_get_response
        
        # Mock the internal _get_file_info_from_headers method to return a size under limit
        with patch.object(updater, '_get_file_info_from_headers') as mock_get_info:
            mock_get_info.return_value = (test_size, 'application/pdf', 'pdf')
            
            # Test the download
            content, mime_type, file_type = updater._download_file_content("https://test.url/doc.pdf")
            
            self.assertEqual(content, b"test content")
            self.assertEqual(mime_type, 'application/pdf')
            self.assertEqual(file_type, 'pdf')
            mock_get.assert_called_once()

    @patch('requests.head')
    @patch('requests.get')
    def test_download_file_over_limit(self, mock_get, mock_head):
        """Test that files over size limit are not downloaded"""
        updater = self._create_test_updater()
        test_size = (updater.config_loader.size_limit * 1024) + 1024  # Just over limit
        
        # Mock the internal _get_file_info_from_headers method to return a size over limit
        with patch.object(updater, '_get_file_info_from_headers') as mock_get_info:
            mock_get_info.return_value = (test_size, 'application/pdf', 'pdf')
            
            # Test the download
            content, mime_type, file_type = updater._download_file_content("https://test.url/doc.pdf")
            
            # Verify the file was rejected due to size
            self.assertIsNone(content)
            self.assertIsNone(mime_type)
            self.assertIsNone(file_type)
            mock_get.assert_not_called()

    @patch('requests.get')
    def test_fetch_files_success(self, mock_get):
        """Test successful file fetching"""
        html_content = """
        <ul>
            <li><a href="/doc1.pdf">Document 1</a></li>
            <li><a href="/doc2.docx">Document 2</a></li>
            <li><a href="/doc3.txt">Document 3</a></li>
            <li><a href="/invalid.exe">Invalid Document</a></li>
        </ul>
        """
        mock_response = Mock()
        mock_response.text = html_content
        mock_response.encoding = 'utf-8'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        updater = self._create_test_updater()
        updater.folder_config = self.mock_folders_config['folders'][0]

        with patch.object(updater, '_get_file_info_from_headers') as mock_info:
            mock_info.return_value = (1024, 'application/pdf', 'pdf')
            documents = updater.fetch_files("https://test.url", "test-folder")

        self.assertIsNotNone(documents)
        self.assertEqual(len(documents), 3)

    @patch('requests.get')
    def test_download_file_content_success(self, mock_get):
        """Test successful file content download"""
        updater = self._create_test_updater()
        mock_response = Mock()
        mock_response.content = b"test content"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch.object(updater, '_get_file_info_from_headers') as mock_info:
            mock_info.return_value = (11, 'application/pdf', 'pdf')
            content, mime_type, file_type = updater._download_file_content("https://test.url/doc.pdf")

        self.assertEqual(content, b"test content")
        self.assertEqual(mime_type, 'application/pdf')
        self.assertEqual(file_type, 'pdf')

    def test_mime_type_detection(self):
        """Test MIME type detection for different file types"""
        updater = self._create_test_updater()
        test_cases = [
            ("doc.pdf", "application/pdf", "pdf"),
            ("doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
            ("doc.txt", "text/plain", "txt")
        ]

        for filename, content_type, expected_type in test_cases:
            with patch('requests.head') as mock_head:
                mock_response = Mock()
                mock_response.headers = {
                    'content-length': '1024',
                    'content-type': content_type
                }
                mock_response.raise_for_status = Mock()
                mock_head.return_value = mock_response

                _, mime_type, file_type = updater._get_file_info_from_headers(f"https://test.url/{filename}")
                self.assertEqual(mime_type, content_type)
                self.assertEqual(file_type, expected_type)

    def test_optimization_skip_unchanged(self):
        """Test skipping unchanged files"""
        updater = self._create_test_updater()
        updater.folder_config = self.mock_folders_config['folders'][0]
        
        self.mock_cursor.fetchall.return_value = [("file-id", "Test Doc", 1024, True)]
        
        with patch.object(updater, 'fetch_files') as mock_fetch:
            mock_fetch.return_value = [
                DocumentFile("Test Doc", "https://test.url/doc.pdf", "pdf", 1024,
                           "folder-id", "application/pdf")
            ]
            
            result = updater.update()
            self.assertTrue(result)
            
            update_calls = [call for call in self.mock_cursor.execute.call_args_list 
                          if 'UPDATE "File"' in str(call)]
            self.assertEqual(len(update_calls), 0)

    def test_handle_invalid_mime_type(self):
        """Test handling of invalid MIME types"""
        updater = self._create_test_updater()
        
        with patch('requests.head') as mock_head:
            mock_response = Mock()
            mock_response.headers = {
                'content-length': '1024',
                'content-type': 'application/octet-stream'
            }
            mock_response.raise_for_status = Mock()
            mock_head.return_value = mock_response

            size, mime_type, file_type = updater._get_file_info_from_headers("https://test.url/doc.unknown")
            self.assertEqual(mime_type, 'application/octet-stream')
            self.assertEqual(file_type, '')

    def test_invalid_folder_config(self):
        """Test handling of invalid folder configuration"""
        updater = self._create_test_updater()
        result = updater.set_folder("Nonexistent Folder")
        self.assertFalse(result)
        self.assertIsNone(updater.folder_config)

if __name__ == '__main__':
    unittest.main()