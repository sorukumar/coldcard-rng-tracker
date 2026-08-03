# Data Pipeline Methodology

This document outlines the methodology used by the Coldcard Investigation Data Pipeline to detect and track stolen funds across the Bitcoin blockchain.

## 1. Intelligence Tiers

Our pipeline categorizes addresses into three distinct tiers to ensure data integrity and prevent false positives from inflating our headline metrics:

*   **Tier 1: Verified Consolidators**: Addresses that are 100% confirmed to belong to the attacker. These are cross-validated by top research firms (Galaxy, Block) and manually verified.
*   **Tier 2: Crowdsourced Suspects**: Addresses reported by the community on social media (e.g. Twitter). We track these but do not include their totals in the verified headline figures.
*   **Tier 3: Heuristic Discoveries**: Addresses automatically flagged by our first-principles script because transactions sweeping funds into them strictly match the attacker's on-chain fingerprints. 

## 2. Data Sources

Our investigation draws from two categories of external intelligence:

### Attacker-Side Data (Where stolen funds landed)

| Source | Type | Storage |
|---|---|---|
| Galaxy Research, Block, Coinspect | Verified attacker consolidation/vault addresses | `address_intel.json` |
| Community reports (X/Twitter) | Reported attacker addresses | `address_intel.json` |
| coldcard-watch.vercel.app | Additional attacker addresses for cross-reference | `address_intel.json` |

### Victim-Side Data (Where stolen funds came from)

| Source | Type | Storage |
|---|---|---|
| coldcard-watch.vercel.app `/list.html` | 4,312 verified drained victim addresses (SHA-256 hashes) | `compromised_hashes.json` |

The victim hashes are used in our client-side privacy-preserving address checker tool. Users can hash their address locally and check for exposure without transmitting their address.

## 3. Detection Approach: Convergence Analysis

### Principles (Informed by coldcard-watch methodology)

Our detection is based on the concept of **convergence** — patterns that individual legitimate users cannot produce in coordination. A single sweep-shaped transaction (1 input, 1 output, no change) is not inherently suspicious; an owner rescuing coins produces the same shape. What an owner cannot produce is **convergence with hundreds of strangers.**

There are two forms of convergence observed in this incident:

**Convergence of Destination** (Waves 1 & 2): Hundreds of sweeps arriving at the same address, at the same fee rate, in the same time window. A thousand separate owners cannot share one destination.

**Convergence of Fee** (Wave 3): When the attacker removed the shared destination (giving each victim their own fresh vault), the fee rate remained constant. 214+ sweeps all paying exactly 201.0 sat/vB when the network was charging ~3 sat/vB. A rate that constant across unrelated transactions is hardcoded in a script, not independently chosen by 215 strangers.

### Current Implementation (v1 — Checklist Scoring)

Our current `fetch_blocks.py` implements a 4-point fingerprint checklist:

1.  **Multi-Wave Fee Rates (+25 pts)**: The attacker utilized hardcoded fee rates across distinct waves:
    *   `30.0 sat/vB` (Wave 1)
    *   `50.2 sat/vB` (Wave 2)
    *   `10.0 sat/vB` (Wave 2b)
    *   `201.0 sat/vB` (Wave 3)
2.  **RBF Sequence (+25 pts)**: The attacker forced a specific Replace-By-Fee sequence (`0xfffffffd`).
3.  **Version/Locktime (+25 pts)**: Expected version (`1` or `2`) and `locktime=0`.
4.  **BIP-69 Sorting (+25 pts)**: Lexicographical sorting of inputs and outputs.

If a transaction generates a confidence score of **50 or higher**, the destination address is flagged as a Tier 3 Heuristic Discovery.

### Known Limitations of v1

> **False Positive Problem**: Our current threshold of 50 allows combinations like `version+bip69` (no fee match) to pass. These two signals alone are true for the vast majority of all Bitcoin transactions. As of the current scan, ~59,779 of our 60,249 confidence=50 sweeps do not match any known attack fee rate. This inflates our heuristic totals to ~39,107 BTC vs the ~1,359 BTC independently verified by coldcard-watch.

### Planned Improvement (v2 — Convergence Scoring)

