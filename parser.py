import re
import json
import os
import tempfile
from datetime import datetime

def standardize_date(date_str):
    if not date_str:
        return ""
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
        
    date_str = date_str.replace("Sept", "Sep")
    
    try:
        parsed_date = datetime.strptime(date_str.strip(), "%d %b %Y")
        return parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        pass

    try:
        parsed_date = datetime.strptime(date_str.strip(), "%d/%m")
        return parsed_date.replace(year=2026).strftime("%Y-%m-%d")
    except ValueError:
        return date_str

def parse_bookings(text_data):
    # Clean out WhatsApp export timestamps/sender prefixes
    cleaned_text = re.sub(r'\[\d{1,2}:\d{2}\s*[APMapm]{2},\s*\d{1,2}/\d{1,2}/\d{4}\]\s*[\+\d\s\-\:]+:\s*', '\n', text_data)

    results = []
    seen_ids = set()

    # Pattern A: Tab-separated or inline formats (handles alphanumeric hyphenated IDs like P4U-1-678492)
    tab_pattern = re.compile(
        r'(?:[A-Za-z\s&]+?\t+)?'
        r'(?P<id>[A-Z0-9]+(?:-[A-Z0-9]+)+|[A-Z0-9\-]{5,})'
        r'\t+'
        r'(?P<name>[A-Za-z.\- ]+?)\s*\(\d+\)\s*\t+'
        r'(?P<date>\d{4}-\d{2}-\d{2}|\d{2}\s+[A-Za-z]+\s+\d{4})',
        re.MULTILINE
    )

    for match in tab_pattern.finditer(cleaned_text):
        b_id = match.group("id").strip()
        if b_id not in seen_ids:
            seen_ids.add(b_id)
            results.append({
                "id": b_id,
                "name": match.group("name").strip(),
                "date": standardize_date(match.group("date"))
            })

    # Pattern B: Multi-line vertical blocks with optional emails/phone metadata lines
    multiline_pattern = re.compile(
        r'(?P<id>[A-Z0-9]+(?:-[A-Z0-9]+)+|[A-Z0-9\-]{5,})\s*[\r\n]+'
        r'(?P<name>[A-Za-z.\- ]+?)\s*\(\d{7,}\)\s*'
        r'(?:[\r\n]+[A-Za-z0-9\.\-_]+@[A-Za-z0-9\.-]+\.[A-Z|a-z]{2,})?\s*[\r\n]+'
        r'(?P<date>\d{2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})',
        re.MULTILINE
    )

    for match in multiline_pattern.finditer(cleaned_text):
        b_id = match.group("id").strip()
        if b_id not in seen_ids:
            seen_ids.add(b_id)
            results.append({
                "id": b_id,
                "name": match.group("name").strip(),
                "date": standardize_date(match.group("date"))
            })

    return results

def safe_save_json(data, filepath):
    dirname = os.path.dirname(filepath) or "."
    with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False) as tf:
        json.dump(data, tf, indent=4)
        temp_name = tf.name
    os.replace(temp_name, filepath)

# # --- Your Sample Data ---
# raw_text = """
# [7:19 PM, 9/12/2026] +92 318 4258691: 05:00
# 11 Sept 2026
# 19:30
# HX64XBZ
# Renault
# Just Park & Ride
# 30 mins
# [7:19 PM, 9/12/2026] +92 318 4258691: CAP-18-651232	
# Mr Martin Town (07798897314)
# 06 Sept 2026
# 06:00
# 11 Sept 2026
# 21:00
# MD70ONE
# Mazda
# Stansted Cheap Park & Ride
# 30m
# [7:19 PM, 9/12/2026] +92 318 4258691: AOA-1-22600	
# Mr Godswill Udo (07956141433)
# 07 Sept 2026
# 12:00
# 12 Sept 2026
# 12:00
# HG15WFS
# Ford
# Premium Park & Ride Stansted
# 30 MINS
# 2 per
# [7:19 PM, 9/12/2026] +92 318 4258691: 487585	
# Lavinia Cercel (07932809154)
# 05 Sept 2026
# 15:00
# 11 Sept 2026
# 23:30
# Bg18bym
# Kia Sportage Red
# Just Park & Ride
# [7:19 PM, 9/12/2026] +92 318 4258691: CP-STA-1307	
# stephanie bloomfield (07500691975)
# sbloomfield1968@gmail.com
# 07 Sept 2026
# 08:00
# 11 Sept 2026
# 18:30
# SL09 PCZ
# Ford Fiesta
# Park and Ride Stansted
# 30m
# [7:19 PM, 9/12/2026] +92 318 4258691: CYP-373873	
# Mrs. Jacq Hill (07592708947)
# 07 Sept 2026
# 03:30
# 11 Sept 2026
# 15:00
# XIG6841
# Mercedes
# Just Park & Ride
# 30m
# [7:19 PM, 9/12/2026] +92 318 4258691: CPD-19-649454	
# Miss KHAULA DAR (07882779795)
# 07 Sept 2026
# 12:00
# 11 Sept 2026
# 19:00
# DG08 SXE
# TOYOTA
# Stansted Cheap Park & Ride
# 2p
# 30mins
# [7:19 PM, 9/12/2026] +92 318 4258691: Just Park & Ride	CYP
# 30 mins-375759	Mr. Ben Elliott (07725580591)	2026-09-04	05:00:00	2026-09-11	16:30:00	Ford	EK12UTP	Just Park & Ride	3
# [7:19 PM, 9/12/2026] +92 318 4258691: CTP-393939	
# Mr. Tom Moat (07554487706)
# 07 Sept 2026
# 05:00
# 11 Sept 2026
# 19:30
# HX64XBZ
# Renault
# Just Park & Ride
# 30 mins
# """

# # # # # Run the parser and print as formatted JSON
# extracted_data = parse_bookings(raw_text)
# print(json.dumps(extracted_data, indent=4))
# safe_save_json(extracted_data,"bookings_data.json")