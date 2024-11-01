import re
import logging
from contact_item import ContactItem

def parse_school_data(raw_data, main_logger, logger):
    """Parser function for school data"""
    schools = []
    
    # Parse individual schools
    school_data = re.findall(r'\*\*(.+?)\*\*([\s\S]+?)(?=\*\*|$)', raw_data)
    
    for name, details in school_data:
        phone = re.search(r'Tel\.: (.+)', details)
        email = re.search(r'E-mail: (.+)', details)
        web = re.search(r'Web: (.+)', details)
        address = re.search(r'(.+?)(?=\r\nTel\.:|$)', details)
        
        school = ContactItem(
            title=name.strip(),
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None,
            web=web.group(1).strip() if web else None,
            address=address.group(1).strip() if address else None
        )
        schools.append(school)
    
    return schools

def parse_general_contact(raw_data, main_logger, logger):
    """Parser function for general contact data"""
    contacts = []
    
    # Parse main contact
    phone = re.search(r'Tel\.: (.+)', raw_data)
    phone2 = re.search(r'Mobil: (.+)', raw_data)
    email = re.search(r'E-mail: (.+)', raw_data)
    maintenance = re.search(r'Údržba obce: (.+)', raw_data)
    
    main_contact = ContactItem(
        title="Obec Ořechov",
        phone=phone.group(1).strip() if phone else None,
        phone2=phone2.group(1).strip() if phone2 else None,
        mail=email.group(1).strip() if email else None,
        maintenance=maintenance.group(1).strip() if maintenance else None
    )
    contacts.append(main_contact)
    return contacts

def parse_town_hall_contact(raw_data, main_logger, logger):
    """Parser function for town hall contact data"""
    contacts = []
    # Parse main contact
    phone = re.search(r'Tel\.: (.+)', raw_data)
    phone2 = re.search(r'Mobil: (.+)', raw_data)
    email = re.search(r'E-mail: (.+)', raw_data)
    maintenance = re.search(r'Údržba obce: (.+)', raw_data)
    # Parse individual contacts (staff)
    staff_data = re.findall(r'\| \*\*(.+?)\*\*\| (.+?) \| (.+?) \| (.+)', raw_data)
    for name, position, phone, email in staff_data:
        contact = ContactItem(
            title=name.strip(),
            subtitle=position.strip(),
            phone=phone.strip(),
            mail=email.strip()
        )
        contacts.append(contact)
    
    return contacts

def parse_post_office_data(raw_data, main_logger, logger):
    """Parser function for post office data"""
    contacts = []
    
    # Parse post office details using regex
    title = re.search(r'\*\*(.+?)\*\*', raw_data)
    address = re.search(r'(.+?)(?=\r\nTel\.:|$)', raw_data)
    phone = re.search(r'Tel\.: (.+)', raw_data)
    
    post_office = ContactItem(
        title=title.group(1).strip() if title else None,
        address=address.group(1).strip() if address else None,
        phone=phone.group(1).strip() if phone else None
    )
    contacts.append(post_office)
    
    return contacts

def parse_firemen_data(raw_data, main_logger, logger):
    """Parser function for fire department data"""
    contacts = []
    
    # Parse fire department details using regex
    title = re.search(r'\*\*(.+?)\*\*', raw_data)
    email = re.search(r'E-mail: (.+)', raw_data)
    phone = re.search(r'Tel\.: (.+)', raw_data)
    web = re.search(r'Web: (.+)', raw_data)
    
    firemen = ContactItem(
        title=title.group(1).strip() if title else None,
        mail=email.group(1).strip() if email else None,
        phone=phone.group(1).strip() if phone else None,
        web=web.group(1).strip() if web else None
    )
    contacts.append(firemen)
    
    return contacts

def parse_library_data(raw_data, main_logger, logger):
    """Parser function for library data"""
    contacts = []
    
    # Parse library details using regex
    title = re.search(r'\*\*(.+?)\*\*', raw_data)
    
    # Get first phone and email only
    phone = re.search(r'\+420 \d{3} \d{3} \d{3}', raw_data)  # Gets first phone number
    email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_data)   # Gets first email
    web = re.search(r'Web: (.+)', raw_data)
    
    library = ContactItem(
        title=title.group(1).strip() if title else None,
        phone=phone.group(0).strip() if phone else None,
        mail=email.group(0).strip() if email else None,
        web=web.group(1).strip() if web else None
    )
    contacts.append(library)
    
    return contacts

def parse_doctors_data(raw_data, main_logger, logger):
    """Parser function for doctors data (excluding pharmacy)"""
    contacts = []
    
    # Split the data into sections by headers (marked with #####)
    sections = raw_data.split('\r\n#####\r\n')
    
    # Process each section with its previous title
    for i in range(1, len(sections)):  # Start from 1 to pair title with next section
        title = sections[i-1].splitlines()[-1]  # Get the last line of previous section
        section = sections[i]
        
        # Skip if it's a pharmacy section
        if 'Lékárna' in title:
            continue
            
        # Get subtitle (name in bold)
        subtitle = re.search(r'\*\*(.+?)\*\*', section)
        # Get other details
        address = re.search(r'(?<=\*\*\r\n)([^*\r\n]+)(?=\r\nTel\.:|$)', section)
        phone = re.search(r'Tel\.: (.+?)(?=\r\n|$)', section)
        email = re.search(r'E-mail: (.+?)(?=\r\n|$)', section)
        
        doctor = ContactItem(
            title=title.strip() if title else None,
            subtitle=subtitle.group(1).strip() if subtitle else None,
            address=address.group(1).strip() if address else None,
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None
        )
        contacts.append(doctor)
    
    return contacts

def parse_drug_store_data(raw_data, main_logger, logger):
    """Parser function for pharmacy data"""
    contacts = []
    
    # Split the data into sections by headers (marked with #####)
    sections = raw_data.split('\r\n#####\r\n')
    
    # Process each section with its previous title
    for i in range(1, len(sections)):  # Start from 1 to pair title with next section
        title = sections[i-1].splitlines()[-1]  # Get the last line of previous section
        section = sections[i]
        
        # Only process if it's a pharmacy section
        if 'Lékárna' not in title:
            continue
            
        # Get other details - modified address pattern to just get the line before Tel.:
        address = re.search(r'^(.+?)(?=\r\nTel\.:|$)', section)
        phone = re.search(r'Tel\.: (.+?)(?=\r\n|$)', section)
        email = re.search(r'E-mail: (.+?)(?=\r\n|$)', section)
        
        pharmacy = ContactItem(
            title=title.strip() if title else None,
            address=address.group(1).strip() if address else None,
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None
        )
        contacts.append(pharmacy)
    
    return contacts

# Dictionary mapping parser function names to actual functions
PARSER_FUNCTIONS = {
    'parse_school_data': parse_school_data,
    'parse_general_contact': parse_general_contact,
    'parse_town_hall_contact': parse_town_hall_contact,
    'parse_post_office_data': parse_post_office_data,
    'parse_firemen_data': parse_firemen_data,
    'parse_library_data': parse_library_data,
    'parse_doctors_data': parse_doctors_data,
    'parse_drug_store_data': parse_drug_store_data
}
