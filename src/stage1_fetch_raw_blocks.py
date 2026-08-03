import os
import json
import requests
from datetime import datetime, UTC
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BTC_RPC_HOST = os.getenv("BTC_RPC_HOST", "100.84.222.115")
BTC_RPC_PORT = os.getenv("BTC_RPC_PORT", "8332")
BTC_RPC_USER = os.getenv("BTC_RPC_USER", "umbrel")
BTC_RPC_PASSWORD = os.getenv("BTC_RPC_PASSWORD", "")

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
RAW_SWEEPS_FILE = DATA_DIR / "raw_sweeps.json"

# Specific blocks for the vulnerability investigation
THEFT_BLOCKS = [
    # Wave 1: Jul 30
    *range(960183, 960192),
    # Wave 2: Jul 31 (Includes 50.2 sat/vB and 10.0 sat/vB waves)
    *range(960345, 960370),
    # Wave 3: Jul 31 (201.0 sat/vB decentralized vaults)
    *range(960400, 960481)
]

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
        return self._call("getblock", [block_hash, 2])

def is_bip69_sorted(tx):
    # Inputs
    if len(tx.get("vin", [])) > 1:
        prev_input = None
        for vin in tx["vin"]:
            txid_hex = vin.get("txid", "")
            vout = vin.get("vout", 0)
            if not txid_hex: continue
            try: txid_bytes = bytes.fromhex(txid_hex)[::-1]
            except ValueError: txid_bytes = b""
            curr = (txid_bytes, vout)
            if prev_input and curr < prev_input: return False
            prev_input = curr
            
    # Outputs
    if len(tx.get("vout", [])) > 1:
        prev_output = None
        for vout in tx["vout"]:
            val = vout.get("value", 0.0)
            sats = int(val * 100_000_000)
            script_hex = vout.get("scriptPubKey", {}).get("hex", "")
            try: script_bytes = bytes.fromhex(script_hex)
            except ValueError: script_bytes = b""
            curr = (sats, script_bytes)
            if prev_output and curr < prev_output: return False
            prev_output = curr
            
    return True

def is_potential_sweep(tx):
    if len(tx.get("vout", [])) != 1: return False
    if not tx.get("vin"): return False
    
    valid_input = False
    for vin in tx["vin"]:
        if "txinwitness" in vin or ("scriptSig" in vin and vin["scriptSig"].get("hex")):
            valid_input = True
            break
    if not valid_input: return False
        
    vout = tx["vout"][0]
    if "scriptPubKey" not in vout or "address" not in vout["scriptPubKey"]: return False
    return True

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rpc = BitcoinRpcClient(BTC_RPC_HOST, BTC_RPC_PORT, BTC_RPC_USER, BTC_RPC_PASSWORD)
    
    current_height = rpc.get_block_count()
    blocks_to_scan = [b for b in THEFT_BLOCKS if b <= current_height]
    
    print(f"Stage 1: Fetching raw sweeps from {len(blocks_to_scan)} blocks via RPC...")
    
    raw_sweeps = []
    
    for height in blocks_to_scan:
        if height % 10 == 0:
            print(f"Scanning block {height}...")
            
        block_hash = rpc.get_block_hash(height)
        block = rpc.get_block(block_hash)
        
        block_time = block["time"]
        date_str = datetime.fromtimestamp(block_time, UTC).strftime('%Y-%m-%d %H:%M:%S')
        
        for tx in block["tx"]:
            if "coinbase" in tx["vin"][0]: continue
                
            if not is_potential_sweep(tx):
                continue
                
            fee_sats = tx.get("fee", 0.0) * 100_000_000
            vsize = tx.get("vsize", 1)
            fee_rate = fee_sats / vsize if vsize > 0 else 0
            
            output_address = tx["vout"][0]["scriptPubKey"]["address"]
            value_btc = tx["vout"][0]["value"]
            
            raw_sweep = {
                "txid": tx["txid"],
                "height": height,
                "date": date_str,
                "fee_rate": round(fee_rate, 2),
                "version": tx.get("version"),
                "locktime": tx.get("locktime", 0),
                "bip69_sorted": is_bip69_sorted(tx),
                "output_address": output_address,
                "value_btc": value_btc,
                "vin_sequences": [vin.get("sequence") for vin in tx.get("vin", [])]
            }
            raw_sweeps.append(raw_sweep)
            
    print(f"Found {len(raw_sweeps)} potential sweeps.")
    with open(RAW_SWEEPS_FILE, "w") as f:
        json.dump(raw_sweeps, f, indent=4)
    print(f"Saved to {RAW_SWEEPS_FILE}")

if __name__ == "__main__":
    main()
