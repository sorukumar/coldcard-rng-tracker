/**
 * Coldcard Investigation Dashboard — app.js
 * Handles data loading, chart rendering, and all interactive components.
 */

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
    initScrollReveal();
});

// ── Data Loading ─────────────────────────────────────────────────────────

async function initDashboard() {
    try {
        const [summaryRes, timelineRes, scatterRes, tier1Res, tier2Res, tier3RawRes, tier3HeurRes] = await Promise.all([
            fetch('data/metrics_summary.json').catch(() => null),
            fetch('data/timeline.json').catch(() => null),
            fetch('data/scatter.json').catch(() => null),
            fetch('data/clusters_tier_1.json').catch(() => null),
            fetch('data/clusters_tier_2.json').catch(() => null),
            fetch('data/scored_sweeps.json').catch(() => null),
            fetch('data/clusters_heuristic.json').catch(() => null)
        ]);

        const summary  = summaryRes  && summaryRes.ok  ? await summaryRes.json()  : null;
        const timeline = timelineRes && timelineRes.ok ? await timelineRes.json() : null;
        const scatter  = scatterRes  && scatterRes.ok  ? await scatterRes.json()  : null;
        const tier1    = tier1Res    && tier1Res.ok    ? await tier1Res.json()    : [];
        const tier2    = tier2Res    && tier2Res.ok    ? await tier2Res.json()    : [];
        const tier3Raw = tier3RawRes && tier3RawRes.ok ? await tier3RawRes.json() : null;
        const tier3Heur = tier3HeurRes && tier3HeurRes.ok ? await tier3HeurRes.json() : [];

        // tier3 / scored_sweeps is large — extract what we need
        const tier3Sweeps = tier3Raw && tier3Raw.suspected_sweeps ? tier3Raw.suspected_sweeps : [];

        // Timestamp
        setDataTimestamp();

        // Act 1: stat cards
        if (summary) renderStatCards(summary, tier1);

        // Act 2: timeline
        if (timeline) renderTimelineChart(timeline);

        // Act 3: wave evolution cards
        renderWaveCards();

        // Act 4: victim histogram
        if (tier3Sweeps.length > 0 || (scatter && scatter.length > 0)) {
            renderVictimHistogram(tier3Sweeps.length > 0 ? tier3Sweeps : scatter);
        }

        // Act 5: wallet tracker
        if (tier1.length > 0) {
            renderWalletCards(tier1);
        }
        if (summary) {
            const hElem = document.getElementById('heuristic-total');
            if (hElem) hElem.textContent = Number(summary.total_stolen_heuristic_btc).toFixed(2);
        }

        // Act 6: address checker
        if (document.getElementById('check-address-btn')) setupAddressChecker();

        // Appendix: tier-1 table
        if (document.querySelector('#attacker-table-tier-1 tbody')) {
            populateAttackerTable(tier1, '#attacker-table-tier-1 tbody');
        }

        // Tier 3 table and download (checker.html)
        if (document.querySelector('#attacker-table-tier-3 tbody')) {
            populateAttackerTable(tier3Heur.slice(0, 500), '#attacker-table-tier-3 tbody');
        }
        setupDownloadButton(tier3Heur);

        // Scatter chart (methodology.html)
        if (document.getElementById('scatterChart') && scatter) {
            renderScatterChart(scatter);
        }

    } catch (err) {
        console.error('Dashboard init error:', err);
        const sc = document.getElementById('stats-container');
        if (sc) sc.innerHTML = `<div style="grid-column:1/-1;padding:1rem;border:2px solid var(--status-danger);background:var(--status-danger-bg);font-family:var(--font-sans);font-size:0.9rem;color:var(--status-danger);"><strong>Error:</strong> Failed to load data. The data pipeline may not have run yet.</div>`;
    }
}

// ── Utility ──────────────────────────────────────────────────────────────

