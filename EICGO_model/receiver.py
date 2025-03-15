import sys
import requests
import sqlite3
import math
import json
import re
import time
from datetime import datetime
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient, AnalysisFeature
from azure.core.exceptions import HttpResponseError
from groq import Groq
import os
import qrcode
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# Fetch Firebase credentials
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

# Haversine formula to calculate the distance between two points on the Earth
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # Radius of the Earth in kilometers
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Function to fetch post offices by pincode from the database
def fetch_post_offices_by_pincode(pincode):
    conn = sqlite3.connect('post_office.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT OfficeName, Pincode, Delivery, StateName, Latitude, Longitude, OfficeType 
        FROM PostOfficeDetails WHERE Pincode = ?
    """, (pincode,))
    post_offices = cursor.fetchall()
    conn.close()

    post_offices_list = []
    for row in post_offices:
        latitude = float(row[4]) if row[4] is not None else None
        longitude = None
        if row[5] is not None:
            longitude_str = str(row[5])
            if longitude_str.replace('.', '', 1).replace('-', '', 1).isdigit():
                longitude = float(longitude_str)
        
        if latitude is not None and longitude is not None:
            post_offices_list.append({
                "name": row[0],
                "pincode": row[1],
                "delivery_type": row[2],
                "state": row[3],
                "latitude": latitude,
                "longitude": longitude,
                "office_type": row[6]
            })
    return post_offices_list

# Function to geocode an address using Google Geocoding API
def geocode_address(api_key, addr, pincode):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    address = addr + pincode
    params = {"address": address, "key": api_key}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get("results"):
            result = data["results"][0]
            geometry = result["geometry"]
            address_components = result["address_components"]

            output = {
                "formattedAddress": result.get("formatted_address", ""),
                "latitude": geometry["location"]["lat"],
                "longitude": geometry["location"]["lng"],
                "pincode": "",
                "city": "",
                "state": ""
            }
            for component in address_components:
                if "locality" in component.get("types", []):
                    output["city"] = component["long_name"]
                if "administrative_area_level_1" in component.get("types", []):
                    output["state"] = component["long_name"]
                if "postal_code" in component.get("types", []):
                    output["pincode"] = component["long_name"]
            return output
    return {"error": f"Geocoding failed: {response.status_code}"}

# Function to find the nearest post office to a given address
def find_nearest_post_office(api_key, pc, address):
    geocoded_info = geocode_address(api_key, address, pc)
    if "error" in geocoded_info:
        return geocoded_info
    
    lat, lon, pincode = geocoded_info["latitude"], geocoded_info["longitude"], geocoded_info["pincode"]
    post_offices = fetch_post_offices_by_pincode(pc)

    if not post_offices:
        print(pc)
        return {"error": "No post offices found for the given pincode"}
    
    nearest_post_office = None
    min_distance = float('inf')

    for post_office in post_offices:
        distance = haversine(lat, lon, post_office["latitude"], post_office["longitude"])
        if distance < min_distance:
            min_distance = distance
            nearest_post_office = post_office

    return nearest_post_office if nearest_post_office else {"error": "No nearest post office found"}

# Function to create a Google Maps link for a location
def create_google_maps_link(latitude, longitude):
    return f"https://www.google.com/maps?q={latitude},{longitude}"

# Load environment variables
load_dotenv()

def process_photo(photo_path):
    # Fetch Azure credentials from environment variables
    endpoint = os.getenv("AZURE_OCR_ENDPOINT")
    key = os.getenv("AZURE_OCR_KEY")

    if not endpoint or not key:
        raise ValueError("Azure OCR credentials (endpoint and key) are not set in .env")

    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint, credential=AzureKeyCredential(key)
    )

    with open(photo_path, "rb") as f:
        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-read", document=f, features=[AnalysisFeature.LANGUAGES]
        )
    
    result = poller.result()

    address = " ".join(line.content for page in result.pages for line in page.lines)

    return address.strip()

def extract_address_details(address):
    try:
    # Fetch API key from .env
        apikey = os.getenv("GROQ_API_KEY")

        if not apikey:
            raise ValueError("Groq API key is not set in .env")

        client = Groq(api_key=apikey)

        # Sending the request to Groq API to process the address
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Identify Address, Pincode, Phone Number, and Name if present.
                    Note: Dont give any other information just provide the asked information in the specified format. 
                    print that in this sequence: Name, PhoneNumber, Address, Pincode.
                    i want the ouput in json format.
                    """
                },
                {
                    "role": "user",
                    "content": address
                }
            ],
            temperature=1,
            max_tokens=1024,
            top_p=1,
            stream=True,
            stop=None,
        )

        response_content = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:  # Check for valid content
                response_content += chunk.choices[0].delta.content

        # Debug: Print full response content before parsing
        print("Response Content:", response_content)

        # Extracting only the JSON part using regex
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)  # Get the matched JSON string
            dic = json.loads(json_str)  # Parse it into a dictionary
            return dic
        else:
            print("No valid JSON found in response.")
    
    except json.JSONDecodeError as e:
        print("Error decoding JSON(llama):", e)
    except Exception as e:
        print("An error occurred(llama):", e)

    return None  # Return None in case of an error


# Function to generate unique post_id
def generate_unique_post_id():
    timestamp = int(time.time() * 1000)
    return str(timestamp)[:12]

