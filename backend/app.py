from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from bson import ObjectId
import os
import bcrypt
import shortuuid
from datetime import datetime, timedelta
import jwt
import requests
import hashlib
from collections import defaultdict
from werkzeug.middleware.proxy_fix import ProxyFix
import qrcode
from io import BytesIO
import base64
from PIL import Image

# Initialize Flask app
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)
CORS(app, origins=["http://localhost:5173", "chrome-extension://*"])

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
JWT_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

# Connect to MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client.urls_shortener_db
    users_collection = db.users
    urls_collection = db.urls
    clicks_collection = db.clicks
    users_collection.create_index("username", unique=True)
    urls_collection.create_index("short_code", unique=True)
    print("Successfully connected to MongoDB and ensured indexes.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    exit(1)

# --- Helper Functions ---

def generate_short_code():
    """Generates a unique 6-character short code using shortuuid."""
    return shortuuid.ShortUUID().random(length=6)

def generate_token(user_id):
    """Generates a JWT token for the given user ID, expiring in 24 hours."""
    payload = {
        "user_id": str(user_id),
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

def verify_token(token):
    """Verifies a JWT token and returns the user ID if valid, otherwise None."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.ExpiredSignatureError:
        print("Token expired.")
        return None
    except jwt.InvalidTokenError:
        print("Invalid token.")
        return None

def get_user_id_from_token():
    """Extracts and verifies the JWT token from the Authorization header."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return verify_token(token)

def get_geolocation(ip_address):
    """Fetches country and city from ip-api.com for a given IP address."""
    private_ip_prefixes = ('10.', '172.16.', '172.17.', '172.18.', '172.19.',
                           '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                           '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                           '172.30.', '172.31.', '192.168.', '127.0.0.1')
    if any(ip_address.startswith(prefix) for prefix in private_ip_prefixes) or ip_address == 'localhost':
        print(f"Geolocation: Skipping lookup for local/private IP: {ip_address}")
        return {"city": "Local/Private", "country": "Local/Private"}
    print(f"Geolocation: Attempting to look up IP: {ip_address}")
    try:
        response = requests.get(f"http://ip-api.com/json/{ip_address}?fields=country,city,status,message")
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            print(f"Geolocation: Successfully retrieved data for {ip_address}: {data.get('city')}, {data.get('country')}")
            return {
                "city": data.get("city", "Unknown"),
                "country": data.get("country", "Unknown")
            }
        else:
            print(f"Geolocation: API failed for IP {ip_address}: Status={data.get('status')}, Message={data.get('message', 'No message')}")
            return {"city": "Unknown", "country": "Unknown"}
    except requests.exceptions.RequestException as e:
        print(f"Geolocation: Request error for IP {ip_address}: {e}")
        return {"city": "Unknown", "country": "Unknown"}
    except Exception as e:
        print(f"Geolocation: Processing error for IP {ip_address}: {e}")
        return {"city": "Unknown", "country": "Unknown"}

def generate_client_uid(ip_address, user_agent):
    """Generates a SHA256 hash from IP and User-Agent for client fingerprinting."""
    user_agent_str = user_agent if user_agent else "Unknown"
    data_string = f"{ip_address}-{user_agent_str}"
    return hashlib.sha256(data_string.encode("utf-8")).hexdigest()

def generate_qr_code(url):
    """Generates a QR code for the given URL and returns it as a base64 string."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return None

# --- API Endpoints ---

@app.route("/test", methods=["GET"])
def test():
    """Simple test endpoint to check if the backend is running."""
    return jsonify({"message": "URL Shortener Backend is running!"}), 200

@app.route("/signup", methods=["POST"])
def signup():
    """Handles new user registration."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if len(username) < 3 or len(password) < 6:
            return jsonify({"error": "Username must be at least 3 characters, password at least 6 characters"}), 400
        if users_collection.find_one({"username": username}):
            return jsonify({"error": "Username already exists"}), 409
        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        user_id = users_collection.insert_one({
            "username": username,
            "password": hashed_password
        }).inserted_id
        token = generate_token(user_id)
        return jsonify({
            "message": "Signup successful",
            "user_id": str(user_id),
            "token": token
        }), 201
    except DuplicateKeyError:
        return jsonify({"error": "Username already exists"}), 409
    except Exception as e:
        return jsonify({"error": f"Signup failed: {str(e)}"}), 500

@app.route("/login", methods=["POST"])
def login():
    """Handles user login and issues a JWT token."""
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        user = users_collection.find_one({"username": username})
        if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            return jsonify({"error": "Invalid username or password"}), 401
        token = generate_token(user["_id"])
        return jsonify({
            "message": "Login successful",
            "user_id": str(user["_id"]),
            "token": token
        }), 200
    except Exception as e:
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@app.route("/shorten-anonymous", methods=["POST"])
def shorten_anonymous():
    """Allows anonymous users to shorten URLs with a shorter expiry and QR code."""
    try:
        data = request.get_json()
        long_url = data.get("long_url")
        if not long_url:
            return jsonify({"error": "Long URL is required"}), 400
        if not long_url.startswith(("http://", "https://")):
            long_url = "https://" + long_url
        short_code = generate_short_code()
        while urls_collection.find_one({"short_code": short_code}):
            short_code = generate_short_code()
        urls_collection.insert_one({
            "user_id": None,
            "long_url": long_url,
            "short_code": short_code,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24),
            "click_count": 0
        })
        short_url = f"http://localhost:5000/{short_code}"
        qr_code = generate_qr_code(short_url)
        if not qr_code:
            return jsonify({"error": "Failed to generate QR code"}), 500
        return jsonify({
            "message": "URL shortened successfully",
            "short_url": short_url,
            "short_code": short_code,
            "qr_code": qr_code
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to shorten URL: {str(e)}"}), 500

@app.route("/shorten", methods=["POST"])
def shorten_url():
    """Allows logged-in users to shorten URLs with a longer expiry and QR code."""
    try:
        user_id = get_user_id_from_token()
        if not user_id:
            return jsonify({"error": "Authorization token required"}), 401
        data = request.get_json()
        long_url = data.get("long_url")
        if not long_url:
            return jsonify({"error": "Long URL is required"}), 400
        if not long_url.startswith(("http://", "https://")):
            long_url = "https://" + long_url
        if not users_collection.find_one({"_id": ObjectId(user_id)}):
            return jsonify({"error": "Invalid user"}), 401
        short_code = generate_short_code()
        while urls_collection.find_one({"short_code": short_code}):
            short_code = generate_short_code()
        urls_collection.insert_one({
            "user_id": ObjectId(user_id),
            "long_url": long_url,
            "short_code": short_code,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(weeks=2),
            "click_count": 0
        })
        short_url = f"http://localhost:5000/{short_code}"
        qr_code = generate_qr_code(short_url)
        if not qr_code:
            return jsonify({"error": "Failed to generate QR code"}), 500
        return jsonify({
            "message": "URL shortened successfully",
            "short_url": short_url,
            "short_code": short_code,
            "qr_code": qr_code
        }), 201
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to shorten URL: {str(e)}"}), 500

@app.route("/urls", methods=["GET"])
def get_history():
    """Retrieves the history of URLs shortened by the logged-in user."""
    try:
        user_id = get_user_id_from_token()
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401
        urls = urls_collection.find(
            {"user_id": ObjectId(user_id), "expires_at": {"$gt": datetime.utcnow()}}
        ).sort("created_at", -1)
        url_list = []
        for url in urls:
            url_list.append({
                "long_url": url["long_url"],
                "short_url": f"http://localhost:5000/{url['short_code']}",
                "short_code": url["short_code"],
                "created_at": url["created_at"].isoformat(),
                "clicks": url.get("click_count", 0)
            })
        return jsonify({
            "message": "History retrieved successfully",
            "urls": url_list
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400
    except Exception as e:
        print(f"Failed to retrieve history: {str(e)}")
        return jsonify({"error": f"Failed to retrieve history: {str(e)}"}), 500

@app.route("/stats", methods=["GET"])
def get_stats():
    """Retrieves statistics for the logged-in user."""
    try:
        user_id_str = get_user_id_from_token()
        if not user_id_str:
            return jsonify({"error": "Invalid or expired token"}), 401
        user_id_obj = ObjectId(user_id_str)
        if not users_collection.find_one({"_id": user_id_obj}):
            return jsonify({"error": "User not found"}), 404
        total_urls_shortened = urls_collection.count_documents(
            {"user_id": user_id_obj, "expires_at": {"$gt": datetime.utcnow()}}
        )
        all_user_clicks = clicks_collection.find({"user_id": user_id_obj})
        all_unique_client_uids = set()
        client_uid_counts = defaultdict(int)
        city_country_counts = defaultdict(int)
        has_public_ip_geolocation = False
        for click in all_user_clicks:
            if "client_uid" in click:
                all_unique_client_uids.add(click["client_uid"])
                client_uid_counts[click["client_uid"]] += 1
            if "geo_location" in click and click["geo_location"]:
                city = click["geo_location"].get("city")
                country = click["geo_location"].get("country")
                if city and city not in ["Unknown", "Local/Private"] and \
                   country and country not in ["Unknown", "Local/Private"]:
                    city_country_counts[(city, country)] += 1
                    has_public_ip_geolocation = True
                elif country and country not in ["Unknown", "Local/Private"] and not city:
                    city_country_counts[(None, country)] += 1
                    has_public_ip_geolocation = True
        unique_clicks = len(all_unique_client_uids)
        returning_visitors_count = sum(1 for count in client_uid_counts.values() if count > 1)
        most_frequent_location = "N/A"
        if has_public_ip_geolocation and city_country_counts:
            top_location_tuple = max(city_country_counts, key=city_country_counts.get)
            city_name, country_name = top_location_tuple
            if city_name and city_name != "Unknown":
                most_frequent_location = f"{city_name}, {country_name}"
            elif country_name and country_name != "Unknown":
                most_frequent_location = country_name
            else:
                most_frequent_location = "Unknown Location"
        elif all_user_clicks.count() == 0:
            most_frequent_location = "No clicks recorded yet."
        else:
            most_frequent_location = "Geo data for public IPs not available."
        return jsonify({
            "message": "Stats retrieved successfully",
            "total_urls_shortened": total_urls_shortened,
            "unique_clicks": unique_clicks,
            "returning_visitors": returning_visitors_count,
            "geo_location": most_frequent_location,
            "device_type": "Client-side detected",
            "browser": "Client-side detected",
            "os": "Client-side detected",
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid user ID format"}), 400
    except Exception as e:
        print(f"Error retrieving stats: {e}")
        return jsonify({"error": f"Failed to retrieve stats: {str(e)}"}), 500

@app.route("/<short_code>", methods=["GET"])
def redirect_url(short_code):
    """Redirects to the long URL and tracks the click."""
    try:
        url_doc = urls_collection.find_one({
            "short_code": short_code,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        if not url_doc:
            return jsonify({"error": "Short URL not found or expired"}), 404
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        print(f"Redirect: Client IP: {ip_address}, User-Agent: {user_agent}")
        client_uid = generate_client_uid(ip_address, user_agent)
        geo_data = get_geolocation(ip_address)
        clicks_collection.insert_one({
            "url_id": url_doc["_id"],
            "user_id": url_doc["user_id"],
            "client_uid": client_uid,
            "geo_location": geo_data,
            "timestamp": datetime.utcnow(),
            "ip_address": ip_address,
            "user_agent": user_agent
        })
        urls_collection.update_one(
            {"_id": url_doc["_id"]},
            {"$inc": {"click_count": 1}}
        )
        return redirect(url_doc["long_url"], code=302)
    except Exception as e:
        print(f"Error in redirect_url: {e}")
        return jsonify({"error": f"Failed to resolve URL: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)