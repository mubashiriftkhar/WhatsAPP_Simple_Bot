import re
import json
import os
import tempfile
from datetime import datetime

def standardize_date(date_str):
    # If the date is already in YYYY-MM-DD format, return it as-is
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
        
    # Python's %b directive expects 3-letter months (Sep), so we normalize 'Sept'
    date_str = date_str.replace("Sept", "Sep")
    
    try:
        # Parse '01 Sep 2026' and convert to '2026-09-01'
        parsed_date = datetime.strptime(date_str, "%d %b %Y")
        return parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        return date_str # Fallback in case of an unexpected format

def parse_bookings(text_data):
    pattern = re.compile(
        r'(?P<id>[A-Z]+(?:-\d+)+|\d{5,})'                        
        r'\s+'                                                   
        r'(?P<name>[A-Za-z.\- ]+?)'                              
        r'\s*\(\d+\)'                                            
        r'\s+'                                                   
        r'(?P<date>\d{2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})' 
    )

    results = []
    
    for match in pattern.finditer(text_data):
        results.append({
            "id": match.group("id"),
            "name": match.group("name").strip(),
            "date": standardize_date(match.group("date"))
        })
        
    return results

def safe_save_json(data, filepath):
    # Uses the atomic write method to prevent corruption during a server crash
    dirname = os.path.dirname(filepath) or "."
    with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False) as tf:
        json.dump(data, tf, indent=4)
        temp_name = tf.name
    os.replace(temp_name, filepath)

# # --- Your Sample Data ---
# raw_text = """
# CTPD-01760	
# Euan Warwick (07456426039)
# 01 Aug 2026
# 03:00
# 05 Sept 2026
# 23:45
# AE19GSU
# VW POLO
# Park & Ride Stansted
# 30m away
# CYP-389830	
# Mrs. Margaret Odukoya (07908848863)
# 01 Sept 2026
# 03:00
# 05 Sept 2026
# 07:00
# NK13UYH
# RAV4
# Just Park & Ride
# 30min
# 488465	
# Mihaita Vasile (07778519149)
	
# 01 Sept 2026
# 02:00
	
# 06 Sept 2026
# 15:00
	
# GL66JZR
# Mazda 6 Blue
# 	Just Park & Ride
# 30 mints 1p
# Just Park & Ride	CTP-392764	Miss. Ellie-may Flood (07725637754)	2026-09-01	03:00:00	2026-09-11	17:00:00	Peugeot	RF74WYH	Just Park & Ride	3
# CAP-18-675177	
# Mr Serhii Gnypa (07394719616)
	
# 01 Sept 2026
# 04:15
	
# 06 Sept 2026
# 01:00
	
# RA66RYK
# INFINITY
# 	Stansted Cheap Park & Ride
# 30 mins 
# 1p
# AOA-1-23336	
# Mr Esmir Fejzullari (07718609335)
# 01 Sept 2026
# 04:45
# 04 Sept 2026
# 23:00
# Ly74aha
# Volkswagen
# Premium Park & Ride Stansted 2
# 30 min
# """

# # # Run the parser and print as formatted JSON
# extracted_data = parse_bookings(raw_text)
# # print(json.dumps(extracted_data, indent=4))
# safe_save_json(extracted_data,"bookings_data.json")