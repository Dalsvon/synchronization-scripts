def parse_school_data(raw_data):
    """Parser function for school data"""
    import re
    from contact_item import ContactItem
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

# Add other parser functions as needed, e.g.:
# def parse_doctors_data(raw_data):
#     from contact_item import ContactItem
#     doctors = []
#     ...
#     return doctors

# Configuration dictionary
CONFIG = {
    'schools': {
        'firebase_route': 'contact_item/schoolss',
        'log_name': 'schools_api.log',
        'api_url': 'https://www.orechovubrna.cz/api/skoly/',
        'parser': parse_school_data
    }
    # Add more configurations as needed
}
