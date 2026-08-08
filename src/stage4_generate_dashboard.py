import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
# If trace hasn't run, we fallback to scored sweeps
TRACED_CLUSTERS_FILE = DATA_DIR / "traced_clusters.json"
SCORED_SWEEPS_FILE = DATA_DIR / "scored_sweeps.json"

METRICS_SUMMARY_FILE = DATA_DIR / "metrics_summary.json"
CLUSTERS_TIER_1_FILE = DATA_DIR / "clusters_tier_1.json"
CLUSTERS_TIER_2_FILE = DATA_DIR / "clusters_tier_2.json"
CLUSTERS_HEURISTIC_FILE = DATA_DIR / "clusters_heuristic.json"
TIMELINE_FILE = DATA_DIR / "timeline.json"
SCATTER_FILE = DATA_DIR / "scatter.json"

def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def main():
    print("Stage 4: Generating dashboard JSON files...")
    
    if TRACED_CLUSTERS_FILE.exists():
        with open(TRACED_CLUSTERS_FILE, "r") as f:
            state = json.load(f)
    elif SCORED_SWEEPS_FILE.exists():
        print(f"Warning: {TRACED_CLUSTERS_FILE} not found. Falling back to scored sweeps.")
        with open(SCORED_SWEEPS_FILE, "r") as f:
            state = json.load(f)
    else:
        print("Error: No input data found.")
        return

    total_stolen = 0
    total_stolen_tier_1 = 0
    total_stolen_tier_2 = 0
    total_stolen_heuristic = 0
    
    clusters_tier_1 = []
    clusters_tier_2 = []
    clusters_heuristic = []
    
    attacker_clusters = state.get("attacker_clusters", {})
    traced_clusters = state.get("traced_clusters", {})
    
    for address, info in attacker_clusters.items():
        total_stolen += info["total_received"]
        scores = info.get("confidence_scores", [])
        avg_confidence = sum(scores) / len(scores) if scores else 0
        
        cluster_data = {
            "address": address,
            "first_seen": info["first_seen"],
            "total_received": round(info["total_received"], 8),
            "avg_confidence": round(avg_confidence, 2),
            "breakdown": info.get("last_breakdown", {}),
            "tier": info.get("tier", "tier_3_heuristic")
        }
        
        # Add trace info if available
        if address in traced_clusters:
            cluster_data["trace_tree"] = traced_clusters[address].get("trace_tree")
            
        tier = info.get("tier")
        if tier == "tier_1_verified":
            total_stolen_tier_1 += info["total_received"]
            clusters_tier_1.append(cluster_data)
        elif tier == "tier_2_crowdsourced":
            total_stolen_tier_2 += info["total_received"]
            clusters_tier_2.append(cluster_data)
        else:
            total_stolen_heuristic += info["total_received"]
            clusters_heuristic.append(cluster_data)
            
    clusters_tier_1.sort(key=lambda x: x["total_received"], reverse=True)
    clusters_tier_2.sort(key=lambda x: x["total_received"], reverse=True)
    clusters_heuristic.sort(key=lambda x: x["total_received"], reverse=True)
        
    timeline_dict = {}
    scatter_data = []
    
    for sweep in state.get("suspected_sweeps", []):
        hour = sweep["date"].split(":")[0] + ":00:00"
        timeline_dict[hour] = timeline_dict.get(hour, 0.0) + sweep["value_btc"]
        
        if "fee_rate" in sweep:
            scatter_data.append({
                "date": sweep["date"],
                "fee_rate": sweep["fee_rate"],
                "value_btc": sweep["value_btc"],
                "confidence_score": sweep.get("confidence_score", 0),
                "tier": sweep.get("tier", "tier_3_heuristic")
            })
        
    timeline_output = [{"date": k, "stolen_amount": round(v, 8)} for k, v in sorted(timeline_dict.items())]

    summary_data = {
        "total_stolen_btc": round(total_stolen, 8),
        "total_stolen_tier_1_btc": round(total_stolen_tier_1, 8),
        "total_stolen_tier_2_btc": round(total_stolen_tier_2, 8),
        "total_stolen_heuristic_btc": round(total_stolen_heuristic, 8),
        "swept_utxos_count": len(state.get("suspected_sweeps", [])),
        "tier_1_clusters_count": len(clusters_tier_1),
        "tier_2_clusters_count": len(clusters_tier_2),
        "heuristic_clusters_count": len(clusters_heuristic),
        "externally_validated_btc": 1405.07,
        "galaxy_confirmed_btc": 1719,
        "victim_reports_count": 250,
        "median_dormancy_years": 3.5,
        "pct_coins_1yr_plus": 88,
        "median_loss_per_victim_btc": 1.022,
        "mean_loss_per_victim_btc": 4.04,
        "attacker_types_identified": 4,
        "waves_identified": 10,
        "addresses_drained_verified": 4925
    }
    
    write_json(METRICS_SUMMARY_FILE, summary_data)
    write_json(CLUSTERS_TIER_1_FILE, clusters_tier_1)
    write_json(CLUSTERS_TIER_2_FILE, clusters_tier_2)
    write_json(CLUSTERS_HEURISTIC_FILE, clusters_heuristic)
    write_json(TIMELINE_FILE, timeline_output)
    write_json(SCATTER_FILE, scatter_data)
        
    print(f"Metrics written to {DATA_DIR}")

if __name__ == "__main__":
    main()
