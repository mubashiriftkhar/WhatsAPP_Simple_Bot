import os
import asyncio
import re
from fastapi import FastAPI, Form, Response, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

# Your custom module imports
from parser import parse_bookings, safe_save_json
from CallAPI import get_bulk_bookings

load_dotenv() 

app = FastAPI()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID") or os.getenv("account_sid")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN") or os.getenv("auth_token")

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    raise ValueError("Twilio credentials are missing! Check your .env file.")

TWILIO_WHATSAPP_NUMBER = "whatsapp:+447853312183" 

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

class OutboundMessage(BaseModel):
    to_number: str
    message_body: str

async def delete_file_after_delay(file_path: str, delay_seconds: int = 120):
    """Waits for Twilio to download the file, then deletes it from the server."""
    await asyncio.sleep(delay_seconds)
    if os.path.exists(file_path) and not file_path.endswith("bookings_data.json"):
        os.remove(file_path)
        print(f"Cleaned up temporary file: {file_path}")

def process_heavy_report(airport: str, start_date: str, end_date: str, excel_filename: str, user_phone: str, base_url: str, background_tasks: BackgroundTasks):
    try:
        print(f"Starting background export for {airport}...")
        
        get_bulk_bookings(
            airport=airport, 
            start_date=start_date, 
            end_date=end_date, 
            json_file_path="bookings_data.json", 
            excel_output_path=excel_filename
        )
        
        background_tasks.add_task(delete_file_after_delay, excel_filename, 120)
        
        media_url = f"{base_url}/download/{excel_filename}"
        
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=f"Here is your data report for {airport} ({start_date} to {end_date}):",
            media_url=[media_url],
            to=user_phone
        )
        print(f"Successfully sent heavy report to {user_phone}")
        
    except Exception as e:
        print(f"Background process failed: {str(e)}")
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=f"Report generation failed: {str(e)}",
            to=user_phone
        )

# ---------------------------------------------------------
# 1. FILE SERVING ENDPOINT
# ---------------------------------------------------------
@app.get("/download/{filename}")
async def download_file(filename: str):
    """Serves Excel or JSON files so Twilio can download and attach them to WhatsApp."""
    file_path = f"./{filename}"
    if os.path.exists(file_path):
        media_type = 'application/json' if filename.endswith('.json') else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type=media_type
        )
    return Response(content="File not found.", status_code=404)

# ---------------------------------------------------------
# 2. WHATSAPP WEBHOOK ROUTER
# ---------------------------------------------------------
@app.post("/webhook")
async def receive_whatsapp_message(
    request: Request, 
    background_tasks: BackgroundTasks, 
    From: str = Form(...), 
    Body: str = Form(...)
):
    """Parses incoming text and triggers the appropriate workflow."""
    twiml_response = MessagingResponse()
    message_body = Body.strip()
    
    try:
        base_url = str(request.base_url).rstrip("/").replace("http://", "https://")

        # CONDITION 1: Check if message is "0000" to send bookings_data.json
        if message_body == os.getenv("bookingFile"):
            json_filename = "bookings_data.json"
            if os.path.exists(json_filename):
                media_url = f"{base_url}/download/{json_filename}"
                msg = twiml_response.message("Here is your current bookings database JSON file:")
                msg.media(media_url)
                return Response(content=str(twiml_response), media_type="application/xml")
            else:
                twiml_response.message("The bookings database file does not exist yet.")
                return Response(content=str(twiml_response), media_type="application/xml")

        # CONDITION 2: Check if message is "Airport, StartDate, EndDate"
        date_query_pattern = re.compile(r'^([A-Za-z\s]+)\s*,\s*(\d{4}-\d{2}-\d{2})\s*,\s*(\d{4}-\d{2}-\d{2})$')
        query_match = date_query_pattern.match(message_body)
        
        if query_match:
            airport, start_date, end_date = query_match.groups()
            airport = airport.strip().lower()
            excel_filename = f"bookings_{airport}_{start_date}.xlsx"
            
            background_tasks.add_task(
                process_heavy_report, 
                airport, start_date, end_date, excel_filename, From, base_url, background_tasks
            )
            
            twiml_response.message(f"Your request for {airport} data is processing. This will take a moment, and the Excel file will be sent to you shortly.")
            return Response(content=str(twiml_response), media_type="application/xml")

        # CONDITION 3: Check if message contains raw booking text
        extracted_data = parse_bookings(message_body)
        
        if extracted_data:
            safe_save_json(extracted_data, "bookings_data.json")
            saved_ids = [item['id'] for item in extracted_data]
            summary_text = f"Successfully extracted and saved {len(extracted_data)} records.\nIDs: {', '.join(saved_ids)}"
            
            twiml_response.message(summary_text)
            return Response(content=str(twiml_response), media_type="application/xml")

        # CONDITION 4: Message does not match any known format
        twiml_response.message("Invalid message format.\n\n- Send raw booking text to update database\n- Send '0000' to get bookings.json\n- Send 'Airport, YYYY-MM-DD, YYYY-MM-DD' for Excel report.")
        return Response(content=str(twiml_response), media_type="application/xml")

    except Exception as e:
        twiml_response.message(f"Process Failed: {str(e)}")
        return Response(content=str(twiml_response), media_type="application/xml")

# ---------------------------------------------------------
# 3. PROACTIVE SEND ENDPOINT
# ---------------------------------------------------------
@app.post("/send")
async def send_whatsapp_message(payload: OutboundMessage):
    """Sends a new, proactive outbound WhatsApp message."""
    cleaned_to = payload.to_number.replace(" ", "")
    formatted_to = cleaned_to if cleaned_to.startswith("whatsapp:") else f"whatsapp:{cleaned_to}"
    
    try:
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=payload.message_body,
            to=formatted_to  
        )
        return {"status": "success", "message_sid": message.sid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))