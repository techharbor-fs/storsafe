"""
Property code to name mapping for Bank Reconciliation.

Maps property codes (used in file names and system) to display names.
"""

# Property code -> Display name mapping
PROPERTY_CODES = {
    # DRE JV 1 and 2
    "cpwest": "Crown Point West",
    "ssmicity": "Michigan City",
    "ssmsouth": "Merrillville South",
    "sssilspr": "Silver Springs",
    "sswildwo": "Wildwood",
    "sspbay": "Palm Bay",
    "ssrock01": "Rockledge",
    "sslexing": "Lexington",
    "sscandle": "Candler",
    "sscedarl": "Cedar Lake",
    "sschgr": "China Grove",
    "ssdowven": "Downtown Venice",
    
    # All Other Storage
    "epcpss": "CPSS",
    "ephss": "Huntley North (HSS)",
    "ephss2": "Huntley South (HSS 2)",
    "epmss": "MSS",
    "2201": "Pilsen (2201 S Halsted)",
    "pshores": "Palm Shores",
    "ssbristo": "Bristol",
    "ssmadiso": "Madison",
    "ssmelbou": "Melbourne",
    "ssvenice": "Venice",
    
    # EP Storsafe III
    "ssracine": "Racine",
    "sslaport": "La Porte",
    
    # 3rd Party Management
    "sms-cary": "Cary",
    "sms-crys": "Crystal Lake",
    "sms-nfss": "Northfield",
    "smsaltoo": "Altoona",
    "smslawnd": "Lawndale",
    
    # Hard Assets
    "4700": "Darlington (4700 N Racine)",
    "314": "314 WIP",
    "1401": "Plaza Verde",
    "1288rick": "Naperville (1288 Rickert)",
    "5301": "Dempster",
    "sselkhar": "Elkhart",
    
    # Others
    "munster": "Munster",
}

# Alternative names/aliases that may appear in files
PROPERTY_ALIASES = {
    "mi city": "ssmicity",
    "michigan city": "ssmicity",
    "hss": "ephss",
    "hss 2": "ephss2",
    "pilsen": "2201",
    "2201 s halsted": "2201",
    "clk": "sms-crys",
    "crystal lake": "sms-crys",
    "darlington": "4700",
    "4700 n racine": "4700",
    "naperville": "1288rick",
    "1288 rickert": "1288rick",
}


def get_property_name(code_or_name: str) -> str:
    """
    Get the canonical display name for a property code or name.
    
    Args:
        code_or_name: Property code (e.g., 'ssmadiso') or display name (e.g., 'Madison')
        
    Returns:
        Canonical display name if found, otherwise returns the input as title case
    """
    if not code_or_name:
        return code_or_name
    
    input_lower = code_or_name.lower().strip()
    
    # Direct code lookup (e.g., 'ssmadiso' -> 'Madison')
    if input_lower in PROPERTY_CODES:
        return PROPERTY_CODES[input_lower]
    
    # Check aliases (e.g., 'mi city' -> 'Michigan City')
    if input_lower in PROPERTY_ALIASES:
        actual_code = PROPERTY_ALIASES[input_lower]
        return PROPERTY_CODES.get(actual_code, code_or_name)
    
    # Check if it matches a display name (case-insensitive)
    for code, display_name in PROPERTY_CODES.items():
        if display_name.lower() == input_lower:
            return display_name  # Return properly cased version
    
    # Return original with title case if not found
    return code_or_name.strip().title()


def get_property_code(name: str) -> str | None:
    """
    Get the property code from a display name or alias.
    
    Args:
        name: Property display name or alias
        
    Returns:
        Property code if found, otherwise None
    """
    if not name:
        return None
    
    name_lower = name.lower().strip()
    
    # Check if it's already a code
    if name_lower in PROPERTY_CODES:
        return name_lower
    
    # Check aliases
    if name_lower in PROPERTY_ALIASES:
        return PROPERTY_ALIASES[name_lower]
    
    # Search display names
    for code, display_name in PROPERTY_CODES.items():
        if display_name.lower() == name_lower:
            return code
    
    return None
