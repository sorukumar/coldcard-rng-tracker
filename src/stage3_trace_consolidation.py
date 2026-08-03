import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ELECTRS_URL = os.getenv("ELECTRS_URL", "http://100.84.222.115:3006/api")

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
SCORED_SWEEPS_FILE = DATA_DIR / "scored_sweeps.json"
TRACED_CLUSTERS_FILE = DATA_DIR / "traced_clusters.json"
CACHE_FILE = DATA_DIR / "electrs_cache.json"

# Simple file-based cache to avoid spamming the Electrs node on repeated runs
if CACHE_FILE.exists():
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
else:
    cache = {}

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def fetch_address_txs(address):
    if address in cache:
        return cache[address]
        
    url = f"{ELECTRS_URL}/address/{address}/txs"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        cache[address] = data
        return data
    except Exception as e:
        print(f"Error fetching txs for {address}: {e}")
        return []

def trace_address(address, current_depth, max_depth, visited):
    if current_depth > max_depth or address in visited:
        return None
        
    visited.add(address)
    txs = fetch_address_txs(address)
    
    # Simple rate limiting
    if address not in cache:
        time.sleep(0.5) 
        
    trace_tree = {
        "address": address,
        "txs_count": len(txs),
        "next_hops": []
    }
    
    if current_depth < max_depth:
        # Find where funds went (outputs of transactions spending from this address)
        # Note: This is a simplified trace. In a real trace, you'd find UTXOs sent to this address,
        # then find transactions that spend those specific UTXOs, and look at their outputs.
        # For this script, we just grab all destination addresses from all txs related to this address.
        destinations = set()
        for tx in txs:
            for vout in tx.get("vout", []):
                scriptpubkey_address = vout.get("scriptpubkey_address")
                if scriptpubkey_address and scriptpubkey_address != address:
                    destinations.add(scriptpubkey_address)
                    
        for dest in list(destinations)[:3]: # Limit branching factor for demo purposes
            child_trace = trace_address(dest, current_depth + 1, max_depth, visited)
            if child_trace:
                trace_tree["next_hops"].append(child_trace)
                
    return trace_tree

def main():
    print("Stage 3: Tracing consolidation via Electrs...")
    if not SCORED_SWEEPS_FILE.exists():
        print(f"Error: {SCORED_SWEEPS_FILE} not found. Run stage 2 first.")
        return
        
    with open(SCORED_SWEEPS_FILE, "r") as f:
        state = json.load(f)
        
    attacker_clusters = state.get("attacker_clusters", {})
    traced_clusters = {}
    
    # Only trace high-confidence clusters (e.g. Tier 1 and Tier 2, plus highly confident Tier 3)
    target_addresses = []
    for address, info in attacker_clusters.items():
        tier = info.get("tier")
        avg_conf = sum(info["confidence_scores"]) / len(info["confidence_scores"]) if info["confidence_scores"] else 0
        if tier in ["tier_1_verified", "tier_2_crowdsourced"] or avg_conf >= 80:
            target_addresses.append(address)
            
    print(f"Tracing {len(target_addresses)} high-score clusters up to depth 1 (to protect node)...")
    
    count = 0
    for address in target_addresses:
        visited = set()
        trace = trace_address(address, current_depth=0, max_depth=1, visited=visited)
        traced_clusters[address] = {
            "cluster_info": attacker_clusters[address],
            "trace_tree": trace
        }
        
        count += 1
        if count % 10 == 0:
            print(f"Traced {count}/{len(target_addresses)} clusters...")
            save_cache()
            
    save_cache()
    
    # We save a combined state file so Stage 4 can just read it seamlessly
    output_state = {
        "suspected_sweeps": state["suspected_sweeps"],
        "attacker_clusters": attacker_clusters,
        "traced_clusters": traced_clusters
    }
    
    with open(TRACED_CLUSTERS_FILE, "w") as f:
        json.dump(output_state, f, indent=4)
        
    print(f"Saved traced clusters to {TRACED_CLUSTERS_FILE}")

if __name__ == "__main__":
    main()
