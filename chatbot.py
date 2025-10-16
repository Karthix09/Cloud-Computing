import os
import re
import sqlite3
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
from collections import defaultdict

user_sessions = defaultdict(dict)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

chatbot_bp = Blueprint('chatbot', __name__)

# ============================================
# CHATBOT ROUTES
# ============================================

@chatbot_bp.route('/chatbot')
def chatbot_page():
    """Chatbot interface page"""
    return render_template('chatbot.html')


@chatbot_bp.route('/api/chat', methods=['POST'])
def chat():
    """Handle chatbot messages"""
    data = request.json
    user_message = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')
    
    if not user_message:
        return jsonify({
            'response': "Please type a message!",
            'type': 'error'
        })
    
    # Get user's session data
    session_data = user_sessions[session_id]
    
    # Process the message with context
    response = process_message(user_message, session_data)
    
    # Update session if response contains stop info
    if response.get('stop_code'):
        session_data['last_stop_code'] = response['stop_code']
        session_data['last_stop_name'] = response.get('stop_name')
    
    return jsonify(response)

@chatbot_bp.route('/api/bus-stops/search', methods=['GET'])
def search_bus_stops():
    """Search bus stops by name or road"""
    query = request.args.get('query', '').strip()
    
    if not query:
        return jsonify([])
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Search in description and road
    search_term = f"%{query}%"
    cursor.execute("""
        SELECT code, description, road, lat, lon
        FROM bus_stops
        WHERE LOWER(description) LIKE LOWER(?)
           OR LOWER(road) LIKE LOWER(?)
        LIMIT 10
    """, (search_term, search_term))
    
    results = cursor.fetchall()
    conn.close()
    
    stops = []
    for row in results:
        stops.append({
            'code': row[0],
            'description': row[1],
            'road': row[2],
            'lat': row[3],
            'lon': row[4]
        })
    
    return jsonify(stops)


