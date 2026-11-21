
import os
import re
import json
import logging
import threading
from datetime import date
from urllib.parse import urlparse
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

from parser import parse_bookings, safe_save_json
from CallAPI import get_bulk_bookings

load_dotenv()

app = FastAPI(title="Compare My Parking Bot API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

JSON_FILE_PATH = os.path.join(BASE_DIR, "bookings_data.json")
GROUP_STATE_PATH = os.path.join(BASE_DIR, "group_messages_state.json")
REPORT_STATE_PATH = os.path.join(BASE_DIR, "completed_reports.json")

BOOKING_FILE_COMMAND = os.getenv("bookingFile", "0000")

COMPANY_API_HOST = "comparemyairportparking.com"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

group_lock = threading.Lock()
report_lock = threading.Lock()

active_jobs = set()


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class Airport(BaseModel):
    id: int
    name: str


class ReportRequest(BaseModel):
    jobId: str
    airport: Airport
    fromDate: date
    toDate: date
    format: str
    requestedBy: dict[str, Any]
    resultUrl: HttpUrl


# ---------------------------------------------------------
# JSON HELPERS
# ---------------------------------------------------------

def load_json_file(file_path: str, default: Any = None):
    if default is None:
        default = []

    if not os.path.exists(file_path):
        return default

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def save_state(file_path: str, data: Any):
    temp_path = file_path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    os.replace(temp_path, file_path)


def get_bookings():
    data = load_json_file(JSON_FILE_PATH, [])
    return data if isinstance(data, list) else []


def save_bookings(data: list):
    safe_save_json(data, JSON_FILE_PATH)


def normalize_event_id(value):
    return str(value)


def is_newer_event(new_event_id, old_event_id):
    try:
        return int(new_event_id) > int(old_event_id)
    except (ValueError, TypeError):
        return str(new_event_id) != str(old_event_id)


def safe_filename(value: str):
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
    return value.strip("_") or "report"


# ---------------------------------------------------------
# 1. GROUP MESSAGE PROCESSING
# ---------------------------------------------------------

def process_group_message(payload: dict):
    event = payload.get("event")
    event_id = payload.get("eventId")
    message = payload.get("message") or {}

    if event not in {
        "message.created",
        "message.edited",
        "message.deleted"
    }:
        raise HTTPException(status_code=400, detail="Invalid event type.")

    if event_id is None:
        raise HTTPException(status_code=400, detail="eventId is required.")

    message_id = message.get("id")

    if message_id is None:
        raise HTTPException(status_code=400, detail="message.id is required.")

    event_id = normalize_event_id(event_id)
    message_id = str(message_id)

    with group_lock:

        state = load_json_file(
            GROUP_STATE_PATH,
            {
                "handled_event_ids": [],
                "messages": {}
            }
        )

        handled_events = set(state.get("handled_event_ids", []))
        stored_messages = state.get("messages", {})

        # Ignore duplicate events.
        if event_id in handled_events:
            return {
                "status": "duplicate",
                "message": "Event already processed."
            }

        previous_message = stored_messages.get(message_id)

        # Ignore an older event arriving after a newer event.
        if previous_message:
            previous_event_id = previous_message.get("event_id")

            if not is_newer_event(event_id, previous_event_id):
                handled_events.add(event_id)

                state["handled_event_ids"] = list(handled_events)
                save_state(GROUP_STATE_PATH, state)

                return {
                    "status": "ignored",
                    "message": "An older message event was received."
                }

        bookings = get_bookings()

        # Remove records associated with the previous version
        # of this group message.
        if previous_message:
            previous_booking_ids = set(
                previous_message.get("booking_ids", [])
            )

            bookings = [
                booking for booking in bookings
                if str(booking.get("id")) not in previous_booking_ids
            ]
            save_bookings(bookings)

        booking_ids = []

        # CONDITION 1: Export current bookings database.
        if event != "message.deleted":

            message_body = (message.get("text") or "").strip()

            if (
                message_body == "0000"
                or (
                    BOOKING_FILE_COMMAND
                    and message_body == BOOKING_FILE_COMMAND
                )
            ):
                handled_events.add(event_id)

                stored_messages[message_id] = {
                    "event_id": event_id,
                    "event": event,
                    "booking_ids": [],
                    "group_id": message.get("groupId"),
                    "group_name": message.get("groupName")
                }

                state["handled_event_ids"] = list(handled_events)
                state["messages"] = stored_messages

                save_state(GROUP_STATE_PATH, state)

                return {
                    "status": "success",
                    "message": "Current bookings database.",
                    "data": bookings
                }

            # CONDITION 2: Parse raw booking text.
            extracted_data = parse_bookings(message_body)

            if extracted_data:

                existing_ids = {
                    str(item["id"])
                    for item in bookings
                    if item.get("id") is not None
                }

                new_records = []

                for item in extracted_data:
                    record_id = str(item["id"])

                    if record_id not in existing_ids:
                        new_records.append(item)
                        existing_ids.add(record_id)

                bookings.extend(new_records)

                booking_ids = [
                    str(item["id"])
                    for item in extracted_data
                    if item.get("id") is not None
                ]

                save_bookings(bookings)

                response = {
                    "status": "success",
                    "message": "Booking message processed.",
                    "total_extracted": len(extracted_data),
                    "new_records": len(new_records),
                    "duplicate_records": len(extracted_data) - len(new_records),
                    "booking_ids": [
                        item["id"] for item in new_records
                    ]
                }

            else:
                # CONDITION 3: Invalid message format.
                response = {
                    "status": "ignored",
                    "message": "Invalid message format. No booking records extracted."
                }

        else:
            # CONDITION 4: Message deleted.
            if previous_message:
                save_bookings(bookings)

            response = {
                "status": "success",
                "message": "Message deleted successfully."
            }

        # Save latest message state.
        stored_messages[message_id] = {
            "event_id": event_id,
            "event": event,
            "group_id": message.get("groupId"),
            "group_name": message.get("groupName"),
            "type": message.get("type"),
            "text": message.get("text"),
            "sender": message.get("sender"),
            "created_at": message.get("createdAt"),
            "edited_at": message.get("editedAt"),
            "deleted_at": message.get("deletedAt"),
            "booking_ids": booking_ids
        }

        handled_events.add(event_id)

        state["handled_event_ids"] = list(handled_events)
        state["messages"] = stored_messages

        save_state(GROUP_STATE_PATH, state)

        return response


# ---------------------------------------------------------
# 2. GROUP MESSAGE ENDPOINT
# ---------------------------------------------------------

@app.post("/group-messages")
def receive_group_message(payload: dict):

    try:
        return process_group_message(payload)

    except HTTPException:
        raise

    except Exception:
        logger.exception("Group message processing failed.")

        raise HTTPException(
            status_code=500,
            detail="Group message processing failed."
        )


# ---------------------------------------------------------
# 3. REPORT CALLBACK
# ---------------------------------------------------------

def validate_result_url(result_url: str):

    parsed = urlparse(str(result_url))

    if (
        parsed.scheme != "https"
        or parsed.hostname != COMPANY_API_HOST
    ):
        raise ValueError("Invalid report result URL.")

    return str(result_url)


def send_report_error(result_url: str, error: str):

    try:
        response = requests.post(
            result_url,
            json={"error": error},
            timeout=30
        )

        if response.status_code == 409:
            logger.info("Report was already delivered.")

        elif response.status_code != 200:
            logger.error(
                "Report error callback failed: %s %s",
                response.status_code,
                response.text
            )

    except requests.RequestException:
        logger.exception("Unable to send report error callback.")


def send_report_file(result_url: str, file_path: str):

    filename = os.path.basename(file_path)

    mime_types = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
        ".csv": "text/csv"
    }

    extension = os.path.splitext(filename)[1].lower()
    mime_type = mime_types.get(extension)

    if not mime_type:
        raise ValueError("Unsupported report file type.")

    with open(file_path, "rb") as report_file:

        response = requests.post(
            result_url,
            files={
                "file": (filename, report_file, mime_type)
            },
            data={
                "fileName": filename
            },
            timeout=(15, 180)
        )

    if response.status_code == 409:
        logger.info("Report was already delivered.")
        return

    if response.status_code != 200:
        raise RuntimeError(
            f"Report upload failed: HTTP {response.status_code} - {response.text}"
        )

    logger.info("Report successfully delivered: %s", filename)


