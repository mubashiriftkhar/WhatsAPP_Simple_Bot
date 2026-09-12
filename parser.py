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
raw_text = """
[11:01 PM, 9/11/2026] +92 318 4258691: CPD-19-631404	
Mr Simon Turner (07877966957)
08 Sept 2026
02:30
18 Sept 2026
01:30
AP72BXD
Nissan
Stansted Cheap Park & Ride
30 MINT 2P
[11:01 PM, 9/11/2026] +92 318 4258691: 489424	
Thadi Crook (07563 995 222)
08 Sept 2026
03:00
11 Sept 2026
23:00
YA64UXZ
Honda civic Red
Just Park & Ride
45m away
[11:01 PM, 9/11/2026] +92 318 4258691: CAP-18-674353	
Mr Vladimir Loginov (07812033397)
31 Aug 2026
05:00
07 Sept 2026
15:00
Sw14LLF
Skoda
Stansted Cheap Park & Rid
07825772067
1p  55 min


still on the plane
[11:01 PM, 9/11/2026] +92 318 4258691: Just Park & Ride	CYP-394571	Miss. Gemma Rear (07446949531)	2026-09-04	03:00:00	2026-09-11	15:30:00	Ford	WV18FXL	Just Park & Ride	1
30 mins
[11:01 PM, 9/11/2026] +92 318 4258691: Just Park & Ride	CYP-389836	Mr. Joe Wallington (07736220392)	2026-09-02	12:00:00	2026-09-10	00:15:00	Audi	LR61LZA	Just Park & Ride	2
collect late fee
coming to yard
[11:01 PM, 9/11/2026] +92 318 4258691: AOA-1-23668	
Mr Hemanth Raj Pachiriyan (07824049991)
06 Sept 2026
22:30
11 Sept 2026
02:00
AJ67BZH
Volkswagen
Premium Park & Ride Stansted
please check screenshot of confirmation
AOA-1-20477	
Mr David Calveley (07400815482)
11 Sept 2026
04:00
18 Sept 2026
03:45
WM67 KK0
Mitsubishi
Premium Park & Ride Stansted
07426035368
2 PER
25 MIN AWAY
Stansted Cheap Park & Ride	P4U-1-671749	Mr Paul Mckay (07715632079)	2026-09-11	03:00:00	2026-09-14	01:30:00	Vauxhall	SH64 VDR	Stansted Cheap Park & Ride	2
CTP-393782	
Mrs. Katarzyna Holke (07860254295)
11 Sept 2026
03:00
13 Sept 2026
12:00
HX64XYS
Renault
Just Park & Ride	
25 mins away 
2p
YP-398424	
Mr. Ryan Westhorpe (447398139078)
11 Sept 2026
13:00
14 Sept 2026
01:00
WF67SJY
Mercedes
Just Park & Ride
5 PER
30 Mints away....
07398139078
P4U-1-678911	
Mr Luke Perry (07478314304)
	
11 Sept 2026
13:30
	
12 Sept 2026
09:00
	
RJ75 LTE
Citroen
	Stansted Park and Fly	
07522824288
30 MINS AWAY 
2P
Premium Park & Ride Stansted	AOA-1-23893	Mr Nilesh Parekh (07773025455)	2026-09-11	15:00:00	2026-09-16	21:00:00	VW	PN11ESH	Premium Park & Ride Stansted	6
CP-STA-1371	
SAFDAR ZAMAN (07957709457)
SAF.ZAM@HOTMAIL.COM
08 Sept 2026
05:00
11 Sept 2026
14:00
SL69VFU
LEXUS LEXUS
Park and Ride Stansted
07459438774
30 MINS
"""

# # # # Run the parser and print as formatted JSON
extracted_data = parse_bookings(raw_text)
print(json.dumps(extracted_data, indent=4))
safe_save_json(extracted_data,"bookings_data.json")