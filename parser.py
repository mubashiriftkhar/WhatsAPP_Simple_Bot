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
# P-393009	
# Miss. Lydia Vaccaro (07598499438)
# 10 Sept 2026
# 04:00
# 14 Sept 2026
# 02:30
# P555LYD
# BMW
# Just Park & Ride	
# 07852789697
# 2 PER
# 27 Mints away

# ACP-17-399771	
# Mr Martin Rutkowski (07949391143)
# 10 Sept 2026
# 06:30
# 12 Sept 2026
# 21:30
# RJ15AKK
# Peugeot
# Stansted Cheap Park & Ride	
# ko08kmx
# 4
# 30 mins

# EZY-416747	
# Muhammad Ismail Hanif (07307874849)
# 10 Sept 2026
# 14:00
# 13 Sept 2026
# 15:30
# AF57JXW
# Volkswagen Polo Black
# Stanstetd Park &amp; Ride
# 3 per
# 50 Mints away...

# P4U-1-678492	
# Mr Defrim Avdullai (07879886528)
# 10 Sept 2026
# 15:45
# 20 Sept 2026
# 23:30
# KV61UDD
# Audi
# Stansted Park and Fly
# 25 mints 1p

# AOA-1-20477	
# Mr David Calveley (07400815482)
# 11 Sept 2026
# 04:00
# 18 Sept 2026
# 03:45
# WM67 KK0
# Mitsubishi
# Premium Park & Ride Stansted
# 07426035368
# 2 PER
# 25 MIN AWAY

# Stansted Cheap Park & Ride	P4U-1-671749	Mr Paul Mckay (07715632079)	2026-09-11	03:00:00	2026-09-14	01:30:00	Vauxhall	SH64 VDR	Stansted Cheap Park & Ride	2

# [9:45 PM, 9/11/2026] +92 318 4258691: CPP-126711	
# Jamie Tonkin (07831861643)
# 31 Aug 2026
# 05:00
# 11 Sept 2026
# 14:00
# GL12HJX
# Peugeot 107 White
# Stanstetd Park &amp; Ride
# 07841512475

# 2 cars                 40 min       3p

# Jg14zdk. Car reg
# 11/09. Return
# 13:00. Time
# 2 per

# [9:45 PM, 9/11/2026] +92 318 4258691: EZY-415876	
# nikki deaney (07551345581)
# 28 Aug 2026
# 04:00
# 11 Sept 2026
# 14:00
# Sg59lcn
# Ford Focus Blue
# Stanstetd Park &amp; Ride
# 3 PER
# 50 Mints...

# [9:45 PM, 9/11/2026] +92 318 4258691: CPD-19-623264	
# Mr Costica Andrei Dan (07526567497)
# 29 Aug 2026
# 04:30
# 11 Sept 2026
# 14:00
# KE65MVN
# Lexus
# Stansted Cheap Park & Ride
# 30 mins away 
# 2 per

# [9:45 PM, 9/11/2026] +92 318 4258691: CYP-389858	
# Mr. Mhd Imad Kalach (07504555543)
# 25 Aug 2026
# 11:30
# 11 Sept 2026
# 17:00
# BT16TXH
# Mercedes
# Just Park & Ride	
# 30 min

# [9:45 PM, 9/11/2026] +92 318 4258691: AOA-1-23668	
# Mr Hemanth Raj Pachiriyan (07824049991)
# 06 Sept 2026
# 22:30
# 11 Sept 2026
# 02:00
# AJ67BZH
# Volkswagen
# Premium Park & Ride Stansted
# please check screenshot of confirmation

# [9:45 PM, 9/11/2026] +92 318 4258691: 106	Just Park & Ride	CYP-389823	Mr. Jameill Hewitt (07552948027)	2026-09-05	03:30:00	2026-09-11	17:00:00	Kia	LC20MKZ	Just Park & Ride	2 *
# 30 mins*

# [9:45 PM, 9/11/2026] +92 318 4258691: CPD-19-618542	
# Mrs Iacob Irina (07751018982)
# 29 Aug 2026
# 04:00
# 11 Sept 2026
# 18:00
# WR68ZYY
# Mitsubishi
# Stansted Cheap Park & Ride
# 07869768305
# 30 MINS

# [9:45 PM, 9/11/2026] +92 318 4258691: CP-STA-1371	
# SAFDAR ZAMAN (07957709457)
# SAF.ZAM@HOTMAIL.COM
# 08 Sept 2026
# 05:00
# 11 Sept 2026
# 14:00
# SL69VFU
# LEXUS LEXUS
# Park and Ride Stansted
# 07459438774
# 30 MINS

# [9:45 PM, 9/11/2026] +92 318 4258691: 07803909109
# 	CP-STA-1340	
# Avtar Sandhu (7803909109)
# sandhu@blueyonder.co.uk
# 30 Aug 2026
# 14:00
# 11 Sept 2026
# 18:00
# MR54NDH
# BMW X4 Xdrive20d M Sport Mhev Auto
# Park and Ride Stansted
# 30 MINS

# [9:45 PM, 9/11/2026] +92 318 4258691: CYP-396415	
# Ms. Jean Kennett (07930697315)
# 07 Sept 2026
# 06:00
# 11 Sept 2026
# 18:00
# LV15EJA
# Ford
# Just Park & Ride
# 30m

# [9:45 PM, 9/11/2026] +92 318 4258691: Just Park & Ride	CYP-389836	Mr. Joe Wallington (07736220392)	2026-09-02	12:00:00	2026-09-10	00:15:00	Audi	LR61LZA	Just Park & Ride	2
# collect late fee
# coming to yard

# [9:38 PM, 9/11/2026] +92 318 4258691: AOA-1-23668	
# Mr Hemanth Raj Pachiriyan (07824049991)
# 06 Sept 2026
# 22:30
# 11 Sept 2026
# 02:00
# AJ67BZH
# Volkswagen
# Premium Park & Ride Stansted
# please check screenshot of confirmation

# [9:38 PM, 9/11/2026] +92 318 4258691: CPD-19-618542	
# Mrs Iacob Irina (07751018982)
# 29 Aug 2026
# 04:00
# 11 Sept 2026
# 18:00
# WR68ZYY
# Mitsubishi
# Stansted Cheap Park & Ride
# 07869768305
# 30 MINS

# [9:38 PM, 9/11/2026] +92 318 4258691: CP-STA-1371	
# SAFDAR ZAMAN (07957709457)
# SAF.ZAM@HOTMAIL.COM
# 08 Sept 2026
# 05:00
# 11 Sept 2026
# 14:00
# SL69VFU
# LEXUS LEXUS
# Park and Ride Stansted
# 07459438774
# 30 MINS

# [9:38 PM, 9/11/2026] +92 318 4258691: Just Park & Ride	CTP-392764	Miss. Ellie-may Flood (07725637754)	2026-09-01	03:00:00	2026-09-11	17:00:00	Peugeot	RF74WYH	Just Park & Ride	3
# 30 MINS

# [9:38 PM, 9/11/2026] +92 318 4258691: 07803909109
# 	CP-STA-1340	
# Avtar Sandhu (7803909109)
# sandhu@blueyonder.co.uk
# 30 Aug 2026
# 14:00
# 11 Sept 2026
# 18:00
# MR54NDH
# BMW X4 Xdrive20d M Sport Mhev Auto
# Park and Ride Stansted
# 30 MINS
# """

# # # # Run the parser and print as formatted JSON
# extracted_data = parse_bookings(raw_text)
# print(json.dumps(extracted_data, indent=4))
# safe_save_json(extracted_data,"bookings_data.json")