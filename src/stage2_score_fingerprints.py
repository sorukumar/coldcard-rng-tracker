import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
RAW_SWEEPS_FILE = DATA_DIR / "raw_sweeps.json"
ADDRESS_INTEL_FILE = DATA_DIR / "address_intel.json"
SCORED_SWEEPS_FILE = DATA_DIR / "scored_sweeps.json"

def calculate_fingerprint_confidence(tx, address_intel=None):
    breakdown = {
        "total": 0,
        "fee": False,
        "fee_matched": None,
        "destination": False,
        "version": False,
        "sequence": False,
        "bip69": False
    }
    
    fee_rate = tx.get("fee_rate", 0)
    output_address = tx.get("output_address")
    
    # --- PRIMARY SIGNAL A: Fee Rate Convergence (+35 pts) ---
    known_rates = {10.0: "wave_2b", 30.0: "wave_1", 50.2: "wave_2", 201.0: "wave_3"}
    for rate, wave in known_rates.items():
        if rate - 0.5 <= fee_rate <= rate + 0.5:
            breakdown["fee"] = True
            breakdown["fee_matched"] = rate
            breakdown["total"] += 35
            break
    
    # --- PRIMARY SIGNAL B: Destination Convergence (+30 pts) ---
    if address_intel and output_address and output_address in address_intel:
        breakdown["destination"] = True
        breakdown["total"] += 30
    
    # --- SECONDARY SIGNALS (boosters, max +30 combined) ---
    if tx.get("version") in [1, 2] and tx.get("locktime", 0) == 0:
        breakdown["version"] = True
        breakdown["total"] += 10
    
    expected_sequence = 0xfffffffd
    if any(seq == expected_sequence for seq in tx.get("vin_sequences", [])):
        breakdown["sequence"] = True
        breakdown["total"] += 10
    
    if tx.get("bip69_sorted", False):
        breakdown["bip69"] = True
        breakdown["total"] += 10
        
    return breakdown

def main():
    print("Stage 2: Scoring sweeps (Pure CPU)...")
    if not RAW_SWEEPS_FILE.exists():
        print(f"Error: {RAW_SWEEPS_FILE} not found. Run stage 1 first.")
        return
        
    with open(RAW_SWEEPS_FILE, "r") as f:
        raw_sweeps = json.load(f)
        
    address_intel = {}
    if ADDRESS_INTEL_FILE.exists():
        with open(ADDRESS_INTEL_FILE, "r") as f:
            address_intel = json.load(f)
            
    scored_sweeps = []
    attacker_clusters = {}
    intel_updated = False
    
    for tx in raw_sweeps:
        confidence_breakdown = calculate_fingerprint_confidence(tx, address_intel)
        confidence_score = confidence_breakdown["total"]
        
        if confidence_score < 50:
            continue
            
        address = tx["output_address"]
        value_btc = tx["value_btc"]
        
        tier = "tier_3_heuristic"
        if address in address_intel:
            tier = address_intel[address]["tier"]
            
            # Promote Tier 2 to Tier 1 based on strict heuristic match
            if tier == "tier_2_crowdsourced":
                print(f"Promoting {address} from tier 2 to tier 1 based on heuristic match.")
                address_intel[address]["tier"] = "tier_1_verified"
                address_intel[address]["notes"] += " (Promoted via heuristic validation)"
                tier = "tier_1_verified"
                intel_updated = True
        
        sweep_info = {
            "txid": tx["txid"],
            "height": tx["height"],
            "date": tx["date"],
            "attacker_address": address,
            "value_btc": value_btc,
            "fee_rate": tx["fee_rate"],
            "confidence_score": confidence_score,
            "confidence_breakdown": confidence_breakdown,
            "tier": tier
        }
        scored_sweeps.append(sweep_info)
        
        if address not in attacker_clusters:
            attacker_clusters[address] = {
                "first_seen": tx["date"],
                "total_received": 0.0,
                "confidence_scores": [],
                "tier": tier
            }
            
        attacker_clusters[address]["total_received"] += value_btc
        attacker_clusters[address]["confidence_scores"].append(confidence_score)
        attacker_clusters[address]["last_breakdown"] = confidence_breakdown
        attacker_clusters[address]["tier"] = tier

    state = {
        "suspected_sweeps": scored_sweeps,
        "attacker_clusters": attacker_clusters
    }
    
    with open(SCORED_SWEEPS_FILE, "w") as f:
        json.dump(state, f, indent=4)
        
    if intel_updated:
        with open(ADDRESS_INTEL_FILE, "w") as f:
            json.dump(address_intel, f, indent=4)
            
    print(f"Scored {len(scored_sweeps)} high-confidence sweeps.")
    print(f"Aggregated into {len(attacker_clusters)} clusters.")
    print(f"Saved to {SCORED_SWEEPS_FILE}")

if __name__ == "__main__":
    main()
