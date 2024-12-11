import requests
import psycopg2
from bs4 import BeautifulSoup
import re
import logging
import os
from datetime import datetime
from pathlib import Path
import configparser
import sys
import mimetypes
from urllib.parse import urljoin, unquote
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv
import uuid

def format_file_size(size_in_bytes: int) -> str:
    # Helper function to convert byte size to human readable format
    for unit in ['B', 'KB', 'MB']:
        if size_in_bytes < 1024:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024
    return f"{size_in_bytes:.2f} GB"

"""
DocumentFile class represents a file with attributes used in the database of Portal obcana. Does not contain content of the file.
"""
class DocumentFile:
    def __init__(self, name: str, url: str, file_type: str, file_size: int, folder_id: str, 
                 mime_type: str, from_website: bool = True):
        self.name = name
        self.description = None
        self.url = url
        self.file_type = file_type
        self.file_size = file_size
        self.folder_id = folder_id
        self.mime_type = mime_type
        self.from_website = from_website

"""
Class for loading the configuration of the program from file named config.txt.
"""
class ConfigLoader:
    def __init__(self, config_path='config.txt'):
        # Convert to Path object if it's a string
        config_path = Path(config_path)
        
        # Get the directory where the script is located
        self.script_dir = Path(__file__).parent.absolute()
        
        # If config_path is relative, make it relative to script directory
        if not config_path.is_absolute():
            config_path = self.script_dir / config_path

        # Check if file exists before trying to read it
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")
        
        load_dotenv()

        self.config = configparser.ConfigParser()
        self.config.read(str(config_path))
        self._load_configurations()
        self.main_logger = self._setup_main_logger()

    def _resolve_path(self, path_str):
        # Helper method to resolve paths based on whether they're absolute or relative
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self.script_dir / path

    def _setup_main_logger(self):
        # Set up the main logger for high-level program status
        try:
            os.makedirs(self.logs_directory, exist_ok=True)
            
            logger = logging.getLogger('main')
            logger.setLevel(logging.INFO)
            logger.handlers = []
            
            handler = logging.FileHandler(
                self.main_log,
                encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            return logger
        except Exception as e:
            raise ValueError(f"Failed to set up main logger: {e}")

    def _load_configurations(self):
        # Load configurations
        self.uses_ssl = self.config.getboolean('SSL', 'with_ssl', fallback=False)
        self.optimize_updates = self.config.getboolean('Optimization', 'skip_unchanged', fallback=False)
        
        # Load SSL configurations if needed
        if self.uses_ssl:
            self.ssl_directory = self._resolve_path(self.config['SSL']['directory'])
            self.client_crt_file = self.ssl_directory / 'client.crt'
            self.client_key_file = self.ssl_directory / 'client.key'
            self.ca_crt = self.ssl_directory / 'ca.crt'
            
            self.db_params = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT'),
                'sslmode': 'verify-full',
                'sslcert': str(self.client_crt_file),
                'sslkey': str(self.client_key_file),
                'sslrootcert': str(self.ca_crt)
            }
            
            # Verify SSL files exist
            self._verify_ssl_files()
        else:
            self.db_params = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT')
            }

        # Load directories and paths
        self.logs_directory = self._resolve_path(self.config['Logs']['directory'])
        self.main_log = self.logs_directory / self.config['Logs']['filename']
        self.folders_config_path = self._resolve_path(self.config['Application']['folders_config'])
        self.size_limit = self.config.getint('Application', 'file_size_limit_KB', fallback=30000)
        
        # Create necessary directories
        self.logs_directory.mkdir(parents=True, exist_ok=True)
        
        # Load folders configuration
        with open(self.folders_config_path, encoding='utf-8') as f:
            self.folders_config = json.load(f)

    def _verify_ssl_files(self):
        # Verify that all required SSL files exist
        ssl_files = [
            self.client_crt_file,
            self.client_key_file,
            self.ca_crt
        ]
        
        for file_path in ssl_files:
            if not file_path.is_file():
                raise FileNotFoundError(f"Required SSL file not found: {file_path}")

