import json
import os
import sys

# Ensure correct path lookup
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.db import SessionLocal, init_db
from dtos.request import IngestEventRequest
from services.event_service import process_event

def seed_database():
    print("Initializing database schema...")
    init_db()

    events_file = "sample_events.json"
    if not os.path.exists(events_file):
        print(f"Error: {events_file} not found in workspace directory.")
        return

    print(f"Reading {events_file}...")
    with open(events_file, "r", encoding="utf-8") as f:
        events = json.load(f)

    print(f"Loaded {len(events)} events. Sorting chronologically by event timestamp...")
    # Sorting chronologically guarantees out-of-order logs in sample data are processed in realistic order
    events.sort(key=lambda e: e.get("timestamp", ""))

    db = SessionLocal()
    print("Ingesting events into database...")
    duplicates_count = 0
    success_count = 0

    try:
        for idx, event_data in enumerate(events):
            req = IngestEventRequest(
                event_id=event_data["event_id"],
                event_type=event_data["event_type"],
                transaction_id=event_data["transaction_id"],
                merchant_id=event_data["merchant_id"],
                merchant_name=event_data["merchant_name"],
                amount=event_data["amount"],
                currency=event_data["currency"],
                timestamp=event_data["timestamp"]
            )
            res = process_event(db, req)
            if res.is_duplicate:
                duplicates_count += 1
            else:
                success_count += 1

            if (idx + 1) % 1000 == 0 or idx + 1 == len(events):
                print(f"Progress: Processed {idx + 1}/{len(events)} (Created: {success_count}, Duplicates Skipped: {duplicates_count})")
        
        print("\nDatabase seeded successfully!")
        print(f"Total events analyzed: {len(events)}")
        print(f"Transactions / Events created: {success_count}")
        print(f"Duplicates ignored gracefully: {duplicates_count}")
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
