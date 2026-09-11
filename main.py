import os
import asyncio
import re
from fastapi import FastAPI, Form, Response, Request, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

from parser import parse_bookings, safe_save_json
from CallAPI import get_bulk_bookings

load_dotenv() 

app = FastAPI()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+447853312183" 

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

class OutboundMessage(BaseModel):
    to_number: str
    message_body: str

async def delete_file_after_delay(file_path: str, delay_seconds: int = 120):
    await asyncio.sleep(delay_seconds)
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Cleaned up temporary file: {file_path}")

# Background worker to handle heavy scraping and proactive sending
def process_heavy_report(airport: str, start_date: str, end_date: str, excel_filename: str, user_phone: str, base_url: str, background_tasks: BackgroundTasks):
    try:
        print(f"Starting background export for {airport}...")
        
        # 1. Fetch data & build Excel (takes 60+ seconds)
        get_bulk_bookings(
            airport=airport, 
            start_date=start_date, 
            end_date=end_date, 
            json_file_path="bookings_data.json", 
            excel_output_path=excel_filename
        )
        
        # 2. Queue temporary file cleanup
        background_tasks.add_task(delete_file_after_delay, excel_filename, 120)
        
        # 3. Construct public media URL
        media_url = f"{base_url}/download/{excel_filename}"
        
        # 4. Proactively send the file to the user's WhatsApp using Twilio Client API
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

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = f"./{filename}"
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=filename, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    return Response(content="File not found.", status_code=404)

@app.post("/webhook")
async def receive_whatsapp_message(
    request: Request, 
    background_tasks: BackgroundTasks, 
    From: str = Form(...), 
    Body: str = Form(...)
):
    twiml_response = MessagingResponse()
    message_body = Body.strip()
    
    date_query_pattern = re.compile(r'^([A-Za-z\s]+)\s*,\s*(\d{4}-\d{2}-\d{2})\s*,\s*(\d{4}-\d{2}-\d{2})$')
    query_match = date_query_pattern.match(message_body)
    
    if query_match:
        airport, start_date, end_date = query_match.groups()
        airport = airport.strip().lower()
        excel_filename = f"bookings_{airport}_{start_date}.xlsx"
        base_url = str(request.base_url).rstrip("/").replace("http://", "https://")
        
        # Offload heavy lifting to background task so webhook responds instantly (< 1 sec)
        background_tasks.add_task(
            process_heavy_report, 
            airport, start_date, end_date, excel_filename, From, base_url, background_tasks
        )
        
        # Immediately tell the user the request is running
        twiml_response.message(f"Your request for {airport} data is processing. This will take a moment, and the Excel file will be sent to you shortly.")
        return Response(content=str(twiml_response), media_type="application/xml")

    # Handle standard text parsing
    extracted_data = parse_bookings(message_body)
    if extracted_data:
        safe_save_json(extracted_data, "bookings_data.json")
        saved_ids = [item['id'] for item in extracted_data]
        twiml_response.message(f"Successfully saved {len(extracted_data)} records.\nIDs: {', '.join(saved_ids)}")
        return Response(content=str(twiml_response), media_type="application/xml")

    twiml_response.message("Invalid format. Send raw text to update data, or 'Airport, YYYY-MM-DD, YYYY-MM-DD' for a report.")
    return Response(content=str(twiml_response), media_type="application/xml")