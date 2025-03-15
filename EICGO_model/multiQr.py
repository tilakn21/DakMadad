import firebase_admin
import os
import json
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, jsonify, request, redirect

# Load environment variables
load_dotenv()

# Fetch Firebase credentials
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

# Initialize Flask app
app = Flask(__name__)

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
            return redirect("https://f655-49-249-229-42.ngrok-free.app/check_delivery173392836097")
        else:
            return redirect("")
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
