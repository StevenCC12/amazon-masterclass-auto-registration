from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import os
import requests
import time

# Load environment variables from .env only in local development
if os.getenv("RENDER") is None:  # Render sets this variable automatically
    from dotenv import load_dotenv
    load_dotenv()

WEBINARJAM_API_KEY = os.getenv("WEBINARJAM_API_KEY")
WEBINAR_ID = os.getenv("WEBINARJAM_WEBINAR_ID")
WEBINAR_SCHEDULE_ID = os.getenv("WEBINARJAM_WEBINAR_SCHEDULE_ID")
register_url = "https://api.webinarjam.com/webinarjam/register"

# Check if all environment variables are set
if not all([WEBINARJAM_API_KEY, WEBINAR_ID, WEBINAR_SCHEDULE_ID]):
    raise RuntimeError("One or more required environment variables are missing. Please ensure WEBINARJAM_API_KEY, WEBINARJAM_WEBINAR_ID, and WEBINARJAM_WEBINAR_SCHEDULE_ID are set.")

# FastAPI app
app = FastAPI()

# Pydantic model for GHL contact data
class Contact(BaseModel):
    name: str
    email: EmailStr
    phone: str

@app.post("/register")
async def register_contact(contact: Contact):
    """
    Register a contact for the WebinarJam webinar.
    """
    # Split the name into first and last name
    name_parts = contact.name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Create payload for WebinarJam API
    payload = {
        "api_key": WEBINARJAM_API_KEY,
        "webinar_id": WEBINAR_ID,
        "schedule": WEBINAR_SCHEDULE_ID,
        "first_name": first_name,
        "last_name": last_name,
        "email": contact.email,
        "phone": contact.phone
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        # Send POST request to WebinarJam API
        response = requests.post(register_url, data=payload, headers=headers)

        # Add a 2-second delay to handle rate-limiting
        time.sleep(2)

        # Log the raw response for debugging
        print(f"Raw response text: {response.text}")

        # Check if the HTTP status code indicates success
        if response.status_code == 200:
            try:
                response_json = response.json()
            except ValueError:
                raise HTTPException(
                    status_code=500,
                    detail=f"WebinarJam API returned an invalid response: {response.text}"
                )

            # Check if the API's custom status field indicates success
            if response_json.get("status") == "success":
                user = response_json.get("user", {})
                return {
                    "message": "Contact successfully registered for the webinar.",
                    "user_id": user.get("user_id"),
                    "live_room_url": user.get("live_room_url"),
                    "replay_room_url": user.get("replay_room_url"),
                    "thank_you_url": user.get("thank_you_url")
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to register contact. WebinarJam API responded with: {response_json.get('error', 'Unknown error')}"
                )
        else:
            # Handle unexpected HTTP status codes
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to register contact. WebinarJam API responded with: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        # Handle request errors
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while communicating with the WebinarJam API: {str(e)}"
        )
