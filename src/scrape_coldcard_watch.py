import requests
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"

def main():
    url = "https://coldcard-watch.vercel.app/drains.js"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch {url}: {response.status_code}")
        return
        
    text = response.text
    # Find the JSON part
    start = text.find('{')
    end = text.rfind('}')
    
    if start == -1 or end == -1:
        print("Could not find JSON object in drains.js")
        return
        
    json_str = text[start:end+1]
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        # Try to fix unquoted keys (e.g. h:, t:) if necessary, but try simple first
        # Let's save it to a file so we can inspect if it fails
        with open("drains_raw.js", "w") as f:
            f.write(json_str)
        return

    rows = data.get("rows", [])
    blocks = data.get("blocks", [])
    
    victims = []
    total_btc = 0
    
    for row in rows:
        address = row[0]
        amount_sats = row[1]
        amount_btc = amount_sats / 1e8
        block_idx = row[2]
        
        block = blocks[block_idx]
        block_height = block["h"]
        block_time = block["t"]
        
        victims.append({
            "address": address,
            "amount_sats": amount_sats,
            "amount_btc": amount_btc,
            "block_height": block_height,
            "block_time": block_time
        })
        total_btc += amount_btc
        
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "victim_addresses.json"
    
    with open(out_path, "w") as f:
        json.dump(victims, f, indent=2)
        
    print(f"Total addresses: {len(victims)}")
    print(f"Total BTC: {total_btc:.2f}")
    if victims:
        min_block = min(v["block_height"] for v in victims)
        max_block = max(v["block_height"] for v in victims)
        print(f"Block range: {min_block} - {max_block}")

if __name__ == "__main__":
    main()