"""
Class that updates downloadable files for Portal Obcana by parsing them from website of Orechov. 
"""
class DocumentSyncUpdater:
    def __init__(self, config_loader):
        self.config_loader = config_loader
        self.main_logger = config_loader.main_logger
        self.logger = None
        self.folder_config = None
        self._initialize_database()
        self._ensure_tables_exist()

    def _initialize_database(self):
        # Check if all necessary parameters for database have been loaded
        try:
            if not all(self.config_loader.db_params.values()):
                raise ValueError("Missing required database configuration")
                
            self.db_params = self.config_loader.db_params
            
        except Exception as e:
            raise ValueError(f"Failed to initialize database connection: {str(e)}")
        
    def _ensure_tables_exist(self):
        # Check if all required tables exist
        self.main_logger.info("Checking if required database tables exist")
        required_tables = ['File', 'Folder']
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
                        
                    self.main_logger.info("All required database tables exist")
                    
                except psycopg2.Error as e:
                    error_msg = f"Database error while checking tables: {str(e)}"
                    self.main_logger.error(error_msg)
                    raise
                
    def setup_logging(self, log_name):
        # Set up logging for the current file category
        try:
            logger = logging.getLogger(log_name)
            logger.setLevel(logging.INFO)
            logger.handlers = []
            
            handler = logging.FileHandler(
                self.config_loader.logs_directory / log_name,
                encoding='utf-8'
            )
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            return logger
        except Exception as e:
            raise ValueError(f"Failure to set up {log_name} log for program: {e}")

    def set_folder(self, folder_name):
        # Set up a folder and so a category of files to be synchronized
        for folder in self.config_loader.folders_config['folders']:
            if folder['name'] == folder_name:
                self.folder_config = folder
                self.logger = self.setup_logging(folder['log_name'])
                return True
        
        self.main_logger.error(f"Configuration error for {folder_name} when setting folder")
        return False

    def _get_file_info_from_headers(self, url):
        # Return information about file by getting it from file header
        try:
            response = requests.head(url, allow_redirects=True)
            response.raise_for_status()
            
            content_length = int(response.headers.get('content-length', 0))
            content_type = response.headers.get('content-type', '').lower()
            
            # First try to get MIME type from Content-Type header
            if content_type and content_type != 'application/octet-stream':
                mime_type = content_type.split(';')[0].strip()
                # Get file type from MIME type
                file_type = mimetypes.guess_extension(mime_type)
                if file_type:
                    return content_length, mime_type, file_type[1:]
            
            extension_to_mime = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.txt': 'text/plain'
            }
            
            ext = os.path.splitext(url)[1].lower()
            if ext in extension_to_mime:
                mime_type = extension_to_mime[ext]
                file_type = ext[1:] 
                return content_length, mime_type, file_type
                
            self.logger.error(f"Could not determine MIME type for {url}, using default")
            return content_length, 'application/octet-stream', ''
        
        except Exception as e:
            self.logger.error(f"Failed to get file info from {url}: {str(e)}")
            return None, None, None

    def _download_file_content(self, url):
        # Download content of the file from url
        try:
            size, mime_type, file_type = self._get_file_info_from_headers(url)
            if size is None:
                return None, None, None
            
            # Check file size limit (limit is in KB so to has to be changed to B)
            if size > self.config_loader.size_limit * 1024:
                self.logger.error(f"File at {url} exceeds size limit of {self.config_loader.size_limit}KB. Skipping download")
                return None, None, None
            
            response = requests.get(url)
            response.raise_for_status()
            
            return response.content, mime_type, file_type
        except Exception as e:
            self.logger.error(f"Failed to download file from {url}: {str(e)}")
            return None, None, None

    def fetch_files(self, url, folder_id):
        # Get and parse files from content of a website
        try:
            response = requests.get(url)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            documents = []

            for li in soup.find_all('li'):
                link = li.find('a')
                if not link or not link.get('href'):
                    continue

                href = link['href']
                
                # Only accept certain formats for safety
                if not href.lower().endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt')):
                    continue

                full_url = urljoin(url, href)
                full_name = link.text.strip()
                name = full_name.split('(')[0].strip()
                
                size, mime_type, file_type = self._get_file_info_from_headers(full_url)
                if size is None:
                    continue

                document = DocumentFile(
                    name=name,
                    url=full_url,
                    file_type=file_type,
                    file_size=size,
                    folder_id=folder_id,
                    mime_type=mime_type
                )
                documents.append(document)
            
            if documents == []:
                self.logger.error(f"Failed to parse documents from {url}")
                raise ValueError("Failed to parse any files. Format of the website has probably changed and so synchronization was not started")
            return documents
        except Exception as e:
            self.logger.error(f"Failed to parse documents from {url}: {str(e)}")
            raise

    def update(self):
        # Update the database with files for previously set category (folder)
        if not self.folder_config:
            self.main_logger.error("No folder selected. Call set_folder() before updating.")
            return False

        try:
            self.main_logger.info(f"Starting document update process for {self.folder_config['name']}")
            self.logger.info(f"Starting update process")
            
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT id FROM "Folder" WHERE name = %s', (self.folder_config['name'],))
                    folder_result = cur.fetchone()
                    
                    if folder_result:
                        folder_id = folder_result[0]
                        self.logger.info(f"Working with existing folder: {self.folder_config['name']}")
                        cur.execute(
                            'UPDATE "Folder" SET "updatedAt" = CURRENT_TIMESTAMP WHERE id = %s',
                            (folder_id,)
                        )
                    else:
                        folder_id = str(uuid.uuid4())
                        cur.execute(
                            """INSERT INTO "Folder" (id, name, "createdAt", "updatedAt")
                               VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                            (folder_id, self.folder_config['name'])
                        )
                        self.logger.info(f"Created new folder: {self.folder_config['name']}")

                    documents = self.fetch_files(self.folder_config['url'], folder_id)
                    self.logger.info(f"Found {len(documents)} documents")

                    # Get existing files
                    cur.execute(
                        'SELECT id, name, "fileSize", "fromWebsite" FROM "File" WHERE "folderId" = %s',
                        (folder_id,)
                    )
                    existing_files = {row[1]: {'id': row[0], 'size': row[2], 'from_website': row[3]} 
                                    for row in cur.fetchall()}

                    # Process documents
                    found_files = set()
                    files_processed = 0
                    bytes_processed = 0

                    for doc in documents:
                        try:
                            found_files.add(doc.name)
                            
                            if doc.name in existing_files:
                                # Update existing file if needed
                                if (self.config_loader.optimize_updates and 
                                    existing_files[doc.name]['size'] == doc.file_size):
                                    self.logger.info(f"Skipping unchanged file: {doc.name}")
                                    continue
                                
                                content, mime_type, file_type = self._download_file_content(doc.url)
                                if not content:
                                    found_files.remove(doc.name)
                                    continue
                                    
                                cur.execute(
                                    """UPDATE "File" SET 
                                       "fileType" = %s, "fileSize" = %s, "uploadDate" = CURRENT_TIMESTAMP,
                                       content = %s, "mimeType" = %s, "fromWebsite" = %s
                                       WHERE id = %s""",
                                    (file_type, doc.file_size, psycopg2.Binary(content), 
                                     mime_type, True, existing_files[doc.name]['id'])
                                )
                                files_processed += 1
                                bytes_processed += doc.file_size
                                self.logger.info(f"Updated file: {doc.name}")
                            else:
                                # Add new file
                                content, mime_type, file_type = self._download_file_content(doc.url)
                                if not content:
                                    found_files.remove(doc.name)
                                    continue
                                    
                                file_id = str(uuid.uuid4())
                                cur.execute(
                                    """INSERT INTO "File" 
                                       (id, name, description, "fileType", "fileSize", "folderId",
                                        content, "mimeType", "fromWebsite", "uploadDate")
                                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                                    (file_id, doc.name, doc.description, file_type, doc.file_size,
                                     folder_id, psycopg2.Binary(content), mime_type, True)
                                )
                                files_processed += 1
                                bytes_processed += doc.file_size
                                self.logger.info(f"Added new file: {doc.name}")
                        
                        except Exception as e:
                            self.logger.error(f"Error processing file {doc.name}: {str(e)}")
                            continue

                    # Remove missing files
                    files_to_remove = {name for name, info in existing_files.items() 
                                     if info['from_website'] and name not in found_files}
                    if files_to_remove:
                        cur.execute(
                            """DELETE FROM "File" 
                               WHERE "folderId" = %s AND name = ANY(%s) AND "fromWebsite" = True""",
                            (folder_id, list(files_to_remove))
                        )
                        self.logger.info(f"Removed {len(files_to_remove)} files that no longer exist")

                    conn.commit()
                    
                    self.logger.info(f"Processed {files_processed} files")
                    self.logger.info(f"Total data processed: {format_file_size(bytes_processed)}")
                    self.main_logger.info(f"Changed or added {files_processed} files and deleted {len(files_to_remove)} in folder {self.folder_config['name']}")
                    return True

        except Exception as e:
            self.logger.error(f"Error during update: {str(e)}")
            self.main_logger.error(f"Error processing folder {self.folder_config['name']}: {str(e)}")
            return False

