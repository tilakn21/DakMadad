import os
import sys
import json
import re
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.exceptions import HttpResponseError

from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Retrieve API keys securely
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_KEY = os.getenv("AZURE_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not AZURE_KEY or not GROQ_API_KEY:
    raise ValueError("Missing API keys. Make sure to set them in the .env file.")

# Retrieve and initialize Firebase credentials
firebase_credentials = os.getenv("FIREBASE_CREDENTIALS")

if firebase_credentials:
    cred_path = os.path.abspath(firebase_credentials)  # Convert to absolute path
    if not os.path.exists(cred_path):
        raise ValueError(f"Firebase credentials file not found at {cred_path}.")

    cred = credentials.Certificate(cred_path)

    if not firebase_admin._apps:  # Ensure Firebase is initialized only once
        firebase_admin.initialize_app(cred)

    db = firestore.client()
else:
    raise ValueError("FIREBASE_CREDENTIALS environment variable is not set.")

def upload_to_firestore(post_id, data):
    try:
        doc_ref = db.collection("post_details").document(post_id)
        doc_ref.set({"sender_details": data}, merge=True)
        print(f"Data uploaded successfully for post_id: {post_id}")
    except Exception as e:
        print(f"Error uploading data to Firestore: {e}")

def extract_text_from_image(photo_path):
    """
    Extracts plain text from the given image using Azure's OCR service.
    
    Args:
        photo_path (str): Path to the image file.
    
    Returns:
        str: Extracted text from the image.
    """
    document_analysis_client = DocumentAnalysisClient(
        endpoint=AZURE_ENDPOINT, credential=AzureKeyCredential(AZURE_KEY)
    )

    with open(photo_path, "rb") as f:
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-read", document=f
        )
    result = poller.result()

    # Combine text from all lines across all pages
    extracted_text = " ".join(
        line.content for page in result.pages for line in page.lines
    )
    
    return extracted_text.strip()

def analyze_address_with_groq(address_text):
    try:
        client = Groq(api_key=GROQ_API_KEY)

        # Sending the request to Groq API to process the address
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Identify Address, Pincode, Phone Number, and Name if present.
                    Note: Don't give any other information, just provide the requested information in JSON format.
                    Format: { "Name": "value", "PhoneNumber": "value", "Address": "value", "Pincode": "value" }
                    """
                },
                {
                    "role": "user",
                    "content": address_text
                }
            ],
            temperature=1,
            max_tokens=1024,
            top_p=1,
            stream=True,
        )

        response_content = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                response_content += chunk.choices[0].delta.content

        # Extracting only the JSON part using regex
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)
            dic = json.loads(json_str)
            return dic
        else:
            print("No valid JSON found in response.")
    
    except json.JSONDecodeError as e:
        print("Error decoding JSON (Groq):", e)
    except Exception as e:
        print("An error occurred (Groq):", e)

    return None

def main():
    if len(sys.argv) < 2:
        print("Error: Please provide the photo path as an argument!")
        sys.exit(1)

    photo_path = sys.argv[1]
    post_id = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(photo_path):
        print(f"Error: The file {photo_path} does not exist.")
        sys.exit(1)

    if post_id:
        print(f"Received post_id: {post_id}")
    else:
        print("No post_id provided. Proceeding without it.")

    try:
        text = extract_text_from_image(photo_path)

        if not text:
            print("Error: Failed to extract text from the image.")
            sys.exit(1)

        groq_result = analyze_address_with_groq(text)

        sender_data = {
            "photo_path": photo_path,
            "post_id": post_id or "N/A",
            "extracted_data": {
                "text": text
            },
            "groq_analysis": groq_result,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Save to sender.json
        with open("sender.json", "w") as json_file:
            json.dump(sender_data, json_file, indent=4)

        # Upload to Firestore
        if post_id:
            upload_to_firestore(post_id, groq_result)
        else:
            print("No post_id provided. Data not uploaded to Firestore.")
    except HttpResponseError as error:
        print("Azure OCR Error:", error)
    except Exception as e:
        print("Unexpected Error:", e)

if __name__ == "__main__":
    main()