# ---------------------------------------------------------
# 4. REPORT JOB STATE
# ---------------------------------------------------------

def get_completed_jobs():
    data = load_json_file(REPORT_STATE_PATH, [])
    return set(data) if isinstance(data, list) else set()


def mark_job_completed(job_id: str):

    with report_lock:

        completed_jobs = get_completed_jobs()
        completed_jobs.add(job_id)

        save_state(
            REPORT_STATE_PATH,
            list(completed_jobs)
        )

        active_jobs.discard(job_id)


# ---------------------------------------------------------
# 5. BACKGROUND REPORT PROCESSING
# ---------------------------------------------------------

def process_report(job: dict):

    job_id = job["jobId"]

    result_url = job["resultUrl"]

    airport = job["airport"]["name"]

    start_date = job["fromDate"]
    end_date = job["toDate"]

    excel_filename = (
        f"bookings_{safe_filename(airport)}_"
        f"{start_date}_to_{end_date}.xlsx"
    )

    excel_path = os.path.join(BASE_DIR, excel_filename)

    try:

        logger.info(
            "Starting report job %s for airport %s",
            job_id,
            airport
        )

        # The existing API caller generates Excel reports.
        if job["format"] != "xlsx":
            raise ValueError(
                "Currently, only xlsx report generation is supported "
                "by the existing get_bulk_bookings API caller."
            )

        get_bulk_bookings(
            airport=airport.lower(),
            start_date=start_date,
            end_date=end_date,
            json_file_path=JSON_FILE_PATH,
            excel_output_path=excel_path
        )

        if not os.path.exists(excel_path):
            raise FileNotFoundError(
                "Report generator did not create the Excel file."
            )

        if os.path.getsize(excel_path) == 0:
            raise ValueError("Generated report is empty.")

        # Upload the completed file to the company's application.
        send_report_file(result_url, excel_path)

        logger.info(
            "Report job %s completed successfully.",
            job_id
        )

    except Exception as error:

        logger.exception("Report job %s failed.", job_id)

        send_report_error(
            result_url,
            str(error)
        )

    finally:

        if os.path.exists(excel_path):
            try:
                os.remove(excel_path)
            except OSError:
                logger.exception("Temporary report cleanup failed.")

        mark_job_completed(job_id)


