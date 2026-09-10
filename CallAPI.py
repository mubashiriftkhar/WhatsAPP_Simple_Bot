import time
import requests
import os
import json
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

def get_bulk_bookings(airport, start_date, end_date, json_file_path="bookings.json", excel_output_path="bookings_output.xlsx"):
    url = os.getenv("base_url")
    headers = {
        "X-API-KEY": os.getenv("my_api_key"),
        "Content-Type": "application/json"
    }
    
    all_bookings = []
    current_page = 1
    total_pages = 1 
    
    # ---------------------------------------------------------
    # 1. API DATA RETRIEVAL
    # ---------------------------------------------------------
    while current_page <= total_pages:
        payload = {
            "airport": airport,
            "start_date": start_date,
            "end_date": end_date,
            "page": current_page,
            "per_page": 200
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            print(f"Rate limit exceeded. Waiting for {retry_after} seconds...")
            time.sleep(retry_after)
            continue
            
        if response.status_code == 500:
            print("Database error encountered. Retrying in 5 seconds...")
            time.sleep(5)
            continue
            
        if response.status_code == 401:
            raise ValueError(f"Authentication Failed: The API rejected your key. Server responded with: {response.text}")
            
        response.raise_for_status()
        response_data = response.json()
        
        if not response_data.get("success"):
            raise ValueError(f"API Error: {response_data.get('message')}")
            
        all_bookings.extend(response_data.get("data", []))
        
        meta = response_data.get("meta", {})
        total_pages = meta.get("total_pages", 1)
        
        print(f"Fetched page {current_page} of {total_pages}. Total items so far: {len(all_bookings)}")
        current_page += 1
        
        remaining = int(response.headers.get("X-RateLimit-Remaining", 20))
        if remaining == 0:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            if reset_time > 0:
                time.sleep(reset_time)

    # ---------------------------------------------------------
    # 2. STATUS ASSIGNMENT VIA JSON LOOKUP
    # ---------------------------------------------------------
    json_ids = set()
    
    # Safely load local IDs into a set for fast O(1) matching
    if os.path.exists(json_file_path):
        with open(json_file_path, "r") as file:
            try:
                local_data = json.load(file)
                # Extracts all "id" values from the JSON list of dictionaries
                json_ids = {item.get("id") for item in local_data if item.get("id")}
            except json.JSONDecodeError:
                print(f"Warning: {json_file_path} is empty or corrupted.")
    else:
        print(f"Warning: {json_file_path} not found. All statuses will default to 'not show'.")

    # Iterate through every booking from the API and append the "status" key
    for booking in all_bookings:
        booking_ref = booking.get("BookingRef")
        if booking_ref in json_ids:
            booking["status"] = "show"
        else:
            booking["status"] = "not show"

    # ---------------------------------------------------------
    # 3. EXCEL FILE EXPORT
    # ---------------------------------------------------------
    if all_bookings:
        # Convert the list of dictionaries directly into a DataFrame
        df = pd.DataFrame(all_bookings)
        
        # Export to Excel without the DataFrame row index numbers
        df.to_excel(excel_output_path, index=False)
        print(f"\nSuccess: Exported {len(all_bookings)} records to {excel_output_path}")
    else:
        print("\nNo bookings found for the requested date range.")

    return all_bookings

# Example Usage:
# bookings = get_bulk_bookings("bristol", "2026-01-01", "2026-01-31")
# print(bookings[0]) # Verify the status key exists in the dictionary


# Example Usage:

bookings = get_bulk_bookings("bristol", "2026-08-01", "2026-08-31")
print(f"Successfully retrieved {len(bookings)} bookings.")
print(bookings[0])