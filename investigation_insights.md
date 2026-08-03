# Coldcard Investigation Insights

This document serves as a living repository for clues, hypotheses, and actionable intelligence regarding the Coldcard RNG vulnerability and the subsequent wallet drain. As we ingest more data, thread analyses, and blog posts, we will synthesize our next steps here.

## 1. Incident Overview
*   **Scale**: ~594–1,083 BTC (~$38M–$70M+) swept from ~500–1,196 single-signature addresses.
*   **Timing**: Primary observed wave occurred ~01:10–01:56 UTC on 2026-07-30 (blocks ~960183–960191).
*   **Nature of Attack**: Automated sweeps. Attackers already knew the keys via offline brute force or candidate scanning; no interactive device compromise required. The attack cost is trivially low (independent researchers confirmed finding 2 stolen keys in ~5 mins for <$5 of GPU time).
*   **Targets**: Primarily single-sig wallets. High-value wallets were hit early in the sequence. Funds were rapidly consolidated and currently remain mostly static.

## 2. Technical Root Cause
*   **RNG Fallback Issue**: A firmware change (commit ~March 2021, first in v4.0.0) moved seed generation from the hardware RNG (`ckcc.rng_bytes`) to `ngu.random.bytes`. Due to a misconfigured `#ifndef` check in `libngu`, it fell back to MicroPython’s Yasmarang PRNG.
*   **Entropy Sources**: The PRNG was seeded from non-secret or constrained sources: MCU UID, SysTick, and RTC registers.
*   **Mk2/Mk3 Impact (v4.0.0–4.1.9)**: Wallet generation was highly deterministic, providing roughly a 40-bit search space once the UID and timing were profiled. *Note: Firmware v3.2.2 and earlier used the hardware RNG directly and are not affected.*
*   **Mk4 / Q / Mk5 Impact**: Added a secure-element reseed, but truncated to 32 bits, resulting in an effective entropy of ~72 bits instead of the intended 128-bit target. **Critical First-Principles Caveat**: While the manufacturer claims these newer models are "less impacted," cryptography relies on absolute margins. 72 bits of entropy is fundamentally insecure against well-resourced offline cracking, and implementation flaws in how the 32-bit SE output mixes with the PRNG could reduce effective entropy even further.
*   **Remediation & First Principles Skepticism**: We must not take manufacturer disclosures as absolute truth. From first principles, any seed generated on firmware v4.0.0+ (regardless of the hardware model) operated on a structurally flawed RNG and should be treated as compromised. Fixed firmware is available (Mk3 4.2.0+, Mk4/Mk5 5.6.0+, Q 1.5.0Q+), but users must generate *new* seeds on fixed firmware. For Mk2 devices, no fixed firmware is published.
*   **Structural Mitigation**: This incident highlights the critical value of **multi-vendor / multi-device Multisig** (e.g., 2-of-3 with diverse entropy sources). A failure in a single hardware RNG does not result in loss of funds if the other keys (e.g., phone, server, or different vendor hardware) maintain strong entropy.

## 3. On-Chain Observables & Clues
Based on analyses by Galaxy Research, Chainalysis, and The Block:

### Clue 1: The "API Fingerprint"
*   **Observation**: The attacker utilized a paid account at a well-known blockchain-services provider (e.g., BlockCypher, Tatum, Alchemy, or Mempool.space Enterprise) to query source addresses and execute sweeps.
*   **Insight**: Commercial blockchain APIs inject highly distinct structural footprints into the transactions they generate. The Block noted an “unusual pattern” / “full fingerprint” shared by the known set and an additional ~695 earlier transactions.

### Clue 2: Predictable Transaction Construction (Multi-Wave Fee Rates)
*   **Fee Rates**: The attacker utilized hardcoded fee rates across distinct waves of the attack. 
    *   **Wave 1 (July 30):** 30.0 sat/vB.
    *   **Wave 2 (July 31):** 50.2 sat/vB (with Replace-by-Fee sequence enabled).
    *   **Wave 2b (July 31):** 10.0 sat/vB.
    *   **Wave 3 (July 31):** 201.0 sat/vB (an extreme overpayment to bypass congestion).
*   **Outputs**: No change outputs; these were full spends (sweeps).
*   **Script Types**: Heavily native SegWit (BIP-84) with a minority of BIP-49/BIP-44, indicating multi-derivation-path scanning.
*   **Broadcasting**: Batch-style broadcasting across highly concentrated block windows.