# ---------------------------------------------------------
# 6. REPORT REQUEST ENDPOINT
# ---------------------------------------------------------

@app.post("/reports", status_code=202)
def receive_report_request(
    payload: ReportRequest,
    background_tasks: BackgroundTasks
):

    try:

        job = payload.model_dump(mode="json")

        job_id = job["jobId"]

        result_url = validate_result_url(
            job["resultUrl"]
        )

        if payload.toDate < payload.fromDate:
            raise HTTPException(
                status_code=400,
                detail="End date cannot be earlier than start date."
            )

        with report_lock:

            completed_jobs = get_completed_jobs()

            # Ignore jobs already completed.
            if job_id in completed_jobs:
                return {
                    "received": True
                }

            # Ignore jobs currently being processed.
            if job_id in active_jobs:
                return {
                    "received": True
                }

            active_jobs.add(job_id)

        job["resultUrl"] = result_url

        background_tasks.add_task(
            process_report,
            job
        )

        logger.info("Accepted report job: %s", job_id)

        return {
            "received": True
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Report request failed.")

        raise HTTPException(
            status_code=500,
            detail="Unable to process report request."
        )


# ---------------------------------------------------------
# 7. HEALTH CHECK
# ---------------------------------------------------------

@app.get("/health")
def health_check():

    return {
        "status": "running",
        "service": "Compare My Parking Bot API"
    }