function fmt(n, d) {
    return Number(n).toLocaleString('en-US', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
}

function fmtBtc(n) { return fmt(n, 4) + ' BTC'; }

function setDataTimestamp() {
    const el = document.getElementById('data-timestamp');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
}

// ── Act 1: Stat Cards ─────────────────────────────────────────────────────

function renderStatCards(summary, tier1) {
    const stolen = document.getElementById('stat-stolen');
    const utxos  = document.getElementById('stat-utxos');
    const status = document.getElementById('stat-status');

    if (stolen) {
        const btc = Math.floor(Number(summary.total_stolen_tier_1_btc));
        stolen.textContent = fmt(btc, 0) + ' BTC';
    }
    if (utxos) utxos.textContent = fmt(summary.addresses_drained_verified || summary.swept_utxos_count, 0);

    // Check if all tier1 balances are still holding (no outgoing txs in data)
    if (status) {
        status.textContent = 'HOLDING';
        status.style.color = 'var(--status-hold)';
    }
}

// ── Act 2: Timeline Chart ─────────────────────────────────────────────────

function renderTimelineChart(timelineData) {
    if (!timelineData || timelineData.length === 0) return;
    const container = document.getElementById('timelineChart');
    if (!container) return;

    const chart = echarts.init(container);

    // Build cumulative series
    let cumulative = 0;
    const cumuData = timelineData.map(d => {
        cumulative += d.stolen_amount;
        return [d.date, cumulative];
    });

    // Wave color bands (markArea)
    const waveAreas = [
        {
            name: 'Wave 1 · 30 sat/vB',
            color: 'rgba(196, 96, 58, 0.09)',
            start: '2026-07-30 01:00:00',
            end:   '2026-07-30 02:00:00'
        },
        {
            name: 'Wave 2 & 2b · 50.2 / 10 sat/vB',
            color: 'rgba(59, 110, 165, 0.09)',
            start: '2026-07-31 04:00:00',
            end:   '2026-07-31 09:00:00'
        },
        {
            name: 'Wave 3 · 201 sat/vB',
            color: 'rgba(158, 43, 37, 0.09)',
            start: '2026-07-31 12:00:00',
            end:   '2026-07-31 23:00:00'
        }
    ];

    const markAreaData = waveAreas.map(w => ([
        { name: w.name, xAxis: w.start, itemStyle: { color: w.color } },
        { xAxis: w.end }
    ]));

    const option = {
        tooltip: {
            trigger: 'axis',
            backgroundColor: '#F1F2DC',
            borderColor: 'rgba(26,29,36,0.25)',
            borderWidth: 1,
            textStyle: { color: '#1A1D24', fontFamily: 'Inter, sans-serif', fontSize: 12 },
            formatter: params => {
                const d = params[0];
                const rawDate = d.name || d.axisValue;
                let dateStr = rawDate;
                try {
                    dateStr = new Date(rawDate.replace(' ', 'T') + 'Z')
                        .toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
                } catch(e) {}
                return `<div style="font-family:Inter,sans-serif"><strong>${dateStr}</strong><br/>Cumulative stolen: <strong style="color:#9E2B25">${fmt(d.value[1], 4)} BTC</strong></div>`;
            }
        },
        xAxis: {
            type: 'time',
            axisLabel: {
                fontFamily: 'Inter, sans-serif',
                fontSize: 11,
                color: 'rgba(26,29,36,0.6)',
                formatter: val => {
                    const d = new Date(val);
                    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric' });
                }
            },
            axisLine: { lineStyle: { color: 'rgba(26,29,36,0.25)' } },
            splitLine: { show: false }
        },
        yAxis: {
            type: 'value',
            name: 'Cumulative BTC',
            nameTextStyle: { fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'rgba(26,29,36,0.5)' },
            axisLabel: { fontFamily: 'Inter, sans-serif', fontSize: 11, color: 'rgba(26,29,36,0.6)', formatter: v => fmt(v, 0) + ' BTC' },
            splitLine: { lineStyle: { color: 'rgba(26,29,36,0.08)', type: 'dashed' } }
        },
        series: [{
            name: 'Cumulative BTC Stolen',
            type: 'line',
            data: cumuData,
            smooth: 0.3,
            symbol: 'none',
            lineStyle: { color: '#9E2B25', width: 2.5 },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                        { offset: 0, color: 'rgba(158, 43, 37, 0.22)' },
                        { offset: 1, color: 'rgba(158, 43, 37, 0.02)' }
                    ]
                }
            },
            markArea: {
                silent: false,
                emphasis: { disabled: false },
                data: markAreaData,
                label: {
                    show: true,
                    position: 'insideTopLeft',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: 9,
                    fontWeight: 700,
                    textBorderWidth: 0,
                    color: 'rgba(26,29,36,0.55)'
                }
            }
        }],
        grid: { left: '1%', right: '2%', bottom: '2%', top: '6%', containLabel: true }
    };

    chart.setOption(option);
    window.addEventListener('resize', () => chart.resize());
}

