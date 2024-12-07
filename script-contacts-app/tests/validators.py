import re
from typing import Optional
import logging

def validate_email(email: Optional[str], logger: Optional[logging.Logger] = None) -> Optional[str]:
    if not email:
        return None
        
    email = email.strip()
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email)
    
    if not match:
        if logger:
            logger.warning(f"No valid email found in: {email}")
        return None
    
    return match.group(0)

def validate_phone(phone: Optional[str], logger: Optional[logging.Logger] = None) -> Optional[str]:
    if not phone:
        return None
        
    # Match standard phone format
    matches = re.finditer(r'(?:\+420\s*)?(\d{3})\s*(\d{3})\s*(\d{3})', phone)
    first_match = next(matches, None)
    
    if not first_match:
        if logger:
            logger.error(f"No valid phone number found in: {phone}")
        return None
    
    groups = first_match.groups()
    
    # Format with proper spacing
    return f"+420 {groups[0]} {groups[1]} {groups[2]}"

def validate_url(url: Optional[str], logger: Optional[logging.Logger] = None) -> Optional[str]:
    if not url:
        return None
        
    url = url.strip()
    
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    pattern = r'^https?:\/\/([\w\d\-]+\.)+[\w\d\-]+(\/[\w\d\-\._\/]*)*\/?$'
    if not re.match(pattern, url):
        if logger:
            logger.error(f"Invalid URL format: {url}")
        return None
    
    return url