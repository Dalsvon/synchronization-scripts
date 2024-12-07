import re
from typing import Optional
import logging

def validate_email(email: Optional[str], logger: Optional[logging.Logger] = None):
    if not email:
        return None
        
    email = email.strip()
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email)
    
    if not match:
        if logger:
            logger.warning(f"No valid email found in: {email}")
        return None
    
    return match.group(0)

def validate_phone(phone: Optional[str], logger: Optional[logging.Logger] = None):
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

def validate_ic(ic: Optional[str], logger: Optional[logging.Logger] = None):
    if not ic:
        return None
        
    ic = ''.join(ic.split())
    
    if not re.match(r'^\d{8}$', ic):
        if logger:
            logger.error(f"Invalid IČ format: {ic}")
        return None
    
    return ic

def validate_dic(dic: Optional[str], logger: Optional[logging.Logger] = None):
    if not dic:
        return None
        
    dic = ''.join(dic.split())
    
    if not re.match(r'^CZ\d{8,10}$', dic):
        if logger:
            logger.error(f"Invalid DIČ format: {dic}")
        return None
    
    return dic

def validate_data_box(data_box: Optional[str], logger: Optional[logging.Logger] = None):
    if not data_box:
        return None
        
    data_box = ''.join(data_box.split())
    
    if not re.match(r'^[a-zA-Z0-9]{7}$', data_box):
        if logger:
            logger.warning(f"Invalid data box ID format: {data_box}")
        return None
    
    return data_box.lower()