# Function to upload data to Firestore
def upload_to_firestore(post_id, data):
    try:
        db.collection("post_details").document(post_id).set(data)
        print(f"Data uploaded successfully with post_id: {post_id}")
    except Exception as e:
        print(f"Error uploading data to Firestore: {e}")
        


def generate_qr_code(data, pincode=None, post_office_name=None, output_path="qr_code.png"):
    try:
        folder_path = "QR"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        qr = qrcode.make(data)
        qr_image = qr.convert('RGB')
        
        margin_top = 50
        width, height = qr_image.size
        new_image = Image.new('RGB', (width, height + margin_top), (255, 255, 255))
        new_image.paste(qr_image, (0, margin_top))
        
        draw = ImageDraw.Draw(new_image)
        
        try:
            font = ImageFont.truetype("arial.ttf", 25)
        except IOError:
            font = ImageFont.load_default()
        
        text = f"Pincode: {pincode}\nPost Office: {post_office_name}"
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = (width - text_width) // 2  # Center text horizontally
        text_y = 10
        
        draw.text((text_x, text_y), text, font=font, fill="black")
        
        output_path = os.path.join(folder_path, output_path)
        new_image.save(output_path)
        print(f"QR code generated and saved as {output_path}")
    
    except Exception as e:
        print(f"Error generating QR code: {e}")
        

# Main execution flow
if __name__ == "__main__":
    try:
        # Fetch photo path from command-line arguments
        if len(sys.argv) < 2:
            print("Error: Please provide a photo path!")
            sys.exit(1)

        photo_path = sys.argv[1]

        if not os.path.exists(photo_path):
            raise FileNotFoundError(f"No such file or directory: {photo_path}")

        # Extract text from photo (Azure)
        address = process_photo(photo_path)

        # Extract structured details
        address_details = extract_address_details(address)
        receiver_name = address_details.get('Name')
        receiver_phone_number = address_details.get('PhoneNumber')
        receiver_address = address_details.get('Address')
        receiver_pincode = address_details.get('Pincode')

        # Geocode and find nearest post office
        with open("credentials.json", "r") as file:
            credentials = json.load(file)
        
        api_key = credentials["google_api_key"]
        geocoded_info = geocode_address(api_key, receiver_address ,receiver_pincode)
        if "pincode" in geocoded_info:
            correct_receiver_pincode = geocoded_info["pincode"]
        else :
            correct_receiver_pincode = receiver_pincode    
            print("Pincode:", correct_receiver_pincode)
        if "formattedAddress" in geocoded_info:
            updated_receiver_address = geocoded_info["formattedAddress"]
            print("formattedAddress:", updated_receiver_address)  
        else :
            updated_receiver_address = receiver_address                  
        print(correct_receiver_pincode, receiver_pincode, updated_receiver_address, receiver_address)            
        nearest_post_office = find_nearest_post_office(api_key, correct_receiver_pincode, updated_receiver_address)
        near_po_name = nearest_post_office.get("name", "Unknown")
        near_pincode = nearest_post_office.get("pincode", "Unknown")
        print(nearest_post_office)
        # Generate unique post_id
        
        print(near_po_name, near_pincode)
        post_id = generate_unique_post_id()
        current_time = datetime.now().strftime("%I:%M %p")  # Time in 12-hour format
        current_date = datetime.now().strftime("%Y-%m-%d")  # Date in YYYY-MM-DD format
        
        initial_event = {
        "date": current_date,
        "time": current_time,
        "location": "post office",
        "status": "Post Received",
        }
        # Prepare data for Firestore
        data = {
            "isDelivered" : False,
            "receiver_details": {
                "post_id": post_id,
                "name": receiver_name,
                "phone_number": receiver_phone_number,
                "address":receiver_address,
                "pincode": receiver_pincode
            },
            "geocoded_info": geocoded_info,
            "nearest_post_office": nearest_post_office,
            "updated_at": datetime.now(),
            "events": [initial_event]  # Add the initial event to the events array
            
        }

        # Upload to Firestore
        upload_to_firestore(post_id, data)
        
        # Assuming you already have post_id, near_pincode, and near_po_name defined
        qr_link = f"https://cd6d-49-249-229-42.ngrok-free.app/check_delivery?post_id={post_id}"
        print(qr_link)

        # Generate QR code with the URL
        output_path = f"{post_id}.png"  # Save the QR code as {post_id}.png
        generate_qr_code(qr_link, near_pincode, near_po_name, output_path)
        
        
        
        receiver_data_json = {
            "azure": address,
            "post_id": post_id,
            "receiver_details": {
                "post_id": post_id,
                "name": receiver_name,
                "phone_number": receiver_phone_number,
                "address":receiver_address,
                "pincode": receiver_pincode
            },
            "geocoded_info": geocoded_info,
            "nearest_post_office": nearest_post_office,
            "events": [
                {
                    "date": initial_event["date"],
                    "time": initial_event["time"],
                    "location": initial_event["location"],
                    "status": initial_event["status"],
                }
            ],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Format datetime as string
        }

        # Save the receiver_data to receiver.json
        with open("receiver.json", "w") as json_file:
            json.dump(receiver_data_json, json_file, indent=4)
        
        print(json.dumps({"post_id": post_id}))
        sys.exit(0)  # Clean exit
        
        
        
    except Exception as e:
        print("Error:", str(e))
        sys.exit(1)  # Error exit