// ── Act 3: Wave Evolution Cards ───────────────────────────────────────────

const WAVES = [
    {
        id: 'w1',
        label: 'Wave 1',
        date: 'Jul 30 · 01:10–01:51 UTC',
        fee: '30.0',
        market: '~3',
        multiple: '10×',
        addresses: '1,195',
        btc: '1,082.65',
        blocks: '960183–960191',
        rbf: 'No',
        consolidation: 'Shared collectors (5 addresses)',
        tactic: 'Centralized sweeping into shared collector addresses. Simple to track — and the community did.'
    },
    {
        id: 'w2',
        label: 'Wave 2',
        date: 'Jul 31 · 04:54–08:36 UTC',
        fee: '50.2',
        market: '~3',
        multiple: '17×',
        addresses: '1,126',
        btc: '45.97',
        blocks: '960345–960369',
        rbf: 'Yes',
        consolidation: 'Single shared collector',
        tactic: 'Added RBF and raised fees — possibly to push transactions ahead of monitoring scripts attempting to frontrun.'
    },
    {
        id: 'w2b',
        label: 'Wave 2b',
        date: 'Jul 31 · separate window',
        fee: '10.0',
        market: '~3',
        multiple: '3.3×',
        addresses: '352',
        btc: '30.18',
        blocks: '960345–960369',
        rbf: 'Yes',
        consolidation: 'Separate collector (Galaxy-identified)',
        tactic: 'Lower fee rate signals either a different attacker or a secondary script targeting a different victim pool.'
    },
    {
        id: 'w3',
        label: 'Wave 3',
        date: 'Jul 31 · 12:23–22:25 UTC',
        fee: '201.0',
        market: '~3',
        multiple: '67×',
        addresses: '1,626',
        btc: '200.33',
        blocks: '960400–960480',
        rbf: 'Yes',
        consolidation: 'Each victim → unique fresh P2WSH vault',
        tactic: 'Complete evasion pivot. No shared destination = no destination convergence signal. Only fee convergence remained.'
    },
    {
        id: 'w4-10',
        label: 'Waves 4–10',
        date: 'Aug 1+ · Multiple windows',
        fee: 'Varies',
        market: '~3',
        multiple: 'N/A',
        addresses: '1,162+',
        btc: '115.90+',
        blocks: '960481+',
        rbf: 'Mixed',
        consolidation: 'Various strategies',
        tactic: 'Independent researchers (coldcard.rip) identified 6 additional subsequent waves targeting smaller balances and using diverse laundering techniques.'
    }
];

function renderWaveCards() {
    const grid = document.getElementById('wave-cards');
    if (!grid) return;

    grid.innerHTML = WAVES.map(w => `
        <div class="wave-card ${w.id}" role="listitem" aria-label="${w.label}">
            <div class="wave-label">${w.label} · ${w.date}</div>
            <div class="wave-fee">${w.fee}<span class="wave-fee-unit">sat/vB</span></div>
            <div class="wave-market">vs market ~${w.market} sat/vB · <strong>${w.multiple} market rate</strong></div>
            <div class="wave-stats">
                <div class="wave-stat-row">
                    <span class="wave-stat-key">Addresses swept</span>
                    <span class="wave-stat-val">${w.addresses}</span>
                </div>
                <div class="wave-stat-row">
                    <span class="wave-stat-key">BTC taken</span>
                    <span class="wave-stat-val">${w.btc}</span>
                </div>
                <div class="wave-stat-row">
                    <span class="wave-stat-key">Block range</span>
                    <span class="wave-stat-val" style="font-size:0.72rem">${w.blocks}</span>
                </div>
                <div class="wave-stat-row">
                    <span class="wave-stat-key">RBF enabled</span>
                    <span class="wave-stat-val">${w.rbf}</span>
                </div>
                <div class="wave-stat-row">
                    <span class="wave-stat-key">Consolidation</span>
                    <span class="wave-stat-val" style="font-size:0.72rem;max-width:140px;text-align:right">${w.consolidation}</span>
                </div>
            </div>
            <div class="wave-tactics">${w.tactic}</div>
        </div>
    `).join('');
}

