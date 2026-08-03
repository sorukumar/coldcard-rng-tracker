import os
import json
import requests
import time
from datetime import datetime
from pathlib import Path
import concurrent.futures
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
    def __init__(self, base_url, pool_size=10):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def get_address_info(self, address):
        response = self.session.get(f"{self.base_url}/address/{address}", timeout=10)
        response.raise_for_status()
        return response.json()
        
    def get_address_txs(self, address):
        response = self.session.get(f"{self.base_url}/address/{address}/txs", timeout=15)
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


def trace_to_consolidation(electrs, start_address, max_hops=3):
    current_address = start_address
    hop_count = 0
    
    while hop_count < max_hops:
        try:
            addr_info = electrs.get_address_info(current_address)
            funded = addr_info.get('chain_stats', {}).get('funded_txo_sum', 0)
            spent = addr_info.get('chain_stats', {}).get('spent_txo_sum', 0)
            balance = funded - spent
            
            # If it still holds a balance, we consider it a terminal/consolidation node
            if balance > 0:
                break
                
            txs = electrs.get_address_txs(current_address)
            
            spent_tx = None
            for tx in txs:
                for vin in tx.get('vin', []):
                    if vin.get('prevout', {}).get('scriptpubkey_address') == current_address:
                        spent_tx = tx
                        break
                if spent_tx:
                    break
                    
            if not spent_tx:
                break
                
            largest_vout = None
            max_val = -1
            for vout in spent_tx.get('vout', []):
                if vout.get('value', 0) > max_val:
                    max_val = vout.get('value', 0)
                    largest_vout = vout
                    
            if largest_vout and largest_vout.get('scriptpubkey_address'):
                next_address = largest_vout['scriptpubkey_address']
                if next_address == current_address:
                    break
                current_address = next_address
                hop_count += 1
            else:
                break
                
        except Exception as e:
            print(f"Error tracing address {current_address}: {e}")
            break
            
    return current_address


def is_bip69_sorted(tx):
    # Inputs
    if len(tx.get("vin", [])) > 1:
        prev_input = None
        for vin in tx["vin"]:
            txid_hex = vin.get("txid", "")
            vout = vin.get("vout", 0)
            if not txid_hex:
                continue
            
            try:
                txid_bytes = bytes.fromhex(txid_hex)[::-1]
            except ValueError:
                txid_bytes = b""
                
            curr = (txid_bytes, vout)
            if prev_input and curr < prev_input:
                return False
            prev_input = curr
            
    # Outputs
    if len(tx.get("vout", [])) > 1:
        prev_output = None
        for vout in tx["vout"]:
            val = vout.get("value", 0.0)
            sats = int(val * 100_000_000)
            script_hex = vout.get("scriptPubKey", {}).get("hex", "")
            
            try:
                script_bytes = bytes.fromhex(script_hex)
            except ValueError:
                script_bytes = b""
                
            curr = (sats, script_bytes)
            if prev_output and curr < prev_output:
                return False
            prev_output = curr
            
    return True

def calculate_fingerprint_confidence(tx, fee_rate):
    score = 0
    
    # 1. 30 sat/vB exact fee rate
    if 29.5 <= fee_rate <= 30.5:
        score += 25
        
    # 2. Version and Locktime
    if tx.get("version") in [1, 2] and tx.get("locktime", 0) == 0:
        score += 25
        
    # 3. RBF nSequence match (0xfffffffd is often used by standard APIs for RBF)
    expected_sequence = 0xfffffffd
    sequence_matched = False
    for vin in tx.get("vin", []):
        if vin.get("sequence") == expected_sequence:
            sequence_matched = True
            break
    if sequence_matched:
        score += 25
        
    # 4. BIP69 sorting
    if is_bip69_sorted(tx):
        score += 25
        
    return score

def is_potential_sweep(tx):
    """
    Heuristic to identify a potential attacker sweep of a vulnerable UTXO.
    """
    # 1. Sweep txs usually have exactly 1 output (no change).
    if len(tx.get("vout", [])) != 1:
        return False
        
    # 2. Must have inputs
    if not tx.get("vin"):
        return False
        
    # 3. Check for single-sig scripts (BIP-84, 49, 44)
    valid_input = False
    for vin in tx["vin"]:
        if "txinwitness" in vin or ("scriptSig" in vin and vin["scriptSig"].get("hex")):
            valid_input = True
            break
            
    if not valid_input:
        return False
        
    # 4. Check if the output address is a valid P2WPKH or P2TR
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
                
                fee_sats = tx.get("fee", 0.0) * 100_000_000
                vsize = tx.get("vsize", 1)
                fee_rate = fee_sats / vsize if vsize > 0 else 0
                
                confidence = calculate_fingerprint_confidence(tx, fee_rate)
                
                # Add to suspected sweeps
                sweep_info = {
                    "txid": tx["txid"],
                    "height": height,
                    "date": date_str,
                    "attacker_address": address,
                    "value_btc": value_btc,
                    "fee_rate": round(fee_rate, 2),
                    "confidence_score": confidence
                }
                state["suspected_sweeps"].append(sweep_info)
                
                # Update clusters
                if address not in state["attacker_clusters"]:
                    state["attacker_clusters"][address] = {
                        "first_seen": date_str,
                        "total_received": 0.0,
                        "confidence_scores": []
                    }
                state["attacker_clusters"][address]["total_received"] += value_btc
                state["attacker_clusters"][address].setdefault("confidence_scores", []).append(confidence)

        state["last_scanned_block"] = height
        # Save state every 10 blocks to prevent data loss
        if height % 10 == 0:
            save_state(state)
            
    return state