@chatbot_bp.route('/api/bus-arrivals/<bus_stop_code>')
def get_bus_arrivals_api(bus_stop_code):
    """Get bus arrivals for a specific stop"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get stop info
    cursor.execute("SELECT description, road FROM bus_stops WHERE code = ?", (bus_stop_code,))
    stop_info = cursor.fetchone()
    
    if not stop_info:
        conn.close()
        return jsonify({'error': 'Bus stop not found'}), 404
    
    # Get latest arrivals
    cursor.execute("""
        SELECT MAX(timestamp) FROM bus_arrivals WHERE stop_code = ?
    """, (bus_stop_code,))
    latest_time = cursor.fetchone()[0]
    
    if not latest_time:
        conn.close()
        return jsonify({
            'stop_code': bus_stop_code,
            'stop_name': stop_info[0],
            'road': stop_info[1],
            'arrivals': []
        })
    
    # Get all arrivals at latest timestamp
    cursor.execute("""
        SELECT service, eta_min, bus_type
        FROM bus_arrivals
        WHERE stop_code = ? AND timestamp = ?
        ORDER BY service ASC, eta_min ASC
    """, (bus_stop_code, latest_time))
    
    arrivals_raw = cursor.fetchall()
    conn.close()
    
    # Group by service
    arrivals_dict = {}
    for service, eta, bus_type in arrivals_raw:
        if service not in arrivals_dict:
            arrivals_dict[service] = {
                'service': service,
                'eta': [],
                'type': bus_type
            }
        arrivals_dict[service]['eta'].append(round(eta, 1))
    
    return jsonify({
        'stop_code': bus_stop_code,
        'stop_name': stop_info[0],
        'road': stop_info[1],
        'arrivals': list(arrivals_dict.values())
    })

@chatbot_bp.route('/api/bus-stops/nearby', methods=['POST'])
def get_nearby_bus_stops():
    """Get bus stops near user's location"""
    import math
    
    data = request.json
    user_lat = data.get('lat')
    user_lon = data.get('lon')
    limit = data.get('limit', 5)
    max_distance = data.get('max_distance', 1000)  # Changed from 2000 to 1000 (1km)
    
    if not user_lat or not user_lon:
        return jsonify({'error': 'Location required'}), 400
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get bus stops with valid coordinates (Singapore bounds)
    cursor.execute("""
        SELECT code, description, road, lat, lon 
        FROM bus_stops
        WHERE lat IS NOT NULL 
          AND lon IS NOT NULL
          AND lat BETWEEN 1.1 AND 1.5
          AND lon BETWEEN 103.6 AND 104.1
    """)
    all_stops = cursor.fetchall()
    conn.close()
    
    def haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate distance between two points in meters"""
        R = 6371000  # Earth's radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    # Calculate distances
    stops_with_distance = []
    for stop in all_stops:
        code, description, road, lat, lon = stop
        distance = haversine_distance(user_lat, user_lon, lat, lon)
        
        # Only include stops within 1km (1000 meters)
        if distance <= max_distance:
            stops_with_distance.append({
                'code': code,
                'description': description,
                'road': road,
                'lat': lat,
                'lon': lon,
                'distance': round(distance, 1)
            })
    
    # Sort by distance
    stops_with_distance.sort(key=lambda x: x['distance'])
    nearest_stops = stops_with_distance[:limit]
    
    return jsonify(nearest_stops)

# ============================================
# CHATBOT LOGIC
# ============================================

def process_message(message, session_data=None):
    """Process user message and return appropriate response"""
    if session_data is None:
        session_data = {}
    
    message_lower = message.lower()
    
    # Greeting
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'start']):
        return {
            'response': "ðŸ‘‹ Hello! I'm your Transport Buddy!\n\n"
                       "I can help you with:\n"
                       "â€¢ ðŸšŒ Bus arrival times\n"
                       "â€¢ ðŸ” Finding bus stops\n"
                       "â€¢ ðŸ“ Bus stops near you\n\n",
            'type': 'greeting'
        }
    
    # Location-based query
    if any(phrase in message_lower for phrase in ['near me', 'nearby', 'closest', 'nearest', 'my location']):
        return {
            'response': "ðŸ“ I'll find bus stops near you!\n\n"
                       "Please allow location access when prompted by your browser.",
            'type': 'request_location',
            'action': 'get_nearby_stops'
        }
    
    # Check for specific bus number query (follow-up context)
    bus_number_match = re.search(r'\b(bus\s+)?(\d{1,3}[A-Z]?)\b', message_lower)
    if bus_number_match:
        bus_number = bus_number_match.group(2).upper()
        
        # Check if we have context about the last stop
        if session_data.get('last_stop_code'):
            last_stop = session_data['last_stop_code']
            last_stop_name = session_data.get('last_stop_name', last_stop)
            
            # Check if this bus serves that stop
            return check_specific_bus_at_stop(bus_number, last_stop, last_stop_name)
    
    # Bus arrival query
    if any(word in message_lower for word in ['bus', 'arrival', 'next', 'when', 'timing']):
        return handle_bus_query(message)
    
    # Help
    if 'help' in message_lower:
        return {
            'response': "ðŸ¤– Here's what I can do:\n\n"
                       "ðŸšŒ **Check Bus Arrivals:**\n"
                       "â€¢ 'Bus at [stop name]'\n"
                       "â€¢ 'When is bus 75 at [stop name] coming?'\n\n"
                       "ðŸ“ **Find Nearby Stops:**\n"
                       "â€¢ 'Bus stops near me'\n"
                       "ðŸ’¬ **Follow-up Questions:**\n"
                       "â€¢ After checking a stop, ask 'What about bus 167?'\n\n"
                       "ðŸ’¡ **Tips:**\n"
                       "â€¢ You can search by bus stop name or road\n"
                       "â€¢ I remember your last searched stop for follow-ups",
            'type': 'help'
        }
    
    # Default response
    return {
        'response': "ðŸ¤” I'm not sure how to help with that.\n\n"
                   "Try asking:\n"
                   "â€¢ 'Bus stops near me'\n"
                   "â€¢ 'Bus at [location name]'\n"
                   "â€¢ Type 'help' for more options",
        'type': 'unknown'
    }


def handle_bus_query(message):
    """Handle bus arrival queries"""
    import re
    
    message_lower = message.lower()
    
    # Check if specific bus stop code (5 digits) mentioned
    bus_stop_match = re.search(r'\b(\d{5})\b', message)
    
    if bus_stop_match:
        bus_stop_code = bus_stop_match.group(1)
        return get_bus_arrivals(bus_stop_code)
    
    # Extract location name (everything after "at", "near", "from")
    location_patterns = [
        r'at\s+(.+?)(?:\?|$)',
        r'near\s+(.+?)(?:\?|$)',
        r'from\s+(.+?)(?:\?|$)',
        r'in\s+(.+?)(?:\?|$)',
    ]
    
    location = None
    for pattern in location_patterns:
        match = re.search(pattern, message_lower)
        if match:
            location = match.group(1).strip()
            break
    
    # If no location found, try to extract meaningful words
    if not location:
        # Remove common words
        words = message_lower.split()
        stop_words = ['when', 'is', 'the', 'next', 'bus', 'at', 'coming', 'arriving', 'arrival', 'timing', 'timings']
        location_words = [w for w in words if w not in stop_words and len(w) > 2]
        if location_words:
            location = ' '.join(location_words)
    
    if not location:
        return {
            'response': "ðŸ¤” I couldn't find a location in your message.\n\n"
                       "Try asking like this:\n"
                       "â€¢ 'Bus at Raffles Place'\n"
                       "â€¢ 'Next bus at Orchard Road'\n"
                       "â€¢ 'Bus timing at stop 01012'",
            'type': 'clarification',
            'needs_location': True
        }
    
    # Search for bus stops
    return search_and_present_stops(location)


def search_and_present_stops(location):
    """Search for bus stops and present results"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # First try: exact phrase match
    search_term = f"%{location}%"
    cursor.execute("""
        SELECT code, description, road
        FROM bus_stops
        WHERE LOWER(description) LIKE LOWER(?)
           OR LOWER(road) LIKE LOWER(?)
        LIMIT 20
    """, (search_term, search_term))
    
    results = cursor.fetchall()
    
    # Second try: search by individual words and rank by relevance
    if not results:
        words = [w for w in location.split() if len(w) > 2]
        
        if words:
            # Search for stops containing any of the words
            conditions = []
            params = []
            
            for word in words:
                conditions.append("LOWER(description) LIKE LOWER(?)")
                conditions.append("LOWER(road) LIKE LOWER(?)")
                params.extend([f"%{word}%", f"%{word}%"])
            
            query = f"""
                SELECT code, description, road
                FROM bus_stops
                WHERE {' OR '.join(conditions)}
            """
            cursor.execute(query, params)
            all_results = cursor.fetchall()
            
            # Rank by how many words match
            scored_results = []
            for row in all_results:
                code, desc, road = row
                score = 0
                for word in words:
                    if word.lower() in desc.lower():
                        score += 2  # Description match worth more
                    if word.lower() in road.lower():
                        score += 1
                scored_results.append((score, row))
            
            # Sort by score (highest first) and take top 20
            scored_results.sort(reverse=True, key=lambda x: x[0])
            results = [row for score, row in scored_results[:20]]
    
    conn.close()
    
    if not results:
        return {
            'response': f"âŒ Sorry, I couldn't find any bus stops matching '{location}'.\n\n"
                       "ðŸ’¡ Try:\n"
                       "â€¢ Using the full road name (e.g., 'Orchard Road')\n"
                       "â€¢ Using the bus stop code if you know it\n"
                       "â€¢ Being more specific (e.g., 'Raffles Quay' or 'Raffles Hotel')\n"
                       "â€¢ Searching for just one word (e.g., 'Raffles')",
            'type': 'not_found'
        }
    
    if len(results) == 1:
        # Only one match - show arrivals directly
        bus_stop_code = results[0][0]
        return get_bus_arrivals(bus_stop_code)
    
    # Multiple matches - ask user to choose
    # Limit to 10 for better UX
    results = results[:10]
    
    return {
        'response': f"ðŸ” I found {len(results)} bus stops matching '{location}':\n\n"
                   "Please choose one by clicking below:",
        'type': 'multiple_matches',
        'stops': [
            {
                'code': row[0],
                'description': row[1],
                'road': row[2]
            } for row in results
        ]
    }

