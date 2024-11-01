import re
import logging
from contact_item import ContactItem

"""
This file contains parsing methods for differnet types of contacts. If no match is found during parsing of the content,
the function raises an exception, because it is likely that the format of the API has changed.
In this case no update is undertaken and old data remains in the database.
"""

def parse_school_data(raw_data, main_logger, logger):
    # Parser function for school data
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
    
    if schools == []:
        raise ValueError(f"Error during parsing of data: No schools found")
    
    return schools

def parse_general_contact(raw_data, main_logger, logger):
    # Parser function for general contact data
    phone = re.search(r'Tel\.: (.+)', raw_data)
    phone2 = re.search(r'Mobil: (.+)', raw_data)
    email = re.search(r'E-mail: (.+)', raw_data)
    maintenance = re.search(r'Údržba obce: (.+)', raw_data)
    web = re.search(r'Web: (.+)', raw_data)
    
    main_contact = ContactItem(
        title="Obec Ořechov",
        phone=phone.group(1).strip() if phone else None,
        phone2=phone2.group(1).strip() if phone2 else None,
        mail=email.group(1).strip() if email else None,
        maintenance=maintenance.group(1).strip() if maintenance else None,
        web=web.group(1).strip() if web else None
    )
    return [main_contact]

def parse_town_hall_contact(raw_data, main_logger, logger):
    # Parser function for town hall contact data
    contacts = []
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
        
    if contacts == []:
        raise ValueError(f"Error during parsing of data: No town hall contacts found")
    
    return contacts

def parse_post_office_data(raw_data, main_logger, logger):
    # Parser function for post office data
    contacts = []
    
    # Parse post office details
    title = re.search(r'\*\*(.+?)\*\*', raw_data)
    if not title:
        raise ValueError(f"Error during parsing of data: Post office contact not found")
    
    address = re.search(r'\*\*[^*]+\*\*\s*([\s\S]+?)(?=Tel\.|$)', raw_data)
    phone = re.search(r'Tel\.: (.+)', raw_data)
    email = re.search(r'E-mail: (.+)', raw_data)
    web = re.search(r'Web: (.+)', raw_data)
    
    post_office = ContactItem(
        title=title.group(1).strip(),
        address=address.group(1).strip() if address else None,
        mail=email.group(1).strip() if email else None,
        web=web.group(1).strip() if web else None,
        phone=phone.group(1).strip() if phone else None
    )
    contacts.append(post_office)
    
    return contacts

def parse_firemen_data(raw_data, main_logger, logger):
    # Parser function for fire department data
    contacts = []
    
    # Parse individual schools
    parsed_data = re.findall(r'\*\*(.+?)\*\*([\s\S]+?)(?=\*\*|$)', raw_data)
    
    for title, details in parsed_data:
        phone = re.search(r'Tel\.: (.+)', details)
        email = re.search(r'E-mail: (.+)', details)
        web = re.search(r'Web: (.+)', details)
        
        contact = ContactItem(
            title=title.strip(),
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None,
            web=web.group(1).strip() if web else None,
        )
        contacts.append(contact)
    
    if contacts == []:
        raise ValueError(f"Error during parsing of data: No firemen found")
    
    return contacts

def parse_library_data(raw_data, main_logger, logger):
    # Parser function for library data
    
    title = re.search(r'\*\*(.+?)\*\*', raw_data)
    
    if not title:
        raise ValueError(f"Error during parsing of data: Post office contact not found")
    
    # Get first phone and email only
    phone = re.search(r'\+420 \d{3} \d{3} \d{3}', raw_data)  # Gets first phone number
    email = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_data)   # Gets first email
    web = re.search(r'Web: (.+)', raw_data)
    
    library = ContactItem(
        title=title.group(1).strip(),
        phone=phone.group(0).strip() if phone else None,
        mail=email.group(0).strip() if email else None,
        web=web.group(1).strip() if web else None
    )
    
    return [library]

def parse_doctors_data(raw_data, main_logger, logger):
    # Parser function for doctors data (excluding pharmacy)
    contacts = []
    sections = raw_data.split('\r\n#####\r\n')
    
    # Process each section with its previous title
    for i in range(1, len(sections)):
        title = sections[i-1].splitlines()[-1]  # Get title from the last line of previous section
        section = sections[i]
        
        # Skip if it's a pharmacy or has no title
        if title is None or 'Lékárna' in title:
            continue
            
        # Get subtitle (name in bold)
        subtitle = re.search(r'\*\*(.+?)\*\*', section)
        address = re.search(r'(?<=\*\*\r\n)([^*\r\n]+)(?=\r\nTel\.:|$)', section)
        phone = re.search(r'Tel\.: (.+?)(?=\r\n|$)', section)
        email = re.search(r'E-mail: (.+?)(?=\r\n|$)', section)
        web = re.search(r'Web: (.+?)(?=\r\n|$)', section)
        
        doctor = ContactItem(
            title=title.strip(),
            subtitle=subtitle.group(1).strip() if subtitle else None,
            address=address.group(1).strip() if address else None,
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None,
            web=web.group(1).strip() if web else None
        )
        contacts.append(doctor)
    
    if contacts == []:
        raise ValueError(f"Error during parsing of data: No doctor contacts found")
    
    return contacts

def parse_drug_store_data(raw_data, main_logger, logger):
    # Parser function for pharmacy data
    contacts = []
    sections = raw_data.split('\r\n#####\r\n')
    
    # Process each section with its previous title
    for i in range(1, len(sections)):
        title = sections[i-1].splitlines()[-1] 
        section = sections[i]
        
        # Only process if it's a pharmacy
        if title is None or 'Lékárna' not in title:
            continue
            
        address = re.search(r'^(.+?)(?=\r\nTel\.:|$)', section)
        phone = re.search(r'Tel\.: (.+?)(?=\r\n|$)', section)
        email = re.search(r'E-mail: (.+?)(?=\r\n|$)', section)
        web = re.search(r'Web: (.+?)(?=\r\n|$)', section)
        
        pharmacy = ContactItem(
            title=title.strip(),
            address=address.group(1).strip() if address else None,
            phone=phone.group(1).strip() if phone else None,
            mail=email.group(1).strip() if email else None,
            web=web.group(1).strip() if web else None
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
