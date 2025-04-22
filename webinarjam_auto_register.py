import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import os
import requests
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",  # Log format
    handlers=[
        logging.FileHandler("webinarjam_auto_register.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console
    ]
)

# Load environment variables from .env only in local development
if os.getenv("RENDER") is None:  # Render sets this variable automatically
    from dotenv import load_dotenv
    load_dotenv()

WEBINARJAM_API_KEY = os.getenv("WEBINARJAM_API_KEY")
WEBINAR_ID = os.getenv("WEBINARJAM_WEBINAR_ID")
WEBINAR_SCHEDULE_ID = os.getenv("WEBINARJAM_WEBINAR_SCHEDULE_ID")
register_url = "https://api.webinarjam.com/webinarjam/register"
ghl_webhook_url = "https://services.leadconnectorhq.com/hooks/kFKnF888dp7eKChjLxb9/webhook-trigger/5f369931-bb5a-4b15-b836-e675c867d211"

# Check if all environment variables are set
if not all([WEBINARJAM_API_KEY, WEBINAR_ID, WEBINAR_SCHEDULE_ID]):
    logging.error("One or more required environment variables are missing.")
    raise RuntimeError("Please ensure WEBINARJAM_API_KEY, WEBINARJAM_WEBINAR_ID, and WEBINARJAM_WEBINAR_SCHEDULE_ID are set.")

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
    Register a contact for the WebinarJam webinar and send data to GHL Webhook.
    """
    logging.info(f"Received registration request for: {contact.name}, {contact.email}")

    # Split the name into first and last name
    name_parts = contact.name.split()
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Ensure the phone number contains only digits
    phone = "".join(filter(str.isdigit, contact.phone)) if contact.phone else None

    # Create payload for WebinarJam API
    payload = {
        "api_key": WEBINARJAM_API_KEY,
        "webinar_id": WEBINAR_ID,
        "schedule": WEBINAR_SCHEDULE_ID,
        "first_name": first_name,
        "last_name": last_name,
        "email": contact.email,
        "phone": phone
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempt {attempt + 1}: Sending request to WebinarJam API.")
            response = requests.post(register_url, data=payload, headers=headers)

            # Add a 2-second delay to handle rate-limiting
            time.sleep(2)

            # Log the raw response for debugging
            logging.info(f"Attempt {attempt + 1}: Response status code: {response.status_code}")
            logging.debug(f"Attempt {attempt + 1}: Response text: {response.text}")

            # Handle 502 Bad Gateway errors with retries
            if response.status_code == 502:
                logging.warning(f"Attempt {attempt + 1}: Received 502 Bad Gateway. Retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue

            # Check if the HTTP status code indicates success
            if response.status_code == 200:
                try:
                    response_json = response.json()
                except ValueError:
                    logging.error("WebinarJam API returned an invalid response.")
                    raise HTTPException(
                        status_code=500,
                        detail=f"WebinarJam API returned an invalid response: {response.text}"
                    )

                # Check if the API's custom status field indicates success
                if response_json.get("status") == "success":
                    user = response_json.get("user", {})
                    logging.info(f"Successfully registered contact: {contact.email}")

                    # Send data to GHL Webhook
                    ghl_payload = {
                        "email": contact.email,
                        "user_id": user.get("user_id"),
                        "live_room_url": user.get("live_room_url"),
                        "replay_room_url": user.get("replay_room_url"),
                        "thank_you_url": user.get("thank_you_url")
                    }
                    ghl_response = requests.post(ghl_webhook_url, json=ghl_payload)

                    if ghl_response.status_code == 200:
                        logging.info(f"Successfully sent data to GHL Webhook for user_id: {user.get('user_id')}")
                    else:
                        logging.error(f"Failed to send data to GHL Webhook. Status code: {ghl_response.status_code}. Response: {ghl_response.text}")

                    return {
                        "message": "Contact successfully registered for the webinar and data sent to GHL Webhook.",
                        "user_id": user.get("user_id"),
                        "live_room_url": user.get("live_room_url"),
                        "replay_room_url": user.get("replay_room_url"),
                        "thank_you_url": user.get("thank_you_url")
                    }
                else:
                    logging.error(f"Failed to register contact. WebinarJam API responded with: {response_json.get('error', 'Unknown error')}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to register contact. WebinarJam API responded with: {response_json.get('error', 'Unknown error')}"
                    )
            else:
                # Handle unexpected HTTP status codes
                logging.error(f"Unexpected HTTP status code: {response.status_code}. Response: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to register contact. WebinarJam API responded with: {response.text}"
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"An error occurred while communicating with the WebinarJam API: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"An error occurred while communicating with the WebinarJam API: {str(e)}"
            )
    else:
        # If all retries fail, raise an exception
        logging.error("WebinarJam API is currently unavailable after multiple attempts.")
        raise HTTPException(
            status_code=502,
            detail="WebinarJam API is currently unavailable after multiple attempts. Please try again later."
        )
