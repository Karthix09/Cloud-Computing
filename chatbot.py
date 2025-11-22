# chatbot.py - UPDATED with Route Planning Feature

from flask import Blueprint, render_template, request, jsonify, session
from functools import wraps
import os
import json
import logging
import requests
import re

# Import database and auth
from database import get_db_connection, IS_PRODUCTION
from auth import login_required

# ---- LEX CONFIG ----
LEX_BOT_ID = os.environ.get("LEX_BOT_ID")
LEX_BOT_ALIAS_ID = os.environ.get("LEX_BOT_ALIAS_ID")
LEX_LOCALE_ID = os.environ.get("LEX_LOCALE_ID", "en_US")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---- LEX CLIENT ----
try:
    import boto3
    lex_client = boto3.client("lexv2-runtime", region_name=AWS_REGION)
except ImportError:
    logger.warning("boto3 not installed, Lex will not work.")
    lex_client = None

# ---- BLUEPRINT ----
chatbot_bp = Blueprint("chatbot", __name__)

# ============================
# HELPER FUNCTIONS
# ============================

def get_user_location_by_label(user_id, label):
    """
    Get user's saved location by label (e.g., 'home', 'work', 'school')
    Returns: dict with {label, lat, lon, address} or None
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Search by label (case-insensitive)
        if IS_PRODUCTION:
            cursor.execute("""
                SELECT label, latitude, longitude, address, postal_code
                FROM locations
                WHERE user_id = %s AND LOWER(label) = LOWER(%s)
                LIMIT 1
            """, (user_id, label))
        else:
            cursor.execute("""
                SELECT label, latitude, longitude, address, postal_code
                FROM locations
                WHERE user_id = ? AND LOWER(label) = LOWER(?)
                LIMIT 1
            """, (user_id, label))
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            return {
                "label": row["label"] if IS_PRODUCTION else row[0],
                "latitude": float(row["latitude"] if IS_PRODUCTION else row[1]),
                "longitude": float(row["longitude"] if IS_PRODUCTION else row[2]),
                "address": row["address"] if IS_PRODUCTION else row[3],
                "postal_code": row["postal_code"] if IS_PRODUCTION else row[4]
            }
        return None
        
    except Exception as e:
        logger.error(f"Error getting user location: {e}")
        return None


def geocode_location(location_name):
    """
    Convert location name to coordinates using OneMap API (Singapore)
    Returns: dict with {lat, lon, address} or None
    """
    try:
        # Use Singapore OneMap API for geocoding
        url = "https://www.onemap.gov.sg/api/common/elastic/search"
        params = {
            "searchVal": location_name,
            "returnGeom": "Y",
            "getAddrDetails": "Y"
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data.get("found", 0) > 0:
            result = data["results"][0]
            return {
                "latitude": float(result["LATITUDE"]),
                "longitude": float(result["LONGITUDE"]),
                "address": result["ADDRESS"],
                "postal_code": result.get("POSTAL", "")
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error geocoding location: {e}")
        return None


def find_nearest_bus_stop(latitude, longitude):
    """
    Find nearest bus stop to given coordinates
    Returns: dict with {code, description, distance} or None
    """
    try:
        from database import get_bus_db_connection
        import math
        
        conn = get_bus_db_connection()
        cursor = conn.cursor()
        
        # Get all bus stops
        if IS_PRODUCTION:
            cursor.execute("SELECT code, description, lat, lon FROM bus_stops")
        else:
            cursor.execute("SELECT code, description, lat, lon FROM bus_stops")
        
        stops = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not stops:
            return None
        
        # Calculate distances using Haversine formula
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371  # Earth radius in km
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c
        
        # Find nearest stop
        nearest = None
        min_distance = float('inf')
        
        for stop in stops:
            if IS_PRODUCTION:
                stop_lat = float(stop["lat"])
                stop_lon = float(stop["lon"])
                stop_code = stop["code"]
                stop_desc = stop["description"]
            else:
                stop_lat = float(stop[2])
                stop_lon = float(stop[3])
                stop_code = stop[0]
                stop_desc = stop[1]
            
            distance = haversine(latitude, longitude, stop_lat, stop_lon)
            
            if distance < min_distance:
                min_distance = distance
                nearest = {
                    "code": stop_code,
                    "description": stop_desc,
                    "distance": round(distance * 1000, 0)  # Convert to meters
                }
        
        return nearest
        
    except Exception as e:
        logger.error(f"Error finding nearest bus stop: {e}")
        return None


def get_bus_route_between_stops(origin_code, destination_code):
    """
    Get bus routes between two stops using your existing routing engine
    Returns: list of routes or None
    """
    try:
        # Import your routing function from app.py
        # You'll need to make this available
        from app import dijkstra_multi_wrapper
        
        routes = dijkstra_multi_wrapper(origin_code, destination_code)
        return routes
        
    except Exception as e:
        logger.error(f"Error getting bus routes: {e}")
        return None


def parse_route_query(message):
    """
    Parse user message to extract origin and destination
    Patterns:
    - "how to get from X to Y"
    - "route from X to Y"
    - "directions from X to Y"
    - "from X to Y"
    Returns: dict with {origin, destination} or None
    """
    patterns = [
        r"(?:how (?:to|do i) get |route |directions? |go )?from\s+(.+?)\s+to\s+(.+)",
        r"(.+?)\s+to\s+(.+)"
    ]
    
    message_lower = message.lower().strip()
    
    for pattern in patterns:
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            return {
                "origin": match.group(1).strip(),
                "destination": match.group(2).strip()
            }
    
    return None


# ============================
# FRONTEND CHATBOT PAGE ROUTE
# ============================
@chatbot_bp.route("/chatbot")
@login_required
def chatbot_page():
    return render_template("chatbot.html")


# ======================================
# ROUTE PLANNING ENDPOINT (NEW)
# ======================================
@chatbot_bp.route("/api/chatbot/route-planning", methods=["POST"])
@login_required
def route_planning():
    """
    Handle route planning requests
    Accepts: { "message": "how to get from home to orchard" }
    Returns: route suggestions with bus services
    """
    try:
        data = request.get_json() or {}
        user_message = data.get("message", "")
        user_id = session.get("user_id")
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        # Parse the query
        parsed = parse_route_query(user_message)
        if not parsed:
            return jsonify({
                "error": "Could not understand route query. Try: 'how to get from home to orchard'"
            }), 400
        
        origin_name = parsed["origin"]
        dest_name = parsed["destination"]
        
        logger.info(f"Route planning: {origin_name} → {dest_name}")
        
        # Step 1: Resolve origin
        origin_coords = None
        
        # Check if it's a saved location
        origin_location = get_user_location_by_label(user_id, origin_name)
        if origin_location:
            origin_coords = origin_location
            origin_name = origin_location.get("label", origin_name)
        else:
            # Geocode the location
            origin_coords = geocode_location(origin_name)
        
        if not origin_coords:
            return jsonify({
                "error": f"Could not find location: {origin_name}"
            }), 404
        
        # Step 2: Resolve destination
        dest_coords = None
        
        # Check if it's a saved location
        dest_location = get_user_location_by_label(user_id, dest_name)
        if dest_location:
            dest_coords = dest_location
            dest_name = dest_location.get("label", dest_name)
        else:
            # Geocode the location
            dest_coords = geocode_location(dest_name)
        
        if not dest_coords:
            return jsonify({
                "error": f"Could not find location: {dest_name}"
            }), 404
        
        # Step 3: Find nearest bus stops
        origin_stop = find_nearest_bus_stop(
            origin_coords["latitude"],
            origin_coords["longitude"]
        )
        
        dest_stop = find_nearest_bus_stop(
            dest_coords["latitude"],
            dest_coords["longitude"]
        )
        
        if not origin_stop or not dest_stop:
            return jsonify({
                "error": "Could not find nearby bus stops"
            }), 404
        
        # Step 4: Get bus routes
        routes = get_bus_route_between_stops(
            origin_stop["code"],
            dest_stop["code"]
        )
        
        if not routes:
            return jsonify({
                "error": f"No bus routes found between {origin_name} and {dest_name}"
            }), 404
        
        # Step 5: Format response
        response = {
            "origin": {
                "name": origin_name,
                "address": origin_coords.get("address", ""),
                "bus_stop": {
                    "code": origin_stop["code"],
                    "name": origin_stop["description"],
                    "distance": origin_stop["distance"]
                }
            },
            "destination": {
                "name": dest_name,
                "address": dest_coords.get("address", ""),
                "bus_stop": {
                    "code": dest_stop["code"],
                    "name": dest_stop["description"],
                    "distance": dest_stop["distance"]
                }
            },
            "routes": routes,
            "message": f"Found {len(routes)} route(s) from {origin_name} to {dest_name}"
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in route planning: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to plan route"}), 500


# ======================================
# SEND TEXT MESSAGE TO AMAZON LEX
# ======================================
@chatbot_bp.route("/api/chatbot/send-message", methods=["POST"])
@login_required
def send_message_to_lex():
    try:
        data = request.get_json() or {}
        user_message = data.get("message", "")
        user_id = session.get("user_id")
        session_id = data.get("sessionId", str(user_id))
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        # Check if this is a route planning query
        if parse_route_query(user_message):
            # Handle route planning directly
            return route_planning()
        
        # Otherwise, send to Lex
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500
        
        response = lex_client.recognize_text(
            botId=LEX_BOT_ID,
            botAliasId=LEX_BOT_ALIAS_ID,
            localeId=LEX_LOCALE_ID,
            sessionId=session_id,
            text=user_message
        )
        
        logger.info(f"Lex response: {response}")
        
        # Extract bot messages
        msgs = []
        for m in response.get("messages", []):
            msgs.append({
                "type": "text",
                "content": m.get("content", "")
            })
        
        # Extract structured data
        session_state = response.get("sessionState", {})
        session_attrs = session_state.get("sessionAttributes", {})
        structured_data_raw = session_attrs.get("responseData")
        
        result = {
            "messages": msgs,
            "intentName": session_state.get("intent", {}).get("name"),
            "sessionId": session_id
        }
        
        if structured_data_raw:
            result["data"] = json.loads(structured_data_raw)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error sending to Lex: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to process message"}), 500


# ======================================
# GET USER'S SAVED LOCATIONS
# ======================================
@chatbot_bp.route("/api/chatbot/user-locations", methods=["GET"])
@login_required
def get_user_locations():
    """Get all saved locations for the current user"""
    try:
        user_id = session.get("user_id")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if IS_PRODUCTION:
            cursor.execute("""
                SELECT label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = %s
                ORDER BY is_favourite DESC, label ASC
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT label, latitude, longitude, address, postal_code, is_favourite
                FROM locations
                WHERE user_id = ?
                ORDER BY is_favourite DESC, label ASC
            """, (user_id,))
        
        locations = []
        for row in cursor.fetchall():
            if IS_PRODUCTION:
                locations.append({
                    "label": row["label"],
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "address": row["address"],
                    "postal_code": row["postal_code"],
                    "is_favourite": row["is_favourite"]
                })
            else:
                locations.append({
                    "label": row[0],
                    "latitude": float(row[1]),
                    "longitude": float(row[2]),
                    "address": row[3],
                    "postal_code": row[4],
                    "is_favourite": bool(row[5])
                })
        
        cursor.close()
        conn.close()
        
        return jsonify({"locations": locations})
        
    except Exception as e:
        logger.error(f"Error getting user locations: {e}")
        return jsonify({"error": "Failed to get locations"}), 500


# ======================================
# NEARBY STOPS (GPS) USING LEX INTENT
# ======================================
@chatbot_bp.route("/api/chatbot/nearby-stops", methods=["POST"])
@login_required
def chatbot_nearby_stops():
    try:
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500
        
        data = request.get_json() or {}
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        session_id = data.get("sessionId", str(session.get("user_id")))
        
        if latitude is None or longitude is None:
            return jsonify({"error": "Latitude & longitude required"}), 400
        
        response = lex_client.recognize_text(
            botId=LEX_BOT_ID,
            botAliasId=LEX_BOT_ALIAS_ID,
            localeId=LEX_LOCALE_ID,
            sessionId=session_id,
            text=f"Find stops near {latitude},{longitude}",
            sessionState={
                "intent": {
                    "name": "FindNearbyStops",
                    "slots": {
                        "Latitude": {
                            "shape": "Scalar",
                            "value": {
                                "originalValue": str(latitude),
                                "interpretedValue": str(latitude),
                                "resolvedValues": [str(latitude)]
                            }
                        },
                        "Longitude": {
                            "shape": "Scalar",
                            "value": {
                                "originalValue": str(longitude),
                                "interpretedValue": str(longitude),
                                "resolvedValues": [str(longitude)]
                            }
                        }
                    }
                }
            }
        )
        
        session_attrs = response.get("sessionState", {}).get("sessionAttributes", {})
        data_raw = session_attrs.get("responseData")
        
        if data_raw:
            return jsonify(json.loads(data_raw))
        
        return jsonify({"error": "No data returned"}), 404
        
    except Exception as e:
        logger.error(f"Error getting nearby stops: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get nearby stops"}), 500


# ======================================
# BUS ARRIVALS VIA LEX INTENT
# ======================================
@chatbot_bp.route("/api/chatbot/arrivals/<bus_stop_code>", methods=["GET"])
@login_required
def chatbot_bus_arrivals(bus_stop_code):
    try:
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500
        
        service_no = request.args.get("serviceNo")
        session_id = request.args.get("sessionId", str(session.get("user_id")))
        
        # Build slots
        slots = {
            "BusStopCode": {
                "shape": "Scalar",
                "value": {
                    "originalValue": bus_stop_code,
                    "interpretedValue": bus_stop_code,
                    "resolvedValues": [bus_stop_code]
                }
            }
        }
        
        if service_no:
            slots["ServiceNumber"] = {
                "shape": "Scalar",
                "value": {
                    "originalValue": service_no,
                    "interpretedValue": service_no,
                    "resolvedValues": [service_no]
                }
            }
        
        response = lex_client.recognize_text(
            botId=LEX_BOT_ID,
            botAliasId=LEX_BOT_ALIAS_ID,
            localeId=LEX_LOCALE_ID,
            sessionId=session_id,
            text=f"Get arrivals for {bus_stop_code}",
            sessionState={
                "intent": {
                    "name": "GetBusArrivals",
                    "slots": slots
                }
            }
        )
        
        session_attrs = response.get("sessionState", {}).get("sessionAttributes", {})
        data_raw = session_attrs.get("responseData")
        
        if data_raw:
            return jsonify(json.loads(data_raw))
        
        return jsonify({"error": "No data returned"}), 404
        
    except Exception as e:
        logger.error(f"Error getting bus arrivals: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get bus arrivals"}), 500