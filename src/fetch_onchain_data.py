import os
import json
import requests
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ELECTRS_URL = os.getenv("ELECTRS_URL", "http://100.84.222.115:3006/api")
BTC_RPC_HOST = os.getenv("BTC_RPC_HOST", "100.84.222.115")
BTC_RPC_PORT = os.getenv("BTC_RPC_PORT", "8332")
BTC_RPC_USER = os.getenv("BTC_RPC_USER", "umbrel")
BTC_RPC_PASSWORD = os.getenv("BTC_RPC_PASSWORD", "")

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
STATE_FILE = DATA_DIR / "state.json"
METRICS_FILE = DATA_DIR / "metrics.json"

# Heuristics settings
# We'll set a default start block. This can be adjusted to the exact firmware release block height.
START_BLOCK = 850000 
MAX_BLOCKS_PER_RUN = 100

class BitcoinRpcClient:
    def __init__(self, host, port, user, password):
        self.url = f"http://{user}:{password}@{host}:{port}"

    def _call(self, method, params=[]):
        payload = {
            "jsonrpc": "1.0",
            "id": "coldcard-investigator",
            "method": method,
            "params": params
        }
        response = requests.post(self.url, json=payload, timeout=30)
        response.raise_for_status()
        res_json = response.json()
        if res_json.get("error"):
            raise Exception(res_json["error"])
        return res_json["result"]

    def get_block_count(self):
        return self._call("getblockcount")

    def get_block_hash(self, height):
        return self._call("getblockhash", [height])

    def get_block(self, block_hash):
        # verbosity=2 gives full transaction details
        return self._call("getblock", [block_hash, 2])

class ElectrsClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')

    def get_address_info(self, address):
        response = requests.get(f"{self.base_url}/address/{address}", timeout=10)
        response.raise_for_status()
        return response.json()


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_scanned_block": START_BLOCK - 1,
        "suspected_sweeps": [],
        "attacker_clusters": {}
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def is_potential_sweep(tx):
    """
    Heuristic to identify a potential attacker sweep of a vulnerable UTXO.
    """
    # 1. Sweep txs usually have exactly 1 output (no change).
    if len(tx["vout"]) != 1:
        return False
        
    # 2. Must have inputs
    if not tx["vin"]:
        return False
        
    # 3. Check for RBF (Sequence < 0xffffffff - 1). Attackers often use RBF to outbid the victim.
    is_rbf = False
    for vin in tx["vin"]:
        if "sequence" in vin and vin["sequence"] < 0xfffffffe:
            is_rbf = True
            break
            
    if not is_rbf:
        return False
        
    # Optional: check if the output address is a valid P2WPKH or P2TR
    # Here we just ensure we can parse the address
    vout = tx["vout"][0]
    if "scriptPubKey" not in vout or "address" not in vout["scriptPubKey"]:
        return False
        
    return True


def scan_blocks(rpc, state):
    current_height = rpc.get_block_count()
    start_height = state["last_scanned_block"] + 1
    end_height = min(start_height + MAX_BLOCKS_PER_RUN - 1, current_height)
    
    if start_height > current_height:
        print("Already at chain tip.")
        return state

    print(f"Scanning blocks {start_height} to {end_height}...")
    
    for height in range(start_height, end_height + 1):
        if height % 10 == 0:
            print(f"Scanning block {height}...")
            
        block_hash = rpc.get_block_hash(height)
        block = rpc.get_block(block_hash)
        
        block_time = block["time"]
        date_str = datetime.utcfromtimestamp(block_time).strftime('%Y-%m-%d')
        
        for tx in block["tx"]:
            # Skip coinbase
            if "coinbase" in tx["vin"][0]:
                continue
                
            if is_potential_sweep(tx):
                address = tx["vout"][0]["scriptPubKey"]["address"]
                value_btc = tx["vout"][0]["value"]
                
                # Add to suspected sweeps
                sweep_info = {
                    "txid": tx["txid"],
                    "height": height,
                    "date": date_str,
                    "attacker_address": address,
                    "value_btc": value_btc
                }
                state["suspected_sweeps"].append(sweep_info)
                
                # Update clusters
                if address not in state["attacker_clusters"]:
                    state["attacker_clusters"][address] = {
                        "first_seen": date_str,
                        "total_received": 0.0
                    }
                state["attacker_clusters"][address]["total_received"] += value_btc

        state["last_scanned_block"] = height
        # Save state every 10 blocks to prevent data loss
        if height % 10 == 0:
            save_state(state)
            
    return state


def generate_metrics(electrs, state):
    total_stolen = 0
    clusters_output = []
    
    print("Fetching current balances for attacker clusters from Electrs...")
    
    for address, info in state["attacker_clusters"].items():
        total_stolen += info["total_received"]
        
        # Get current balance from Electrs
        try:
            addr_info = electrs.get_address_info(address)
            funded_sats = addr_info.get('chain_stats', {}).get('funded_txo_sum', 0)
            spent_sats = addr_info.get('chain_stats', {}).get('spent_txo_sum', 0)
            current_balance = (funded_sats - spent_sats) / 100_000_000.0
        except Exception as e:
            print(f"Warning: Failed to fetch balance for {address}: {e}")
            current_balance = 0.0
            
        clusters_output.append({
            "address": address,
            "first_seen": info["first_seen"],
            "total_received": round(info["total_received"], 8),
            "current_balance": round(current_balance, 8)
        })
        
    # Aggregate timeline
    timeline_dict = {}
    for sweep in state["suspected_sweeps"]:
        date = sweep["date"]
        timeline_dict[date] = timeline_dict.get(date, 0.0) + sweep["value_btc"]
        
    timeline_output = [{"date": k, "stolen_amount": round(v, 8)} for k, v in sorted(timeline_dict.items())]

    summary = {
        "total_stolen_btc": round(total_stolen, 8),
        "swept_utxos_count": len(state["suspected_sweeps"]),
        "estimated_rescued_btc": 0.0 # To be implemented (tracking user rescues)
    }

    data = {
        "summary": summary,
        "timeline": timeline_output,
        "clusters": clusters_output
    }
    
    with open(METRICS_FILE, "w") as f:
        json.dump(data, f, indent=4)
        
    print(f"Metrics written to {METRICS_FILE}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Loading state...")
    state = load_state()
    
    print(f"Connecting to Bitcoin RPC at {BTC_RPC_HOST}:{BTC_RPC_PORT}")
    rpc = BitcoinRpcClient(BTC_RPC_HOST, BTC_RPC_PORT, BTC_RPC_USER, BTC_RPC_PASSWORD)
    
    print(f"Connecting to Electrs at {ELECTRS_URL}")
    electrs = ElectrsClient(ELECTRS_URL)
    
    # Run a block scanning iteration
    try:
        state = scan_blocks(rpc, state)
    except Exception as e:
        print(f"Error scanning blocks: {e}")
    finally:
        save_state(state)
        
    # Generate the frontend metrics JSON
    generate_metrics(electrs, state)


if __name__ == "__main__":
    main()