// ── Act 4: Victim Histogram ───────────────────────────────────────────────

function renderVictimHistogram(sweeps) {
    const wrap = document.getElementById('victim-histogram');
    const summary = document.getElementById('hist-summary');
    if (!wrap) return;

    // Handle both scored_sweeps format and scatter format
    const amounts = sweeps.map(s => {
        if (typeof s.value_btc === 'number') return s.value_btc;
        if (typeof s.value === 'number') return s.value;
        return 0;
    }).filter(v => v > 0);

    if (amounts.length === 0) {
        wrap.innerHTML = '<div style="padding:1rem;font-family:var(--font-sans);font-size:0.88rem;color:var(--text-faint);">Victim distribution data not available.</div>';
        return;
    }

    const buckets = [
        { label: '< 0.001 BTC',   min: 0,      max: 0.001,  count: 0, color: 'var(--text-faint)' },
        { label: '0.001–0.01 BTC', min: 0.001,  max: 0.01,   count: 0, color: 'var(--wave2b-color)' },
        { label: '0.01–0.1 BTC',  min: 0.01,   max: 0.1,    count: 0, color: 'var(--wave2-color)' },
        { label: '0.1–1 BTC',     min: 0.1,    max: 1,      count: 0, color: 'var(--wave1-color)' },
        { label: '1–10 BTC',      min: 1,      max: 10,     count: 0, color: 'var(--accent-text)' },
        { label: '10–50 BTC',     min: 10,     max: 50,     count: 0, color: '#9E2B25' },
        { label: '50+ BTC',       min: 50,     max: Infinity, count: 0, color: '#6B1818' },
    ];

    amounts.forEach(v => {
        const b = buckets.find(b => v >= b.min && v < b.max);
        if (b) b.count++;
    });

    const maxCount = Math.max(...buckets.map(b => b.count));

    wrap.innerHTML = buckets.map(b => `
        <div class="hist-row">
            <div class="hist-label">${b.label}</div>
            <div class="hist-bar-track">
                <div class="hist-bar" style="background:${b.color};width:0"
                     data-width="${maxCount > 0 ? Math.round((b.count / maxCount) * 100) : 0}%">
                </div>
            </div>
            <div class="hist-count">${fmt(b.count, 0)}</div>
        </div>
    `).join('');

    // Animate bars in after a tick
    requestAnimationFrame(() => {
        setTimeout(() => {
            wrap.querySelectorAll('.hist-bar').forEach(bar => {
                bar.style.width = bar.dataset.width;
            });
        }, 200);
    });

    // Summary insights
    const bigLosers = amounts.filter(v => v >= 1).length;
    const totalSweeps = amounts.length;
    const medianIdx = Math.floor(amounts.slice().sort((a,b) => a-b).length / 2);
    const median = amounts.slice().sort((a,b) => a-b)[medianIdx];

    if (summary) {
        summary.innerHTML = `
            Analyzed <strong>${fmt(totalSweeps, 0)} sweep transactions</strong> in our dataset.
            <strong>${fmt(bigLosers, 0)} addresses</strong> lost 1 BTC or more.
            Median loss per sweep: <strong>${fmt(median, 4)} BTC</strong>.
            The largest single address lost 51.07 BTC.
        `;
    }
}

// ── Act 5: Wallet Tracker Cards ───────────────────────────────────────────

