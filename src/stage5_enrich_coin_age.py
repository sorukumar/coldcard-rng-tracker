import json
import time
import requests
import os
from pathlib import Path

# Set up paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / 'docs' / 'data' / 'scored_sweeps.json'

def fetch_tx(txid):
    url = f"https://mempool.space/api/tx/{txid}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            print("Rate limited, sleeping 5s...")
            time.sleep(5)
            return fetch_tx(txid)
    except Exception as e:
        print(f"Error fetching {txid}: {e}")
    return None

def main():
    if not DATA_PATH.exists():
        print(f"File not found: {DATA_PATH}")
        return
        
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)
        
    sweeps = data.get('suspected_sweeps', [])
    print(f"Found {len(sweeps)} sweeps.")
    
    updated = 0
    
    # Sort sweeps by value descending to prioritize the biggest ones
    sweeps_sorted = sorted(sweeps, key=lambda x: x.get('value_btc', 0), reverse=True)
    
    for idx, sweep in enumerate(sweeps_sorted):
        # We only need enough data to generate a realistic histogram for the UI.
        # Let's cap at 500 sweeps for time efficiency, prioritizing largest values.
        if updated >= 500:
            break
            
        if 'block_height_delta' in sweep:
            updated += 1
            continue
            
        txid = sweep['txid']
        sweep_height = sweep['height']
        
        # 1. Fetch the sweep tx to get its input
        tx_data = fetch_tx(txid)
        if not tx_data:
            continue
            
        vin = tx_data.get('vin', [])
        if not vin:
            continue
            
        # Get the first input
        prev_txid = vin[0].get('txid')
        if not prev_txid:
            continue
            
        # 2. Fetch the previous tx to get its block height
        prev_tx_data = fetch_tx(prev_txid)
        if not prev_tx_data:
            continue
            
        status = prev_tx_data.get('status', {})
        if not status.get('confirmed'):
            continue
            
        prev_height = status.get('block_height')
        if not prev_height:
            continue
            
        delta = sweep_height - prev_height
        if delta < 0:
            delta = 0
            
        sweep['block_height_delta'] = delta
        sweep['coin_age_days'] = round(delta * 10 / (60 * 24), 2)
        updated += 1
        
        if updated % 10 == 0:
            print(f"Updated {updated} sweeps. Last: delta={delta} blocks ({sweep['coin_age_days']} days)")
            
            # Save incrementally
            with open(DATA_PATH, 'w') as f:
                json.dump(data, f, indent=4)
                
        time.sleep(0.3)

    # Final save
    with open(DATA_PATH, 'w') as f:
        json.dump(data, f, indent=4)
        
    print(f"Finished. Updated {updated} sweeps (top 500 by value).")

if __name__ == '__main__':
    main()
