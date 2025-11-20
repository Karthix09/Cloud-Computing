# charts.py
import os
import pandas as pd
from flask import Blueprint, render_template, jsonify

# Create Blueprint
charts_bp = Blueprint('charts', __name__, template_folder='templates')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "static/datasets")

def load_csv(filename):
    """Loads a CSV file from /datasets."""
    full_path = os.path.join(DATASET_DIR, filename)
    print(f"📄 Loading: {full_path}")

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Dataset not found: {full_path}")

    df = pd.read_csv(full_path)
    return df.fillna(0)


@charts_bp.route("/charts")
def chart_dashboard():
    print("\n============================")
    print("🔍 ENTERED /charts ROUTE")
    print("============================\n")

    # Load datasets from /datasets
    avg_by_hour_df = load_csv("avg_by_hour.csv")
    median_by_service_df = load_csv("median_by_service.csv")
    drift_by_service_df = load_csv("drift_by_service.csv")
    top10_worst_df = load_csv("top10_worst.csv")

    # ===== CHART 1 CLEANING =====
    hourly_df = (
        avg_by_hour_df.groupby("hour")["avg_eta"]
        .mean()
        .reset_index()
        .sort_values("hour")
    )
    hourly = hourly_df.to_dict(orient="records")

    # ===== CHART 2 CLEANING =====
    median_sorted_df = (
        median_by_service_df.sort_values("median_eta", ascending=False)
    )
    median_by_service = median_sorted_df.to_dict(orient="records")

    # ===== CHART 3 CLEANING =====
    drift_sorted_df = (
        drift_by_service_df.sort_values("avg_eta_drift", ascending=False)
    )
    drift_by_service = drift_sorted_df.to_dict(orient="records")

    # ===== CHART 4 =====
    top10_worst = top10_worst_df.to_dict(orient="records")

    # Print debug
    print("Hourly:", hourly[:3])
    print("Median:", median_by_service[:3])
    print("Drift:", drift_by_service[:3])
    print("Top10:", top10_worst[:3])
    print("============================\n")

    return render_template(
        "chart_dashboard.html",
        hourly=hourly,
        median_by_service=median_by_service,
        drift_by_service=drift_by_service,
        top10_worst=top10_worst
    )

# charts.py - ANEW ENDPOINT

@charts_bp.route("/api/bus_analytics/<service_no>")
def get_bus_analytics(service_no):
    """
    Get analytics data for a specific bus service.
    Returns metrics like median ETA, drift, volatility, etc.
    """
    try:
        # Load the analytics datasets
        median_by_service_df = load_csv("median_by_service.csv")
        drift_by_service_df = load_csv("drift_by_service.csv")
        
        # Find data for this specific service
        service_no = str(service_no).strip()
        
        # Get median/ETA data
        median_data = median_by_service_df[
            median_by_service_df['service'].astype(str).str.strip() == service_no
        ]
        
        # Get drift data
        drift_data = drift_by_service_df[
            drift_by_service_df['service'].astype(str).str.strip() == service_no
        ]
        
        # If no data found, return defaults
        if median_data.empty and drift_data.empty:
            return jsonify({
                "service": service_no,
                "found": False,
                "message": "No analytics data available for this service"
            })
        
        # Extract metrics
        analytics = {
            "service": service_no,
            "found": True,
            "median_eta": float(median_data['median_eta'].iloc[0]) if not median_data.empty else 0,
            "avg_eta": float(median_data['avg_eta'].iloc[0]) if not median_data.empty else 0,
            "eta_variability": float(median_data['eta_variability'].iloc[0]) if not median_data.empty else 0,
            "avg_eta_drift": float(drift_data['avg_eta_drift'].iloc[0]) if not drift_data.empty else 0,
            "drift_variability": float(drift_data['drift_variability'].iloc[0]) if not drift_data.empty else 0,
            "avg_volatility": float(drift_data['avg_volatility'].iloc[0]) if not drift_data.empty else 0
        }
        
        # Determine status based on drift
        drift_abs = abs(analytics['avg_eta_drift'])
        if drift_abs >= 30:
            analytics['status'] = 'Critical'
            analytics['status_color'] = '#dc2626'
        elif drift_abs >= 20:
            analytics['status'] = 'High Drift'
            analytics['status_color'] = '#ea580c'
        elif drift_abs >= 10:
            analytics['status'] = 'Medium'
            analytics['status_color'] = '#d97706'
        else:
            analytics['status'] = 'Stable'
            analytics['status_color'] = '#059669'
        
        return jsonify(analytics)
        
    except Exception as e:
        print(f"Error fetching bus analytics: {e}")
        return jsonify({
            "service": service_no,
            "found": False,
            "error": str(e)
        }), 500