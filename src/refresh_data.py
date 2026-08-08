import json
import hashlib
from datetime import datetime
from pathlib import Path
import subprocess

SRC_DIR = Path(__file__).parent
DATA_DIR = SRC_DIR.parent / "docs" / "data"

def hash_address(address):
    # SHA256 of the utf-8 encoded address, truncated to first 16 hex chars
    sha256_hash = hashlib.sha256(address.encode('utf-8')).hexdigest()
    return sha256_hash[:16]

def update_compromised_hashes():
    victim_path = DATA_DIR / "victim_addresses.json"
    if not victim_path.exists():
        print("No victim_addresses.json found.")
        return
        
    with open(victim_path, "r") as f:
        victims = json.load(f)
        
    hashes = []
    for v in victims:
        hashes.append(hash_address(v["address"]))
        
    # Sort for consistency
    hashes.sort()
    
    out_path = DATA_DIR / "compromised_hashes.json"
    with open(out_path, "w") as f:
        json.dump(hashes, f)
        
    print(f"Updated compromised_hashes.json with {len(hashes)} hashes.")

def update_sources():
    sources_path = DATA_DIR / "sources.json"
    if not sources_path.exists():
        return
        
    with open(sources_path, "r") as f:
        data = json.load(f)
        
    today = datetime.now().strftime("%Y-%m-%d")
    for source in data.get("sources", []):
        if "last_checked" in source:
            source["last_checked"] = today
            
    with open(sources_path, "w") as f:
        json.dump(data, f, indent=2)
        
    print("Updated sources.json timestamps.")

def main():
    print("Refreshing data from external sources for validation...")
    
    # 1. Scrape coldcardwatch.com
    print("\n--- Scraping coldcard-watch ---")
    scrape_script = SRC_DIR / "scrape_coldcard_watch.py"
    subprocess.run(["python", str(scrape_script)], check=True)
    
    # 2. Update hashes
    print("\n--- Updating compromised hashes ---")
    update_compromised_hashes()
    
    # 3. Update sources timestamps
    print("\n--- Updating sources.json ---")
    update_sources()
    
    # 4. Regenerate dashboard metrics
    print("\n--- Regenerating Dashboard Metrics ---")
    stage4_script = SRC_DIR / "stage4_generate_dashboard.py"
    subprocess.run(["python", str(stage4_script)], check=True)
    
    print("\nRefresh complete. Ready to push to GitHub.")

if __name__ == "__main__":
    main()
