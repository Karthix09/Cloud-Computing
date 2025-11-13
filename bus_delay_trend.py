# bus_delay_trend.py
import sqlite3
import pandas as pd
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database/bus_data.db")

def compute_delay_trends(stop_code=None, service=None, window_minutes=30):
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT stop_code, service, eta_min, timestamp FROM bus_arrivals"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("⚠️ No bus arrival data available.")
        return pd.DataFrame(columns=["stop_code","service","window","avg_delay","samples","status"])

    # ✅ Convert timestamp and clean
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    # ✅ Optional filters
    if stop_code:
        df = df[df["stop_code"] == stop_code]
    if service:
        df = df[df["service"] == service]

    if df.empty:
        print(f"⚠️ No data for stop {stop_code} service {service}")
        return pd.DataFrame(columns=["stop_code","service","window","avg_delay","samples","status"])

    # ✅ Ignore next-cycle ETAs (e.g. next bus 30+ min away)
    df = df[df["eta_min"] < 25]

    # Sort for delay calculation
    df = df.sort_values(by=["stop_code", "service", "timestamp"])

    # ✅ Compute previous readings for comparison
    df["prev_eta"] = df.groupby(["stop_code", "service"])["eta_min"].shift(1)
    df["prev_time"] = df.groupby(["stop_code", "service"])["timestamp"].shift(1)

    def calc_delay(row):
        if pd.isna(row["prev_eta"]) or pd.isna(row["prev_time"]):
            return 0
        elapsed = (row["timestamp"] - row["prev_time"]).total_seconds() / 60
        expected_eta = max(row["prev_eta"] - elapsed, 0)
        delay = row["eta_min"] - expected_eta
        return delay  # can be negative if bus arrived early

    df["delay_min"] = df.apply(calc_delay, axis=1)

    # ✅ Only keep realistic values (-5 ≤ delay ≤ 15)
    df = df[df["delay_min"].between(-5, 15)]

    # Aggregate over rolling time window
    df["window"] = df["timestamp"].dt.floor(f"{window_minutes}min")
    trend = (
        df.groupby(["stop_code", "service", "window"])
          .agg(avg_delay=("delay_min", "mean"), samples=("delay_min", "count"))
          .reset_index()
    )

    # ✅ Classify delay severity
    def classify_status(avg_delay):
        if avg_delay < 1:
            return "On time"
        elif avg_delay < 3:
            return "Minor delay"
        else:
            return "Severe delay"

    trend["status"] = trend["avg_delay"].apply(classify_status)

    # Add identifiers
    trend["stop_code"] = stop_code
    trend["service"] = service

    print("\n📈 Bus Delay Trend Preview:")
    print(trend.tail(10))

    return trend[["stop_code", "service", "window", "avg_delay", "samples", "status"]]


# Run standalone (for testing)
if __name__ == "__main__":
    trend_df = compute_delay_trends(stop_code="97009", service="36")
    if not trend_df.empty:
        trend_df.to_csv("delay_trend_sample.csv", index=False)
        print("✅ Delay trend exported to delay_trend_sample.csv")
    else:
        print("⚠️ No trend data generated.")
