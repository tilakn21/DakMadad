import sys
import firebase_admin
from firebase_admin import credentials, firestore
from twilio.rest import Client
import re
import os
from dotenv import load_dotenv
from pathlib import Path

# Set correct path to .env inside EICGO
env_path = Path(__file__).parent / "EICGO" / ".env"
load_dotenv(dotenv_path=env_path)

# Twilio credentials from .env
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
client = Client(account_sid, auth_token)

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS")  # Firebase JSON filename from .env
    cred_full_path = Path(__file__).parent / "EICGO" / cred_path  # Adjust for EICGO folder

    if not cred_path or not cred_full_path.exists():
        print("Error: Firebase credentials file not found.")
        sys.exit(1)

    cred = credentials.Certificate(str(cred_full_path))
    firebase_admin.initialize_app(cred)

# Validate input arguments
if len(sys.argv) != 3:
    print("Usage: python message.py <post_id> <message>")
    sys.exit(1)

post_id = sys.argv[1]
message_content = f"Dear user, your post is received and is in transit. You can click on the link to track the post: https://7a8e-49-249-229-42.ngrok-free.app/Tracking?page={post_id}"

# Firestore client
db = firestore.client()

try:
    # Fetch the document based on post_id
    post_details = db.collection("post_details").document(post_id).get()

    if post_details.exists:
        data = post_details.to_dict()

        # Extract raw phone numbers
        raw_receiver_phone = data.get("receiver_details", {}).get("phone_number", None)
        raw_sender_phone = data.get("sender_details", {}).get("PhoneNumber", None)

        # Log raw phone numbers
        print(f"Raw Receiver Phone: {raw_receiver_phone}")
        print(f"Raw Sender Phone: {raw_sender_phone}")

        # Function to format phone number to E.164 standard
        def format_phone_number(phone):
            if phone:
                phone = phone.strip()  # Remove any leading or trailing spaces
                if not phone.startswith("+91") and len(phone) == 10 and phone.isdigit():
                    phone = f"+91{phone}"  # Add +91 for Indian numbers if missing
                elif not phone.startswith("+") and phone.isdigit():
                    phone = f"+{phone}"  # Handle other missing '+' for international numbers
            return phone

        # Function to validate phone number
        def is_valid_phone_number(phone):
            return bool(re.fullmatch(r'\+?[1-9]\d{1,14}$', phone))  # Regex for E.164 format

        # Format and validate phone numbers
        receiver_phone = format_phone_number(raw_receiver_phone)
        sender_phone = format_phone_number(raw_sender_phone)

        if not is_valid_phone_number(receiver_phone):
            print(f"Invalid receiver phone number: {receiver_phone}")
            receiver_phone = None
        if not is_valid_phone_number(sender_phone):
            print(f"Invalid sender phone number: {sender_phone}")
            sender_phone = None

        # Extract names
        receiver_name = data.get("receiver_details", {}).get("name", "Receiver")
        sender_name = data.get("sender_details", {}).get("Name", "Sender")

        # Send message to receiver
        if receiver_phone:
            print(f"Sending message to receiver: {receiver_phone}")
            message = client.messages.create(
                to=receiver_phone,
                from_=twilio_number,
                body=message_content
            )
            print(f"Message sent to receiver: {receiver_phone}, SID: {message.sid}")
        else:
            print("Skipping message to receiver due to invalid phone number.")

        # Send message to sender
        if sender_phone:
            print(f"Sending message to sender: {sender_phone}")
            message = client.messages.create(
                to=sender_phone,
                from_=twilio_number,
                body=message_content
            )
            print(f"Message sent to sender: {sender_phone}, SID: {message.sid}")
        else:
            print("Skipping message to sender due to invalid phone number.")

    else:
        print(f"No document found for post_id: {post_id}")

except Exception as e:
    print(f"Error: {e}")