def generate_metrics(electrs, state):
    total_stolen = 0
    clusters_output = []
    
    print("Fetching current balances and tracing hops for attacker clusters from Electrs (this may take time)...")
    
    final_clusters = {}
    known_traces = {}
    
    addresses_to_trace = list(state["attacker_clusters"].keys())
    total_addresses = len(addresses_to_trace)
    processed_count = 0
    
    def process_address(addr):
        time.sleep(0.3)
        return addr, trace_to_consolidation(electrs, addr, max_hops=3)

    print(f"Starting trace for {total_addresses} addresses with 1 worker (safe mode)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future_to_addr = {executor.submit(process_address, addr): addr for addr in addresses_to_trace}
        for future in concurrent.futures.as_completed(future_to_addr):
            addr, final_addr = future.result()
            known_traces[addr] = final_addr
            processed_count += 1
            if processed_count % 1000 == 0:
                print(f"Traced {processed_count}/{total_addresses} addresses...")
    
    for address, info in state["attacker_clusters"].items():
        total_stolen += info["total_received"]
        
        final_address = known_traces[address]
            
        if final_address not in final_clusters:
            final_clusters[final_address] = {
                "first_seen": info["first_seen"],
                "total_received": 0.0,
                "confidence_scores": [],
                "source_addresses": set()
            }
            
        final_clusters[final_address]["total_received"] += info["total_received"]
        final_clusters[final_address]["confidence_scores"].extend(info.get("confidence_scores", []))
        final_clusters[final_address]["source_addresses"].add(address)
        
        if info["first_seen"] < final_clusters[final_address]["first_seen"]:
            final_clusters[final_address]["first_seen"] = info["first_seen"]
            
    def get_balance(final_addr):
        time.sleep(0.3)
        try:
            addr_info = electrs.get_address_info(final_addr)
            funded_sats = addr_info.get('chain_stats', {}).get('funded_txo_sum', 0)
            spent_sats = addr_info.get('chain_stats', {}).get('spent_txo_sum', 0)
            return final_addr, (funded_sats - spent_sats) / 100_000_000.0
        except Exception as e:
            print(f"Warning: Failed to fetch balance for {final_addr}: {e}")
            return final_addr, 0.0

    print(f"Fetching balances for {len(final_clusters)} final consolidation addresses...")
    balances = {}
    processed_final = 0
    total_final = len(final_clusters)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future_to_final = {executor.submit(get_balance, addr): addr for addr in final_clusters.keys()}
        for future in concurrent.futures.as_completed(future_to_final):
            addr, bal = future.result()
            balances[addr] = bal
            processed_final += 1
            if processed_final % 1000 == 0:
                print(f"Fetched balances for {processed_final}/{total_final} addresses...")
        
    for final_address, data in final_clusters.items():
        current_balance = balances[final_address]
            
        scores = data["confidence_scores"]
        avg_confidence = sum(scores) / len(scores) if scores else 0

        clusters_output.append({
            "address": final_address,
            "first_seen": data["first_seen"],
            "total_received": round(data["total_received"], 8),
            "current_balance": round(current_balance, 8),
            "avg_confidence": round(avg_confidence, 2),
            "sources_count": len(data["source_addresses"])
        })
        
    clusters_output.sort(key=lambda x: x["total_received"], reverse=True)
        
    # Aggregate timeline and scatter
    timeline_dict = {}
    scatter_data = []
    
    for sweep in state["suspected_sweeps"]:
        date = sweep["date"]
        timeline_dict[date] = timeline_dict.get(date, 0.0) + sweep["value_btc"]
        
        if "fee_rate" in sweep:
            scatter_data.append({
                "date": date,
                "fee_rate": sweep["fee_rate"],
                "value_btc": sweep["value_btc"],
                "confidence_score": sweep.get("confidence_score", 0)
            })
        
    timeline_output = [{"date": k, "stolen_amount": round(v, 8)} for k, v in sorted(timeline_dict.items())]

    summary = {
        "total_stolen_btc": round(total_stolen, 8),
        "swept_utxos_count": len(state["suspected_sweeps"]),
        "estimated_rescued_btc": 0.0 # To be implemented (tracking user rescues)
    }

    data = {
        "summary": summary,
        "timeline": timeline_output,
        "scatter": scatter_data,
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
