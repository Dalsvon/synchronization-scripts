The newspapers_to_app_sync.py script synchronizes Ořechovský zpravodaj (local newspaper) releases from the Ořechov municipality website to Realtime Firebase database of mobile app of Ořechov.
The script scans the website for newspaper entries, validates them, and updates the database accordingly, maintaining data consistency across platforms.

The config.txt file contains configuration for the script. Remember to first download necessary Python libraries listed in requirements.txt.

Folder key contains service key for database of the mobile app. Folder tests contains unit tests for this script.