The next iteration will adopt multi-layered convergence scoring that weights **fee convergence** and **destination convergence** as primary signals, with metadata as secondary boosters. See `investigation_insights.md` for the full plan.

## 4. Automated Promotion

If a **Tier 2 (Crowdsourced)** address receives a transaction that strongly matches our strict heuristics (score >= 50), the pipeline automatically promotes that address to **Tier 1 (Verified)**, creating a powerful automated feedback loop for community intelligence.

## 5. On-Chain Fingerprints by Wave

We scan specific targeted block ranges (Blocks `960183`–`960481`) corresponding to three observed attack waves:

| Wave | Date | Block Range | Fee Rate | Addresses | BTC | Notes |
|---|---|---|---|---|---|---|
| 1 | Jul 30, 01:10–01:51 UTC | 960183–960191 | 30.0 sat/vB | 1,195 | 1,082.65 | Shared collectors. Cross-validated with Galaxy/Block. |
| 2 | Jul 31, 04:54–08:36 UTC | 960345–960369 | 50.2 sat/vB | 1,126 | 45.97 | Shared collector. RBF enabled (Wave 1 did not). |
| 2b | Jul 31 | 960345–960369 | 10.0 sat/vB | 352 | 30.18 | Separate collector, reported by Galaxy Research Aug 1. |
| 3 | Jul 31, 12:23–22:25 UTC | 960400–960480 | 201.0 sat/vB | 1,626 | 200.33 | **No shared collector.** Each victim → unique fresh address → unique P2WSH vault. 214 vaults, all unspent. |

Source: [coldcard-watch.vercel.app/methodology.html](https://coldcard-watch.vercel.app/methodology.html) (independently verified)

Total confirmed by coldcard-watch: **4,312 addresses, ~1,359 BTC**

## 6. Evasion Tactics (Wave 3)

In early waves, the attacker swept thousands of wallets into a handful of shared collector addresses. 
During Wave 3 (July 31st), the attacker changed tactics to evade address-clustering detection: they swept every victim wallet into its own completely fresh, dedicated P2WSH vault. 

Because they did not reuse addresses, our system relies entirely on the strict `201.0 sat/vB` fingerprint to track Wave 3. This generated tens of thousands of individual clusters in our Tier 3 bucket, successfully capturing the decentralized sweeps without polluting the Tier 1 verified metrics.

## 7. Pipeline Architecture

### Current (2-script)

```
fetch_blocks.py          → state.json → decoupled dashboard JSON files
                           (Bitcoin RPC)

generate_deep_metrics.py → metrics.json (legacy, 100MB, largely superseded)
                           (Bitcoin RPC + Electrs)
```

### Planned (4-stage)

```
Stage 1: fetch_raw_sweeps.py    → raw_sweeps.json        (Bitcoin RPC only)
Stage 2: score_sweeps.py        → scored_sweeps.json      (Pure CPU)
Stage 3: enrich_clusters.py     → traced_clusters.json    (Electrs, cached)
Stage 4: generate_dashboard.py  → frontend JSON files     (Pure CPU)
```

Key benefits: decouple extraction from scoring (re-run scoring without re-fetching), protect Electrs (only trace high-confidence clusters), enable validation against external datasets.

## 8. Vulnerability Timeline

| Version | Date | Model | Status | Approx Block Height |
|---|---|---|---|---|
| v4.0.1 | March 2021 | Mk3 | ❌ Vulnerable (~40-bit entropy) | ~675,000 |
| v4.1.0–4.1.9 | 2021–2024 | Mk3 | ❌ Vulnerable (~40-bit entropy) | ~675,000–840,000 |
| v5.0.0+ | 2023+ | Mk4 | ⚠️ Partial (~72-bit) | ~780,000+ |
| Q 1.0.0+ | 2024+ | Q | ⚠️ Partial (~72-bit) | ~830,000+ |
| v4.2.0 | July 31, 2026 | Mk3 | ✅ Fixed | ~960,200 |
| v5.6.0 | July 31, 2026 | Mk4/Mk5 | ✅ Fixed | ~960,200 |

Note from coldcard-watch: the oldest coin in the verified victim set was created in block 677,217, approximately two weeks after the vulnerable firmware shipped. Nothing in the set predates the flaw.
