from typing import Optional, Tuple, Any
import logging
import re
from datetime import datetime

def validate_link(link: Optional[str], logger: Optional[logging.Logger] = None):
    if not link:
        if logger:
            logger.error("Empty link provided")
        return None, None
        
    link = link.strip()
    if not link.startswith(('http://', 'https://')):
        link = 'https://www.orechovubrna.cz' + link
        
    if not link.lower().endswith('.pdf'):
        if logger:
            logger.error(f"Link does not point to a PDF file: {link}")
        return None
    
    # Checks for valid URL format, also allows Czech characters, spaces and common URL characters
    if not re.match(r'^https?://[a-zA-Z0-9\u00C0-\u017F\-._~:/\?#\[\]@!$&\'\(\)\*\+,;=\%\s]+$', link):
        if logger:
            logger.error(f"Invalid URL format: {link}")
        return None
    
    return link

def validate_release(release: Any, logger: Optional[logging.Logger] = None):
    try:
        release_num = int(release)
        if not 1 <= release_num <= 12:
            if logger:
                logger.error(f"Release number out of valid range (1-12): {release_num}")
            return None
        return release_num
    except (ValueError, TypeError):
        if logger:
            logger.error(f"Invalid release number format: {release}")
        return None

def validate_year(year: Any, logger: Optional[logging.Logger] = None):
    try:
        year_num = int(year)
        current_year = datetime.now().year
        if not 1970 <= year_num <= current_year:
            if logger:
                logger.error(f"Year out of valid range (1990-{current_year}): {year_num}")
            return None
        return year_num
    except (ValueError, TypeError):
        if logger:
            logger.error(f"Invalid year format: {year}")
        return None

def validate_id(id: Any, year: int, release: int, logger: Optional[logging.Logger] = None):
    try:
        id_num = int(id)
        expected_id = (year * 100) + release
        if id_num != expected_id:
            if logger:
                logger.error(f"ID {id_num} doesn't match expected format YYYYRR for year {year} and release {release}")
            return None
        return id_num
    except Exception:
        if logger:
            logger.error(f"Invalid ID format: {id}")
        return None