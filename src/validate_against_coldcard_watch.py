"""
Cross-validates our pipeline's detections against coldcard-watch's 
verified 4,312 victim addresses.

Our pipeline finds ATTACKER addresses (destinations of sweeps).
coldcard-watch lists VICTIM addresses (sources of sweeps).
These are opposite sides of the same transaction.

To cross-validate, we check: for each victim address in coldcard-watch,
is there a sweep in our state.json whose transaction involves that victim?

Since we don't currently store victim (input) addresses in our sweep records,
we use a different approach: compare the BLOCK heights and AMOUNTS.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"

def main():
    # Load our state
    state_path = DATA_DIR / "state.json"
    if not state_path.exists():
        print("ERROR: state.json not found. Run fetch_blocks.py first.")
        return
    
    state = json.load(open(state_path))
    
    # Load coldcard-watch victim data
    victim_path = DATA_DIR / "victim_addresses.json"
    if not victim_path.exists():
        print("ERROR: victim_addresses.json not found. Run scrape_coldcard_watch.py first.")
        return
    
    victims = json.load(open(victim_path))
    
    print(f"Our pipeline: {len(state['suspected_sweeps'])} sweeps, {len(state['attacker_clusters'])} clusters")
    print(f"coldcard-watch: {len(victims)} verified victim addresses")
    print()
    
    # Build a set of (block_height, amount_btc_rounded) from coldcard-watch
    # This is an approximate match since we can't compare addresses directly
    cw_set = set()
    cw_by_block = {}
    for v in victims:
        height = v["block_height"]
        amount = round(v["amount_btc"], 6)
        cw_set.add((height, amount))
        cw_by_block[height] = cw_by_block.get(height, 0) + 1
    
    # Build same from our sweeps
    our_set = set()
    our_by_block = {}
    for s in state["suspected_sweeps"]:
        height = s["height"]
        amount = round(s["value_btc"], 6)
        our_set.add((height, amount))
        our_by_block[height] = our_by_block.get(height, 0) + 1
    
    # Compare
    overlap = cw_set & our_set
    cw_only = cw_set - our_set
    our_only = our_set - cw_set
    
    print(f"=== Cross-Validation Results ===")
    print(f"Matches (in both):     {len(overlap)}")
    print(f"coldcard-watch only:   {len(cw_only)} (we missed these)")
    print(f"Our pipeline only:     {len(our_only)} (could be false positives or additional finds)")
    print()
    
    # Coverage by block
    print(f"=== Block Coverage ===")
    all_blocks = sorted(set(list(cw_by_block.keys()) + list(our_by_block.keys())))
    for block in all_blocks[:20]:  # Show first 20 blocks
        cw_count = cw_by_block.get(block, 0)
        our_count = our_by_block.get(block, 0)
        marker = "✓" if cw_count > 0 and our_count > 0 else "⚠"
        print(f"  {marker} Block {block}: coldcard-watch={cw_count}, ours={our_count}")
    if len(all_blocks) > 20:
        print(f"  ... and {len(all_blocks) - 20} more blocks")
    
    # Total BTC comparison
    cw_total_btc = sum(v["amount_btc"] for v in victims)
    our_total_btc = sum(s["value_btc"] for s in state["suspected_sweeps"])
    
    # Tier breakdown of our total
    tier_btc = {}
    for s in state["suspected_sweeps"]:
        t = s.get("tier", "unknown")
        tier_btc[t] = tier_btc.get(t, 0) + s["value_btc"]
    
    print()
    print(f"=== BTC Totals ===")
    print(f"coldcard-watch verified: {cw_total_btc:.2f} BTC")
    print(f"Our pipeline total:      {our_total_btc:.2f} BTC")
    for tier, btc in sorted(tier_btc.items()):
        print(f"  {tier}: {btc:.2f} BTC")

if __name__ == "__main__":
    main()
