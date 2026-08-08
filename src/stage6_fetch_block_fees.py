import json
import time
import requests
from pathlib import Path

SRC_DIR = Path(__file__).parent
DATA_DIR = SRC_DIR.parent / "docs" / "data"
SCORED_FILE = DATA_DIR / "scored_sweeps.json"
FEES_FILE = DATA_DIR / "block_fees.json"

def main():
    if not SCORED_FILE.exists():
        print(f"Error: {SCORED_FILE} not found.")
        return

    with open(SCORED_FILE, "r") as f:
        data = json.load(f)
    
    sweeps = data.get("suspected_sweeps", [])
    if not sweeps:
        print("No sweeps found.")
        return

    # Extract unique block heights
    heights = set()
    for s in sweeps:
        if "height" in s:
            heights.add(s["height"])
            
    heights = sorted(list(heights))
    print(f"Found {len(heights)} unique blocks containing sweeps.")

    # Load existing fees to avoid re-fetching
    existing_fees = {}
    if FEES_FILE.exists():
        with open(FEES_FILE, "r") as f:
            existing_fees = json.load(f)
            
    # Convert string keys to int if necessary
    existing_fees = {int(k): v for k, v in existing_fees.items()}

    new_fees = existing_fees.copy()
    
    session = requests.Session()
    session.headers.update({"User-Agent": "Coldcard-Investigator/1.0"})

    for i, h in enumerate(heights):
        if h in new_fees:
            continue
            
        print(f"Fetching fee for block {h} ({i+1}/{len(heights)})...")
        try:
            # 1. Get block hash
            res = session.get(f"https://mempool.space/api/block-height/{h}", timeout=10)
            res.raise_for_status()
            b_hash = res.text.strip()
            
            # 2. Get block data
            res2 = session.get(f"https://mempool.space/api/v1/block/{b_hash}", timeout=10)
            res2.raise_for_status()
            b_data = res2.json()
            
            avg_fee = b_data.get("extras", {}).get("avgFeeRate", 0)
            
            from datetime import datetime, UTC
            dt = datetime.fromtimestamp(b_data["timestamp"], UTC).strftime('%Y-%m-%d %H:%M:%S')
            
            # Store date and fee
            new_fees[h] = {
                "date": dt,
                "fee": avg_fee
            }
            
            # Save incrementally
            with open(FEES_FILE, "w") as f:
                json.dump(new_fees, f, indent=2)
                
            time.sleep(0.3)
        except Exception as e:
            print(f"Error fetching block {h}: {e}")
            time.sleep(1)
            
    print(f"Finished. Saved {len(new_fees)} block fee records to {FEES_FILE}.")

if __name__ == "__main__":
    main()
