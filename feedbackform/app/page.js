'use client';

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { initializeApp } from "firebase/app";
import { getFirestore, doc, getDoc, setDoc } from "firebase/firestore";

// Firebase Configuration
const firebaseConfig = {
  apiKey: "AIzaSyDxONvcaGcMbBvY-RrVcXW8fzX30DqU4jI",
  authDomain: "india-post-cfab4.firebaseapp.com",
  databaseURL: "https://india-post-cfab4-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "india-post-cfab4",
  storageBucket: "india-post-cfab4.firebasestorage.app",
  messagingSenderId: "867503451116",
  appId: "1:867503451116:web:f079c45d0670aee672eec9"
};

// Initialize Firebase
let db;
try {
  const app = initializeApp(firebaseConfig);
  db = getFirestore(app);
  console.log("Firebase initialized successfully");
} catch (error) {
  console.error("Firebase initialization error:", error);
}

export default function FeedbackForm() {
  const searchParams = useSearchParams();
  const [postId, setPostId] = useState("");
  const [deliveredCorrectly, setDeliveredCorrectly] = useState(false);
  const [isReceived, setIsReceived] = useState(false);
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [correctAddress, setCorrectAddress] = useState("");
  const [comments, setComments] = useState("");

  useEffect(() => {
    const fetchAddress = async () => {
      const id = searchParams.get("post_id");
      console.log("Post ID from URL:", id);

      if (id) {
        setPostId(id);

        try {
          const docRef = doc(db, "post_details", id);
          const docSnap = await getDoc(docRef);

          if (docSnap.exists()) {
            const data = docSnap.data();
            console.log("Document data:", data);
            const address = data.geocoded_info?.formattedAddress || "Address not found";
            setDeliveryAddress(address);
          } else {
            console.warn("No document found for Post ID:", id);
          }
        } catch (error) {
          console.error("Error fetching delivery address:", error);
        }
      }
    };

    fetchAddress();
  }, [searchParams]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    console.log("Submitting feedback for Post ID:", postId);

    if (!postId) {
      alert("Post ID is missing. Please try again.");
      return;
    }

    const feedbackData = {
      deliveredCorrectly: deliveredCorrectly,
      postReceived: isReceived,
      deliveryAddress: isReceived ? deliveryAddress : correctAddress,
      comments: comments,
    };

    try {
      console.log("Feedback Data:", feedbackData);
      const docRef = doc(db, "address_db", postId);
      await setDoc(docRef, feedbackData);
      alert("Feedback submitted successfully!");
      console.log("Feedback submitted for Post ID:", postId);
    } catch (error) {
      console.error("Error uploading feedback:", error);
      alert("Failed to submit feedback. Please try again.");
    }
  };

  return (
    <div className="max-w-md mx-auto mt-10 p-6 border border-gray-300 rounded-lg shadow-lg bg-white">
      <form onSubmit={handleSubmit} className="space-y-5">
        <h2 className="text-2xl font-bold text-gray-800">Post Delivery Feedback</h2>
        <p className="text-sm text-gray-500">Help us improve our delivery service</p>
        
        <div className="flex items-center">
          <input
            type="checkbox"
            id="deliveredCorrectly"
            checked={deliveredCorrectly}
            onChange={() => setDeliveredCorrectly(!deliveredCorrectly)}
            className="w-4 h-4 text-red-900 border-gray-300 rounded focus:ring-black"
          />
          <label
            htmlFor="deliveredCorrectly"
            className="ml-2 text-sm font-medium text-gray-700"
          >
            Was the post delivered correctly?
          </label>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Delivery Address
          </label>
          <input
            type="text"
            value={deliveryAddress}
            readOnly
            className="w-full mt-1 p-2 border border-gray-300 rounded bg-gray-100 text-gray-600 cursor-not-allowed"
          />
        </div>

        <div className="flex items-center">
          <input
            type="checkbox"
            id="postReceived"
            checked={isReceived}
            onChange={() => setIsReceived(!isReceived)}
            className="w-4 h-4 text-red-900 border-gray-300 rounded focus:ring-black"
          />
          <label
            htmlFor="postReceived"
            className="ml-2 text-sm font-medium text-gray-700"
          >
            please confirm if above address is correct?
            <br />
            If not then enter the correct address
          </label>
        </div>

        {!isReceived && (
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Correct Address
            </label>
            <input
              type="text"
              placeholder="Enter the correct address"
              value={correctAddress}
              onChange={(e) => setCorrectAddress(e.target.value)}
              className="w-full mt-1 p-2 border border-gray-300 rounded focus:ring-black focus:border-black"
              required
            />
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Additional Comments
          </label>
          <textarea
            placeholder="Any additional feedback?"
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            className="w-full mt-1 p-2 border border-gray-300 rounded focus:ring-black focus:border-black"
            rows="4"
          />
        </div>
        <button
          type="submit"
          className="w-full py-2 px-4 bg-red-900 text-white font-semibold rounded hover:bg-red-700"
        >
          Submit Feedback
        </button>
      </form>
    </div>
  );
}
