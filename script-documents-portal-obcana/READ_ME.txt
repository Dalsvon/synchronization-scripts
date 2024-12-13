The documents_to_portal_obcana_sync.py script synchronizes downloadable documents and folders from the Ořechov municipality website to PostgreSQL database of Portal občana of Ořechov.
The script scans the website for the documents and updates the database accordingly, maintaining data consistency across platforms.

The config.txt file contains configuration for the script. Remember to first download necessary Python libraries listed in requirements.txt.
File folders_config.json contains information where the documents are located and to which folder are they supposed to be placed in the database.

File .env contains more sensitive information like password and name of the database.

Folder ssl contains ssl keys if they are necessary for connecting to the database. Folder tests contains unit tests for this script.