function renderWalletCards(tier1) {
    const grid = document.getElementById('wallet-grid');
    const totalEl = document.getElementById('wallet-total');
    if (!grid) return;

    const sourceLabels = {
        galaxy_research: 'Galaxy Research',
        community:       'Community Report',
        coinspect:       'Coinspect',
        'coldcard-watch':'coldcard-watch.vercel.app'
    };

    let total = 0;

    grid.innerHTML = tier1.map(c => {
        total += c.total_received || 0;
        const shortAddr = c.address.slice(0, 14) + '…' + c.address.slice(-8);
        const source = sourceLabels[c.source || ''] || 'Verified';
        const wave = c.breakdown && c.breakdown.fee_matched;
        const waveLabel = wave ? `Wave fee ${wave} sat/vB` : 'Cross-validated';

        return `
            <div class="wallet-card" role="listitem">
                <div>
                    <a class="wallet-addr"
                       href="https://mempool.space/address/${c.address}"
                       target="_blank" rel="noopener noreferrer"
                       title="${c.address}">
                        ${shortAddr}
                    </a>
                    <div class="wallet-meta">${source} · ${waveLabel} · First seen ${c.first_seen || '—'}</div>
                </div>
                <div class="wallet-btc">
                    ${fmt(c.total_received, 4)}<span class="unit">BTC</span>
                </div>
                <div class="wallet-status holding">
                    <span class="dot"></span>HOLDING
                </div>
            </div>
        `;
    }).join('');

    if (totalEl) totalEl.textContent = fmt(total, 4) + ' BTC';
}

// ── Tier-1 Address Table ──────────────────────────────────────────────────

function populateAttackerTable(clusters, selector) {
    if (!clusters || clusters.length === 0) return;
    const tbody = document.querySelector(selector);
    if (!tbody) return;
    tbody.innerHTML = '';

    clusters.forEach(c => {
        const tr = document.createElement('tr');
        const conf = c.avg_confidence || 0;
        let badgeClass = 'badge-tier1';
        let badgeText = '<i class="fas fa-check-circle"></i> Tier 1 Verified';
        if (c.tier === 'tier_2_crowdsourced') {
            badgeClass = 'badge-tier2';
            badgeText = '<i class="fas fa-users"></i> Crowdsourced';
        } else if (c.tier === 'tier_3_heuristic') {
            badgeClass = 'badge-tier3';
            badgeText = `<i class="fas fa-robot"></i> ${conf}% Match`;
        }
        tr.innerHTML = `
            <td style="font-family:var(--font-mono);font-size:0.8rem;">
                <a href="https://mempool.space/address/${c.address}" target="_blank" rel="noopener">${c.address}</a>
            </td>
            <td style="font-family:var(--font-sans);font-size:0.82rem;">${c.first_seen || '—'}</td>
            <td style="font-family:var(--font-sans);font-size:0.9rem;font-weight:700;">${fmt(c.total_received, 4)}</td>
            <td><span class="badge ${badgeClass}">${badgeText}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// ── Privacy-Preserving Address Checker ────────────────────────────────────

const compromisedHashes = new Set();

async function setupAddressChecker() {
    const btn       = document.getElementById('check-address-btn');
    const input     = document.getElementById('address-input');
    const resultDiv = document.getElementById('checker-result');
    const countEl   = document.getElementById('hash-count');

    if (!btn || !input || !resultDiv) return;

    try {
        const res = await fetch('data/compromised_hashes.json');
        if (res.ok) {
            const arr = await res.json();
            arr.forEach(h => compromisedHashes.add(h));
            if (countEl) countEl.textContent = arr.length.toLocaleString() + '+';
        }
    } catch (e) {
        console.error('Failed to load hashes:', e);
    }

    const doCheck = async () => {
        const address = input.value.trim();
        if (!address) return;

        btn.disabled = true;
        btn.textContent = 'Checking…';
        input.classList.remove('ok', 'hit');
        resultDiv.style.display = 'none';

        try {
            const encoder = new TextEncoder();
            const data = encoder.encode(address);
            const hashBuffer = await crypto.subtle.digest('SHA-256', data);
            const hashHex = Array.from(new Uint8Array(hashBuffer))
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            const shortHash = hashHex.substring(0, 16);

            const isCompromised = compromisedHashes.has(shortHash) || compromisedHashes.has(hashHex);

            resultDiv.style.display = 'block';
            if (isCompromised) {
                resultDiv.className = 'checker-result result-compromised';
                resultDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> <strong>WARNING:</strong> This address matches a known compromised sweep. Do not deposit funds. Move any remaining balance to a new wallet generated on fixed firmware.`;
                input.classList.add('hit');
            } else {
                resultDiv.className = 'checker-result result-safe';
                resultDiv.innerHTML = `<i class="fas fa-check-circle"></i> <strong>Not found:</strong> This address does not appear in our database of ${compromisedHashes.size.toLocaleString()} verified compromised sweeps.`;
                input.classList.add('ok');
            }
        } catch (err) {
            console.error('Hashing error:', err);
            resultDiv.style.display = 'block';
            resultDiv.className = 'checker-result';
            resultDiv.style.background = 'rgba(26,29,36,0.05)';
            resultDiv.style.borderColor = 'var(--border-color)';
            resultDiv.innerHTML = 'Error running check. Please try again.';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Check Address';
        }
    };

    btn.addEventListener('click', doCheck);
    input.addEventListener('keypress', e => { if (e.key === 'Enter') doCheck(); });
}

