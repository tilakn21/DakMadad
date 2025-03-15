from flask import Flask, request, jsonify
import os
import subprocess
import threading
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, jsonify, request, redirect
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS")
    cred_full_path = Path(__file__).parent / cred_path
    
    if not cred_path or not cred_full_path.exists():
        raise ValueError("Error: Firebase credentials file not found.")
    
    cred = credentials.Certificate(str(cred_full_path))
    firebase_admin.initialize_app(cred)
    db = firestore.client()


app = Flask(__name__)

# Directory to save uploaded photos
UPLOAD_FOLDER = "scanned_posts"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_photos(photos):
    """Background processing for the photos."""
    try:
        output = {}
        post_id = None

        # Process photo1 with receiver.py
        if '1' in photos:
            combined_script_path = os.path.abspath("receiver.py")
            print(f"Executing receiver.py with {photos['1']}")
            result_combined = subprocess.run(
                ["python", combined_script_path, photos['1']],
                text=True,
                capture_output=True,
                check=True
            )
            output_combined = result_combined.stdout.strip()
            output['combined_output'] = output_combined

            # Extract post_id from the last line of the output
            try:
                lines = output_combined.split('\n')
                last_line = lines[-1].strip()

                print(f"Last line extracted: {last_line}")

                if last_line.startswith("{") and last_line.endswith("}"):
                    result_data = json.loads(last_line)
                    post_id = result_data.get("post_id")
                    if post_id:
                        print(f"Extracted post_id: {post_id}")
                    else:
                        print("post_id not found in the last line of output.")
                else:
                    print("Last line is not valid JSON.")
            except json.JSONDecodeError as e:
                print(f"Error decoding receiver.py output: {e}")
                post_id = None

        # Execute sender.py with post_id and photo2
        if post_id and '2' in photos:
            sender_script_path = os.path.abspath("sender.py")
            print(f"Executing sender.py with {photos['2']} and post_id={post_id}")
            try:
                result_sender = subprocess.run(
                    ["python", sender_script_path, photos['2'], str(post_id)],
                    text=True,
                    capture_output=True,
                    check=True
                )
                output_sender = result_sender.stdout.strip()
                print(f"sender.py output: {output_sender}")
                output['sender_output'] = output_sender
            except subprocess.CalledProcessError as e:
                print(f"Error executing sender.py: {e.stderr}")

        # Execute message.py with post_id and message
        if post_id:
            message_script_path = os.path.abspath("message.py")
            message = "Processing completed for photos"  # Example message
            print(f"Executing message.py with post_id={post_id} and message='{message}'")
            try:
                result_message = subprocess.run(
                    ["python", message_script_path, str(post_id), message],
                    text=True,
                    capture_output=True,
                    check=True
                )
                output_message = result_message.stdout.strip()
                print(f"message.py output: {output_message}")
                output['message_output'] = output_message
            except subprocess.CalledProcessError as e:
                print(f"Error executing message.py: {e.stderr}")

        print(f"Photo processing completed with output: {output}")

    except Exception as e:
        print(f"Error in background processing: {e}")

@app.route("/upload", methods=["POST"])
def upload_photo():
    print("Received a request to /upload")

    # Initialize a dictionary to store photo paths and IDs
    photos = {}
    responses = []

    # Check and process 'photo1' and 'id1'
    if "photo1" in request.files:
        photo1 = request.files['photo1']
        id1 = request.form.get('id1')
        if not id1:
            print("Missing id1 for photo1")
            responses.append({"error": "Missing id1 for photo1"})
        else:
            photo1_path = os.path.join(UPLOAD_FOLDER, photo1.filename)
            photo1.save(photo1_path)
            photos['1'] = photo1_path
            print(f"Saved photo1 at: {photo1_path}")
            responses.append({"message": "photo1 uploaded successfully", "photo1_path": photo1_path})
    else:
        print("No photo1 part in the request")
        responses.append({"error": "No photo1 part in the request"})

    # Check and process 'photo2' and 'id2' if present
    if "photo2" in request.files:
        photo2 = request.files['photo2']
        id2 = request.form.get('id2')
        if not id2:
            print("Missing id2 for photo2")
            responses.append({"error": "Missing id2 for photo2"})
        else:
            photo2_path = os.path.join(UPLOAD_FOLDER, photo2.filename)
            photo2.save(photo2_path)
            photos['2'] = photo2_path
            print(f"Saved photo2 at: {photo2_path}")
            responses.append({"message": "photo2 uploaded successfully", "photo2_path": photo2_path})
    else:
        print("No photo2 part in the request")
        responses.append({"error": "No photo2 part in the request"})

    # Respond immediately after upload
    response = {"message": "Photos uploaded successfully", "uploads": responses}
    if photos:
        # Start a thread to process the photos in the background
        threading.Thread(target=process_photos, args=(photos,)).start()

    return jsonify(response), 200

@app.route('/check_delivery', methods=['GET'])
def check_delivery():
    # Get post_id from query parameters
    post_id = request.args.get('post_id')
    
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    
    # Fetch document from Firestore using post_id
    try:
        doc_ref = db.collection("post_details").document(post_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({"error": "Post not found"}), 404
        
        # Get the 'isDelivered' status
        is_delivered = doc.to_dict().get('isDelivered', None)
        
        if is_delivered is None:
            return jsonify({"error": "isDelivered field not found"}), 404
        
        # Redirect based on the isDelivered status
        if is_delivered:
            return redirect("https://c390-49-249-229-42.ngrok-free.app/")
            
        else:
            return redirect(f"https://cd6d-49-249-229-42.ngrok-free.app/delivery_status?post_id={post_id}")

    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/delivery_status", methods=["GET"])
def delivery_status():
    post_id = request.args.get('post_id')
    
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    
    try:
        # Fetch post details from Firestore using post_id
        post_ref = db.collection('post_details').document(post_id)
        post_doc = post_ref.get()
        
        if not post_doc.exists:
            return jsonify({"error": f"No post found with post_id {post_id}"}), 404
        
        # Extract geocoded_details (latitude and longitude) from the document
        post_data = post_doc.to_dict()
        geocoded_details = post_data.get('geocoded_info', {})
        
        latitude = geocoded_details.get('latitude')
        longitude = geocoded_details.get('longitude')
        formattedAddress = geocoded_details.get('formattedAddress')
        pincode = geocoded_details.get('pincode')
        city = geocoded_details.get('city')
        state = geocoded_details.get('state')
        
        if not latitude or not longitude:
            return jsonify({"error": "Latitude and/or longitude not found in geocoded_details"}), 400
        
        # Return the data
        return jsonify({
            "post_id": post_id,
            "geocoded_info":{
            "latitude": latitude,
            "longitude": longitude,
            "formattedAddress": formattedAddress,
            "pincode": pincode,
            "city": city,
            "state": state,
            }
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
@app.route("/")
def home():
    return "Flask server is running! Use the /upload endpoint to upload photos."


if __name__ == "__main__":
    app.run(debug=True)