def main():
    try:
        config_loader = ConfigLoader()
    except Exception as e:
        print(f"Synchronizace selhala. Konfigurační chyba: {str(e)}", file=sys.stderr)
        return 1

    try:
        updater = DocumentSyncUpdater(config_loader)
        full_update = True
        
        # Process each folder separately
        for folder in config_loader.folders_config['folders']:
            if updater.set_folder(folder['name']):
                if not updater.update():
                    full_update = False
                    config_loader.main_logger.error(f"The documents from {folder['name']} could not be updated")
                else:
                    config_loader.main_logger.info(f"Successfully finished synchronization of documents from {folder['name']}")
            else:
                full_update = False
                config_loader.main_logger.error(f"The documents from {folder['name']} could not be processed due to configuration error")
        
        if not full_update:
            print(
                f"""Synchronizace nemohla být zcela dokončena. \
Některé dokumenty pravděpodobně nebyly aktualizovány. \
Pro více informací si přečtěte log soubor na adrese {config_loader.main_log}""",
                file=sys.stderr
            )
            return 1
        return 0
                
    except Exception as e:
        config_loader.main_logger.error(f"Error during update of database: {str(e)}")
        print(f"Synchronizace selhala. Pro více informací si přečtěte záznamový soubor na adrese {config_loader.main_log}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