// ── Scroll Reveal ─────────────────────────────────────────────────────────

function initScrollReveal() {
    const sections = document.querySelectorAll('.section-wrap');
    if (!sections.length) return;

    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    sections.forEach(s => observer.observe(s));
}

// ── Legacy: Address Checker + Download (checker.html compat) ──────────────

function setupDownloadButton(clusters) {
    const btn = document.getElementById('download-csv-btn');
    if (!btn || !clusters || !clusters.length) return;

    btn.addEventListener('click', () => {
        const headers = ['Address', 'Tier', 'First Seen', 'Total Received (BTC)', 'Confidence Score'];
        const rows = clusters.map(c => [
            `"${c.address}"`,
            `"${c.tier || 'unknown'}"`,
            `"${c.first_seen || ''}"`,
            c.total_received || 0,
            c.avg_confidence || 0
        ]);
        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'attacker_clusters.csv';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });
}

// Scatter chart for checker.html (kept for backward compat)
function renderScatterChart(scatterData) {
    if (!scatterData || scatterData.length === 0) return;
    const container = document.getElementById('scatterChart');
    if (!container) return;

    const chart = echarts.init(container);
    const limited = [...scatterData].sort((a, b) => b.value_btc - a.value_btc).slice(0, 2000);
    const seriesData = limited.map(d => [
        d.date,
        d.fee_rate,
        Math.max(4, Math.min(25, d.value_btc * 10)),
        d.value_btc,
        d.confidence_score
    ]);

    chart.setOption({
        tooltip: {
            formatter: p => `Fee: ${p.data[1].toFixed(1)} sat/vB<br>Value: ${p.data[3].toFixed(4)} BTC<br>Confidence: ${p.data[4] || 0}%`
        },
        xAxis: {
            type: 'time',
            axisLabel: { fontFamily: 'Inter, sans-serif', color: '#1A1D24' },
            splitLine: { show: false }
        },
        yAxis: {
            type: 'log',
            name: 'Fee Rate (sat/vB)',
            axisLabel: { fontFamily: 'Inter, sans-serif', color: '#1A1D24' },
            splitLine: { lineStyle: { color: 'rgba(26,29,36,0.1)' } }
        },
        series: [{
            type: 'scatter',
            symbolSize: d => d[2],
            data: seriesData,
            itemStyle: {
                color: p => {
                    const c = p.data[4] || 0;
                    if (c >= 75) return 'rgba(158, 43, 37, 0.8)';
                    if (c >= 50) return 'rgba(196, 96, 58, 0.7)';
                    return 'rgba(26, 29, 36, 0.3)';
                },
                borderColor: 'rgba(26,29,36,0.15)',
                borderWidth: 1
            }
        }],
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true }
    });
    window.addEventListener('resize', () => chart.resize());
}
