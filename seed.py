import argparse
import json
import os
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

def post_event(base_url, event_data):
    """Sends a single event via HTTP POST to the events endpoint."""
    url = f"{base_url.rstrip('/')}/events"
    headers = {"Content-Type": "application/json"}
    payload = json.dumps(event_data).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            body = json.loads(response.read().decode("utf-8"))
            return True, status_code, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = e.reason
        return False, e.code, body
    except Exception as e:
        return False, 500, str(e)

def seed_database():
    parser = argparse.ArgumentParser(description="Seed database via FastAPI HTTP POST events.")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running FastAPI server (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=100,
        help="Number of concurrent workers for sending requests (default: 100)"
    )
    args = parser.parse_args()

    events_file = "sample_events.json"
    if not os.path.exists(events_file):
        print(f"Error: {events_file} not found in current directory.")
        return

    print(f"Reading {events_file}...")
    with open(events_file, "r", encoding="utf-8") as f:
        events = json.load(f)

    print(f"Loaded {len(events)} events. Sorting chronologically by event timestamp...")
    events.sort(key=lambda e: e.get("timestamp", ""))

    print(f"Target URL: {args.url.rstrip('/')}/events")
    print(f"Starting ingestion with {args.workers} concurrent workers...")
    
    success_count = 0
    duplicate_count = 0
    failed_count = 0
    total_events = len(events)
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        futures = {executor.submit(post_event, args.url, event): event for event in events}
        
        for idx, future in enumerate(as_completed(futures)):
            success, code, body = future.result()
            if success:
                # In the API, 201 = newly created, 200 = duplicate ignored
                # Check response structure
                if isinstance(body, dict) and body.get("is_duplicate"):
                    duplicate_count += 1
                elif code == 200:
                    duplicate_count += 1
                else:
                    success_count += 1
            else:
                failed_count += 1
                # Print sample failures for debugging
                if failed_count <= 5:
                    print(f"Sample failure on request {idx+1}: HTTP {code} - {body}")
            
            # Progress printing every 1000 events
            processed = idx + 1
            if processed % 1000 == 0 or processed == total_events:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"Progress: {processed}/{total_events} requests processed "
                      f"(Created: {success_count}, Duplicates: {duplicate_count}, Failed: {failed_count}, Rate: {rate:.1f} req/s)")

    duration = time.time() - start_time
    print("\nIngestion Completed!")
    print(f"Total time elapsed: {duration:.2f} seconds")
    print(f"Total processed: {total_events}")
    print(f"Created events: {success_count}")
    print(f"Duplicates ignored: {duplicate_count}")
    print(f"Failed requests: {failed_count}")

if __name__ == "__main__":
    seed_database()
