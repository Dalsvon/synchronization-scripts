The contacts_to_app_sync.py script synchronizes contacts from the Ořechov municipality website to Realtime Firebase database of mobile app of Ořechov.
The script takes the contacts from API provided by the website, validates them, and updates the database accordingly, maintaining data consistency across platforms.

The config.txt file contains configuration for the script. Remember to first download necessary Python libraries listed in requirements.txt.
Config folder holds parsers and data_config for each type of contact synchronized.

Folder key contains service key for database of the mobile app. Folder tests contains unit tests for this script.