def get_bus_arrivals(bus_stop_code):
    """Get bus arrivals for a specific stop"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get stop info
    cursor.execute("SELECT description, road FROM bus_stops WHERE code = ?", (bus_stop_code,))
    stop_info = cursor.fetchone()
    
    if not stop_info:
        conn.close()
        return {
            'response': f"âŒ Bus stop {bus_stop_code} not found in database.",
            'type': 'error'
        }
    
    stop_name = stop_info[0]
    road = stop_info[1]
    
    # Get latest timestamp
    cursor.execute("""
        SELECT MAX(timestamp) FROM bus_arrivals WHERE stop_code = ?
    """, (bus_stop_code,))
    latest_time_result = cursor.fetchone()[0]
    
    if not latest_time_result:
        conn.close()
        return {
            'response': f"ðŸš **{stop_name}** ({bus_stop_code})\n"
                       f"ðŸ“ {road}\n\n"
                       f"âŒ No bus arrival data available at the moment.",
            'type': 'no_data',
            'stop_code': bus_stop_code,
            'stop_name': stop_name
        }
    
    # Get all arrivals within 2 minutes of the latest timestamp
    # This handles cases where different buses have slightly different timestamps
    from datetime import datetime, timedelta
    
    try:
        latest_time = datetime.fromisoformat(latest_time_result)
        time_threshold = (latest_time - timedelta(minutes=2)).isoformat()
    except:
        # Fallback: just use the latest timestamp
        time_threshold = latest_time_result
    
    cursor.execute("""
        SELECT service, eta_min, bus_type, timestamp
        FROM bus_arrivals
        WHERE stop_code = ? 
          AND timestamp >= ?
        ORDER BY service ASC, timestamp DESC, eta_min ASC
    """, (bus_stop_code, time_threshold))
    
    arrivals_raw = cursor.fetchall()
    conn.close()
    
    if not arrivals_raw:
        return {
            'response': f"ðŸš **{stop_name}** ({bus_stop_code})\n"
                       f"ðŸ“ {road}\n\n"
                       f"âŒ No buses currently arriving.",
            'type': 'no_arrivals',
            'stop_code': bus_stop_code,
            'stop_name': stop_name
        }
    
    # Helper function to convert bus type codes
    def format_bus_type(bus_type):
        """Convert bus type code to readable format with emoji"""
        if not bus_type:
            return ""
        
        bus_type_upper = bus_type.upper()
        
        if bus_type_upper == 'SD':
            return "ðŸšŒ Single Decker"
        elif bus_type_upper == 'DD':
            return "ðŸš Double Decker"
        elif bus_type_upper == 'BD':
            return "ðŸš Bendy Bus"
        else:
            return f"ðŸšŒ {bus_type}"
    
    # Group by service number (take most recent record for each service)
    arrivals_dict = {}
    for service, eta, bus_type, timestamp in arrivals_raw:
        if service not in arrivals_dict:
            arrivals_dict[service] = {
                'service': service,
                'eta': [],
                'type': bus_type,
                'timestamp': timestamp
            }
        arrivals_dict[service]['eta'].append(eta)
    
    # Format response
    response_text = f"ðŸš **{stop_name}** ({bus_stop_code})\n"
    response_text += f"ðŸ“ {road}\n\n"
    response_text += "ðŸšŒ **Bus Arrivals:**\n\n"
    
    for service_data in sorted(arrivals_dict.values(), key=lambda x: x['service']):
        service = service_data['service']
        etas = service_data['eta']
        bus_type = service_data['type']
        
        # Format ETAs
        formatted_etas = []
        for eta in etas[:3]:  # Show max 3 arrivals per bus
            if eta < 1:
                formatted_etas.append("**Arr**")
            elif eta == 1:
                formatted_etas.append("1 min")
            else:
                formatted_etas.append(f"{int(eta)} min")
        
        eta_text = " â€¢ ".join(formatted_etas)
        bus_type_text = format_bus_type(bus_type)
        
        # Display bus with type
        response_text += f"**Bus {service}** - {bus_type_text}\n"
        response_text += f"â±ï¸ {eta_text}\n\n"
    
    # Use the latest timestamp for display
    try:
        timestamp_obj = datetime.fromisoformat(latest_time_result)
        formatted_time = timestamp_obj.strftime('%I:%M %p')
    except:
        formatted_time = latest_time_result
    
    response_text += f"ðŸ•’ Last updated: {formatted_time}"
    
    return {
        'response': response_text,
        'type': 'arrivals',
        'stop_code': bus_stop_code,
        'stop_name': stop_name,
        'arrivals': list(arrivals_dict.values())
    }

def check_specific_bus_at_stop(bus_number, stop_code, stop_name):
    """Check if a specific bus serves a particular stop"""
    import re
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get latest timestamp for this stop
    cursor.execute("""
        SELECT MAX(timestamp) FROM bus_arrivals WHERE stop_code = ?
    """, (stop_code,))
    latest_time_result = cursor.fetchone()[0]
    
    if not latest_time_result:
        conn.close()
        return {
            'response': f"âŒ No bus arrival data for {stop_name}.",
            'type': 'error'
        }
    
    # Get arrivals within 2 minutes of latest timestamp
    from datetime import datetime, timedelta
    
    try:
        latest_time = datetime.fromisoformat(latest_time_result)
        time_threshold = (latest_time - timedelta(minutes=2)).isoformat()
    except:
        time_threshold = latest_time_result
    
    # Look for the specific bus
    cursor.execute("""
        SELECT service, eta_min, bus_type, timestamp
        FROM bus_arrivals
        WHERE stop_code = ? 
          AND UPPER(service) = UPPER(?)
          AND timestamp >= ?
        ORDER BY timestamp DESC, eta_min ASC
        LIMIT 3
    """, (stop_code, bus_number, time_threshold))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        return {
            'response': f"âŒ Bus {bus_number} doesn't serve **{stop_name}** ({stop_code}), or no arrival data is currently available.\n\n"
                       f"Try asking about the stop again to see which buses are available.",
            'type': 'bus_not_found',
            'stop_code': stop_code,
            'stop_name': stop_name
        }
    
    # Format the response
    service, eta, bus_type, timestamp = results[0]
    
    def format_bus_type(bus_type):
        if not bus_type:
            return ""
        bus_type_upper = bus_type.upper()
        if bus_type_upper == 'SD':
            return "ðŸšŒ Single Decker"
        elif bus_type_upper == 'DD':
            return "ðŸš Double Decker"
        elif bus_type_upper == 'BD':
            return "ðŸš Bendy Bus"
        else:
            return f"ðŸšŒ {bus_type}"
    
    # Format ETAs
    etas = [row[1] for row in results]
    formatted_etas = []
    for eta_val in etas:
        if eta_val < 1:
            formatted_etas.append("**Arr**")
        elif eta_val == 1:
            formatted_etas.append("1 min")
        else:
            formatted_etas.append(f"{int(eta_val)} min")
    
    eta_text = " â€¢ ".join(formatted_etas)
    bus_type_text = format_bus_type(bus_type)
    
    response_text = f"ðŸš **{stop_name}** ({stop_code})\n\n"
    response_text += f"ðŸšŒ **Bus {service}** - {bus_type_text}\n"
    response_text += f"â±ï¸ {eta_text}\n\n"
    
    try:
        timestamp_obj = datetime.fromisoformat(latest_time_result)
        formatted_time = timestamp_obj.strftime('%I:%M %p')
    except:
        formatted_time = latest_time_result
    
    response_text += f"ðŸ•’ Last updated: {formatted_time}"
    
    return {
        'response': response_text,
        'type': 'specific_bus',
        'stop_code': stop_code,
        'stop_name': stop_name
    }