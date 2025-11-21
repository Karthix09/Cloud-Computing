# chatbot.py

from flask import Blueprint, render_template, request, jsonify, session
from functools import wraps
import os
import json
import logging
import requests

# Use your existing login_required from auth.py
# try:
#     from auth import login_required
# except ImportError:
#     # Fallback (won't be used since your project already has one)
#     def login_required(f):
#         @wraps(f)
#         def wrapper(*args, **kwargs):
#             if "user_id" not in session:
#                 return jsonify({"error": "Not logged in"}), 401
#             return f(*args, **kwargs)
#         return wrapper

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
# FRONTEND CHATBOT PAGE ROUTE
# ============================
@chatbot_bp.route("/chatbot")
# @login_required
def chatbot_page():
    return render_template("chatbot.html")


# ======================================
# SEND TEXT MESSAGE TO AMAZON LEX
# ======================================
@chatbot_bp.route("/api/chatbot/send-message", methods=["POST"])
#@login_required
def send_message_to_lex():
    try:
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500

        data = request.get_json() or {}
        user_message = data.get("message", "")
        session_id = data.get("sessionId", session.get("user_id", "session-default"))

        if not user_message:
            return jsonify({"error": "Message is required"}), 400

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

        # Extract structured data from sessionAttributes
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
# NEARBY STOPS (GPS) USING LEX INTENT
# ======================================
@chatbot_bp.route("/api/chatbot/nearby-stops", methods=["POST"])
#@login_required
def chatbot_nearby_stops():
    try:
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500

        data = request.get_json() or {}
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        session_id = data.get("sessionId", session.get("user_id", "session-default"))

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
#@login_required
def chatbot_bus_arrivals(bus_stop_code):
    try:
        if not lex_client:
            return jsonify({"error": "Lex client not configured"}), 500

        service_no = request.args.get("serviceNo")
        session_id = request.args.get("sessionId", session.get("user_id", "session-default"))

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