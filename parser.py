
import re
import json
import os
import tempfile
from datetime import datetime


def standardize_date(date_str):
    if not date_str:
        return ""

    date_str = date_str.strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str

    date_str = date_str.replace("Sept", "Sep")

    try:
        parsed_date = datetime.strptime(date_str, "%d %b %Y")
        return parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        pass

    try:
        parsed_date = datetime.strptime(date_str, "%d/%m")
        return parsed_date.replace(year=2026).strftime("%Y-%m-%d")
    except ValueError:
        return date_str


def parse_bookings(text_data):
    cleaned_text = re.sub(
        r"\[\d{1,2}:\d{2}\s*[APMapm]{2},\s*\d{1,2}/\d{1,2}/\d{4}\]\s*\+?\d[\d\s\-:]*:\s*",
        "\n",
        text_data
    )

    blocks = re.split(r"\n(?=\S)", cleaned_text)

    results = []
    seen_ids = set()

    date_pattern = re.compile(
        r"^\d{1,2}\s+[A-Za-z]+\s+\d{4}$|^\d{4}-\d{2}-\d{2}$"
    )

    customer_pattern = re.compile(
        r"^(?:Mr|Mrs|Miss|Ms|Dr)\.?\s+.+?\s+\(?\d{7,15}\)?$",
        re.I
    )

    def clean_line(line):
        line = line.strip()
        line = re.sub(r"^\|+|\|+$", "", line)
        line = re.sub(r"^\*+|\*+$", "", line)
        return line.strip()

    def is_time(line):
        return bool(re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", line.strip()))

    def is_vehicle_reg(line):
        normalized = re.sub(r"\s+", "", line.upper())

        return (
            bool(re.fullmatch(r"[A-Z]{1,3}\d{1,4}[A-Z]{0,3}", normalized))
            and not re.search(r"\d{4,}", normalized)
        )

    def is_valid_booking_id(value):
        value = value.strip().upper()

        if not value:
            return False

        # Pure numeric IDs:
        # 489424
        # 487585
        # 688657
        if re.fullmatch(r"\d{5,7}", value):
            return True

        # Prefix + numeric:
        # CYP-394571
        # CTP-392764
        # P-393009
        # EUP-2000031
        if re.fullmatch(r"[A-Z][A-Z0-9]{0,5}-\d{5,7}", value):
            return True

        # Prefix + number + number:
        # CAP-18-675468
        # CPD-19-631404
        # AOA-1-23668
        # P4U-1-678492
        if re.fullmatch(
            r"[A-Z][A-Z0-9]{0,5}-\d{1,2}-\d{5,7}",
            value
        ):
            return True

        # Prefix + prefix + number:
        # CP-STA-1204
        # CP-STA-0570
        if re.fullmatch(
            r"[A-Z][A-Z0-9]{0,5}-[A-Z][A-Z0-9]{0,5}-\d{3,7}",
            value
        ):
            return True

        return False

    def extract_booking_id(line):
        line = clean_line(line)

        if not line:
            return None

        normalized = line.upper()

        # Remove Markdown formatting that may surround the ID.
        normalized = normalized.replace("**", "").replace("__", "")

        # First check whether the complete line is an ID.
        if is_valid_booking_id(normalized):
            return normalized

        # Extract structured hyphenated IDs first.
        # This handles:
        # CAP-18-675468
        # CPD-19-631404
        # CP-STA-1204
        # CYP-394571
        # P4U-1-678492
        hyphenated_pattern = re.compile(
            r"(?<![A-Z0-9])"
            r"(?:[A-Z][A-Z0-9]{0,5}-[A-Z][A-Z0-9]{0,5}-\d{3,7}"
            r"|[A-Z][A-Z0-9]{0,5}-\d{1,2}-\d{5,7}"
            r"|[A-Z][A-Z0-9]{0,5}-\d{5,7})"
            r"(?![A-Z0-9])",
            re.I
        )

        match = hyphenated_pattern.search(normalized)

        if match:
            candidate = match.group(0).upper()

            if is_valid_booking_id(candidate):
                return candidate

        # Extract standalone numeric IDs.
        # Word boundaries prevent extracting part of a larger number.
        numeric_matches = re.findall(
            r"(?<!\d)\d{5,7}(?!\d)",
            normalized
        )

        for candidate in numeric_matches:
            if is_valid_booking_id(candidate):
                return candidate

        return None

    for raw_block in blocks:
        lines = [clean_line(line) for line in raw_block.splitlines()]
        lines = [line for line in lines if line]

        if not lines:
            continue

        booking_ref = None
        customer_name = None
        booking_date = None

        # Find customer line.
        customer_index = None

        for i, line in enumerate(lines):
            if customer_pattern.match(line):
                customer_name = line
                customer_index = i
                break

        # Booking reference is normally before the customer.
        if customer_index is not None:
            for i in range(customer_index - 1, -1, -1):
                candidate = extract_booking_id(lines[i])

                if candidate:
                    if not is_vehicle_reg(lines[i]):
                        booking_ref = candidate
                        break

        # Fallback: search the entire block.
        if not booking_ref:
            for line in lines:
                if is_time(line):
                    continue

                candidate = extract_booking_id(line)

                if candidate and not is_vehicle_reg(line):
                    booking_ref = candidate
                    break

        # Find first date after customer.
        if customer_index is not None:
            for line in lines[customer_index + 1:]:
                if date_pattern.match(line):
                    booking_date = line
                    break

        # Fallback: search entire block for date.
        if not booking_date:
            for line in lines:
                if date_pattern.match(line):
                    booking_date = line
                    break

        if booking_ref and booking_ref not in seen_ids:
            seen_ids.add(booking_ref)

            results.append({
                "id": booking_ref,
                "name": customer_name.replace("\t", " ").strip() if customer_name else "",
                "date": standardize_date(booking_date) if booking_date else ""
            })

    return results


def safe_save_json(data, filepath):
    dirname = os.path.dirname(filepath) or "."

    with tempfile.NamedTemporaryFile(
        "w",
        dir=dirname,
        delete=False,
        encoding="utf-8"
    ) as tf:
        json.dump(data, tf, indent=4, ensure_ascii=False)
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

# # # # # # Run the parser and print as formatted JSON
# extracted_data = parse_bookings(raw_text)
# print(json.dumps(extracted_data, indent=4))
# safe_save_json(extracted_data,"bookings_data.json")