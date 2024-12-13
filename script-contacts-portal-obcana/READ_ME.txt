The contacts_to_portal_obcana_sync.py script synchronizes contacts from the Ořechov municipality website to PostgreSQL database of Portal občana of Ořechov.
The script takes the contacts from API provided by the website, validates them, and updates the database accordingly, maintaining data consistency across platforms.

The config.txt file contains configuration for the script. Remember to first download necessary Python libraries listed in requirements.txt.

File .env contains more sensitive information like password and name of the database.

Folder ssl contains ssl keys if they are necessary for connecing to the database. Folder tests contains unit tests for this script.