### Clue 3: Consolidation Patterns & Evasion Tactics
*   **Wave 1 & 2 (Centralized Collection)**: Funds were initially swept into a small set of collector addresses and largely remain there. Known final consolidation addresses (Tier 1 Verified):
    *   `bc1qq85v2c926eg6pgxhwp6q7lf6cnsz80qs3fcu9r` (~562 BTC)
    *   `bc1qx76cae2706qd5q576feh7xq8rfcsjpf2htfhe3` (~398 BTC)
    *   `bc1q8jy96fe5lf8vfugydnte3cguk92gpev7kwtp3q` (~90 BTC)
    *   `bc1qnk4zh9qcnap2mycp56qjrgza3cc8ylrh8fecp0` (~32 BTC)
*   **Wave 3 (Decentralized Evasion)**: In later waves, the attacker changed tactics to evade detection. Instead of sweeping funds into shared collector addresses, they swept every individual victim wallet into its own fresh, isolated P2WSH vault address. This creates tens of thousands of single-transaction clusters that can only be flagged via strict on-chain fingerprinting (e.g., the 201.0 sat/vB fee rate).

### Clue 4: Evolving Community Efforts & Attacker Response
*   The community is actively tracking the exploit, with basic tracking dashboards already emerging (e.g., [Noackdom's Tracker](https://x.com/noackdom/status/2083235584537931777)). 
*   Given the high visibility of this vulnerability and public discourse (like the detailed Galaxy Research and Block threads), the attacker is highly likely to change their sweeping strategy, fee rates, or consolidation methods in secondary waves.

## 4. Plan of Action for Investigation
Based on the synthesis of the above intelligence, our ongoing on-chain investigation should focus on the following core tasks:

### Task 1: Expand the Known Victim Set
*   **Action**: Query on-chain data for all transactions within the primary attack windows (~115 targeted blocks across July 30 and July 31) that match our rigid multi-wave fingerprints:
    *   Fee rate matching known attack waves (10.0, 30.0, 50.2, or 201.0 sat/vB)
    *   No change outputs (1 output only)
    *   Inputs from typical single-sig script types (BIP-84, BIP-49, BIP-44)

### Task 2: Trace the "API Fingerprint" & Earlier Test Runs
*   **Action**: Deeply analyze the known sweeps to extract the structural API fingerprint (e.g., `version`, `locktime`, `nSequence`, BIP69 sorting).
*   **Action**: Scan historical blocks (prior to 2026-07-30) for this exact fingerprint to identify the attacker's suspected test runs or earlier, undetected thefts (correlating with the ~695 earlier transactions reported by The Block).

### Task 3: Monitor Consolidation Addresses
*   **Action**: Continuously monitor the primary consolidation addresses for any outgoing transactions.
*   **Action**: Trace the flow of funds to subsequent hops, clustering by input patterns, derivation path usage, and any change behavior to identify potential off-ramps or mixing services.

### Task 4: Pipeline and Dashboard Upgrades
*   **Action**: Update our data pipeline to perform strict pattern matching based on the 30.0 sat/vB and no-change heuristics.
*   **Action**: Upgrade our analytics dashboard to score sweeps with a **Fingerprint Confidence** metric to filter out false positives and accurately track the total drained amount.
*   **Action**: Implement **Dynamic Heuristic Tracking**. Since the attacker is likely to adapt their strategy, we must build generalized alerts for rapid single-sig sweeps (e.g., with different fee rates or obfuscation patterns) and monitor the mempool for transactions matching the structural API fingerprint regardless of fee.

### Task 5: Frontend Dashboard Construction
*   **Action**: Construct a web-based analytics dashboard to visualize the data in `metrics.json`.
*   **Privacy-Preserving Address Checker**: Implement a client-side address verification tool. We will load a list of *hashed* (SHA-256) compromised addresses to the client, allowing users to locally hash their address and check for exposure without leaking their address to our servers.
*   **Aesthetics**: The UI should reflect the "bitcoin-data-labs" product suite style. It should employ a light theme (similar background color to the "this-week-in-bitcoin" repository) to differentiate from the typical dark themes, maintaining a clean, premium, and professional data-storytelling aesthetic.
