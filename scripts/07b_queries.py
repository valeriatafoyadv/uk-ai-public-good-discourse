#!/usr/bin/env python3
"""
Task 2: Generate count queries by genre and by gds_tier, and create HTML with charts.
"""

import csv
from pathlib import Path
from collections import defaultdict

# Configuration
DATA_DIR = Path(__file__).parent.parent / "data"
MANIFEST_FILE = DATA_DIR / "manifest.csv"
TERM_COUNTS_FILE = Path(__file__).parent.parent / "analysis" / "queries" / "term_counts.csv"
ANALYSIS_DIR = Path(__file__).parent.parent / "analysis" / "queries"
OUTPUT_CSV_GENRE = ANALYSIS_DIR / "zero_count_by_genre.csv"
OUTPUT_CSV_TIER = ANALYSIS_DIR / "nominal_by_gdstier.csv"
AGENCY_CSV_FILE = ANALYSIS_DIR / "agency_by_genre.csv"
OUTPUT_HTML = ANALYSIS_DIR / "queries.html"

# Valid genres and tiers
GENRES = ['STRAT', 'MOU', 'PRGOV', 'PRCO', 'BLOG', 'WMS', 'REG']
TIERS = ['T1', 'T2', 'T3']
AGENCY_FORMS = ['explicit_agent', 'agentless_passive', 'nominalisation']

def load_manifest():
    """Load manifest as {doc_id: {columns}}."""
    docs = {}
    with open(MANIFEST_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            docs[row['doc_id']] = row
    return docs

def load_term_counts():
    """Load term_counts as {doc_id: {n_nominal, n_variant, n_distributive}}."""
    counts = {}
    with open(TERM_COUNTS_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts[row['doc_id']] = {
                'n_nominal': int(row['n_nominal']) if row['n_nominal'] else 0,
                'n_variant': int(row['n_variant']) if row['n_variant'] else 0,
                'n_distributive': int(row['n_distributive']) if row['n_distributive'] else 0,
            }
    return counts

def load_agency_data():
    """Load analysis/queries/agency_by_genre.csv, produced by
    scripts/11_agency_query.py. Returns (agency_data, partial_note) where
    agency_data is {genre: {form: count}} or None if the query hasn't been
    run yet, and partial_note is the text of a leading '# STATUS: PARTIAL...'
    comment line in that CSV, or None when the query is corpus-complete."""
    if not AGENCY_CSV_FILE.exists():
        return None, None
    with open(AGENCY_CSV_FILE, encoding='utf-8') as f:
        lines = f.readlines()
    partial_note = None
    data_lines = lines
    if lines and lines[0].lstrip().startswith('#'):
        partial_note = lines[0].lstrip('#').strip()
        data_lines = lines[1:]
    reader = csv.DictReader(data_lines)
    agency_data = defaultdict(lambda: {f: 0 for f in AGENCY_FORMS})
    for row in reader:
        genre = row.get('genre', '')
        for form in AGENCY_FORMS:
            agency_data[genre][form] = int(row.get(form) or 0)
    return dict(agency_data), partial_note


def process_by_genre(manifest, term_counts):
    """Process counts by genre."""
    genre_data = defaultdict(lambda: {
        'docs_present': 0,
        'docs_variant': 0,
        'docs_absent': 0,
        'total_nominal': 0,
        'total_variant': 0
    })

    for doc_id, row in manifest.items():
        genre = row.get('genre', '')
        if genre not in GENRES:
            continue

        term_status = row.get('term_status', '')
        counts = term_counts.get(doc_id, {'n_nominal': 0, 'n_variant': 0})

        if term_status == 'present':
            genre_data[genre]['docs_present'] += 1
        elif term_status == 'variant':
            genre_data[genre]['docs_variant'] += 1
        elif term_status == 'absent':
            genre_data[genre]['docs_absent'] += 1

        genre_data[genre]['total_nominal'] += counts['n_nominal']
        genre_data[genre]['total_variant'] += counts['n_variant']

    return dict(genre_data)

def process_by_tier(manifest, term_counts):
    """Process counts by gds_tier."""
    tier_data = defaultdict(lambda: {
        'docs_present': 0,
        'docs_variant': 0,
        'docs_absent': 0,
        'total_nominal': 0,
        'total_variant': 0
    })

    for doc_id, row in manifest.items():
        tier = row.get('gds_tier', '')
        if tier not in TIERS:
            continue

        term_status = row.get('term_status', '')
        counts = term_counts.get(doc_id, {'n_nominal': 0, 'n_variant': 0})

        if term_status == 'present':
            tier_data[tier]['docs_present'] += 1
        elif term_status == 'variant':
            tier_data[tier]['docs_variant'] += 1
        elif term_status == 'absent':
            tier_data[tier]['docs_absent'] += 1

        tier_data[tier]['total_nominal'] += counts['n_nominal']
        tier_data[tier]['total_variant'] += counts['n_variant']

    return dict(tier_data)

def write_genre_csv(genre_data):
    """Write CSV of counts by genre."""
    with open(OUTPUT_CSV_GENRE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'genre', 'docs_present', 'docs_variant', 'docs_absent', 'total_nominal_mentions', 'total_variant_mentions'
        ])
        writer.writeheader()
        for genre in GENRES:
            if genre in genre_data:
                data = genre_data[genre]
                writer.writerow({
                    'genre': genre,
                    'docs_present': data['docs_present'],
                    'docs_variant': data['docs_variant'],
                    'docs_absent': data['docs_absent'],
                    'total_nominal_mentions': data['total_nominal'],
                    'total_variant_mentions': data['total_variant']
                })
            else:
                writer.writerow({
                    'genre': genre,
                    'docs_present': 0,
                    'docs_variant': 0,
                    'docs_absent': 0,
                    'total_nominal_mentions': 0,
                    'total_variant_mentions': 0
                })

def write_tier_csv(tier_data):
    """Write CSV of counts by tier with a footnote."""
    with open(OUTPUT_CSV_TIER, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'gds_tier', 'docs_present', 'docs_variant', 'docs_absent', 'total_nominal_mentions', 'total_variant_mentions'
        ])
        writer.writeheader()
        for tier in TIERS:
            if tier in tier_data:
                data = tier_data[tier]
                writer.writerow({
                    'gds_tier': tier,
                    'docs_present': data['docs_present'],
                    'docs_variant': data['docs_variant'],
                    'docs_absent': data['docs_absent'],
                    'total_nominal_mentions': data['total_nominal'],
                    'total_variant_mentions': data['total_variant']
                })
            else:
                writer.writerow({
                    'gds_tier': tier,
                    'docs_present': 0,
                    'docs_variant': 0,
                    'docs_absent': 0,
                    'total_nominal_mentions': 0,
                    'total_variant_mentions': 0
                })
        # Footnote
        f.write("# gds_tier auto-assigned, provisional\n")

def generate_html(genre_data, tier_data, agency_data=None, agency_note=None):
    """Generate HTML with the three NVivo-plan-query SVG charts."""

    # Prepare data for charts
    genre_labels = GENRES
    genre_present = [genre_data.get(g, {}).get('docs_present', 0) for g in genre_labels]
    genre_variant = [genre_data.get(g, {}).get('docs_variant', 0) for g in genre_labels]
    genre_absent = [genre_data.get(g, {}).get('docs_absent', 0) for g in genre_labels]

    tier_labels = TIERS
    tier_present = [tier_data.get(t, {}).get('docs_present', 0) for t in tier_labels]
    tier_variant = [tier_data.get(t, {}).get('docs_variant', 0) for t in tier_labels]
    tier_absent = [tier_data.get(t, {}).get('docs_absent', 0) for t in tier_labels]

    # Generate SVG charts
    genre_svg = generate_bar_chart("Zero count x genre (term status per document)", genre_labels, genre_present, genre_variant, genre_absent)
    tier_svg = generate_bar_chart("Nominal term x GDS tier (provisional)", tier_labels, tier_present, tier_variant, tier_absent)

    agency_svg = None
    if agency_data is not None:
        agency_explicit = [agency_data.get(g, {}).get('explicit_agent', 0) for g in genre_labels]
        agency_passive = [agency_data.get(g, {}).get('agentless_passive', 0) for g in genre_labels]
        agency_nominal = [agency_data.get(g, {}).get('nominalisation', 0) for g in genre_labels]
        agency_svg = generate_bar_chart("Agency x genre (instance counts)", genre_labels,
                                         agency_explicit, agency_passive, agency_nominal)

    # HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Term queries — public good</title>
    <style>
        :root {{
            --bg-primary: #ffffff;
            --bg-secondary: #ffffff;
            --surface-soft: #f7f7f7;
            --surface-strong: #eef0f3;
            --text-primary: #0a0b0d;
            --text-secondary: #5b616e;
            --text-muted: #7c828a;
            --border-color: #dee1e6;
            --color-present: #0052ff;
            --color-variant: #a87700;
            --color-absent: #048f56;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: system-ui, -apple-system, sans-serif;
            padding: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        h1 {{
            margin-bottom: 1rem;
            font-size: 1.5rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        .note {{
            background-color: var(--surface-soft);
            border-left: 4px solid var(--color-present);
            padding: 1rem;
            margin-bottom: 2rem;
            color: var(--text-secondary);
            font-size: 0.875rem;
            border-radius: 0 8px 8px 0;
        }}

        .chart-section {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 3rem;
        }}

        .chart-section h2 {{
            margin-bottom: 1.5rem;
            font-size: 1.125rem;
            color: var(--text-primary);
        }}

        .legend {{
            display: flex;
            gap: 2rem;
            margin-bottom: 2rem;
            font-size: 0.875rem;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 2px;
        }}

        .table-section {{
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 3rem;
            overflow-x: auto;
        }}

        .table-section h2 {{
            margin-bottom: 1rem;
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--text-primary);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }}

        th {{
            background-color: var(--surface-strong);
            color: var(--text-muted);
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
        }}

        td {{
            padding: 0.75rem;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
        }}

        tr:hover {{
            background-color: var(--surface-soft);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Term queries — &ldquo;public good&rdquo; across the corpus</h1>

        <div class="note">
            <strong>Note:</strong> {(
                "Agency x genre query: pending Round 1 coding (run scripts/11_agency_query.py once "
                "coding/round1/*.jsonl has AGENCY records)."
            ) if agency_data is None else (
                f"Agency x genre query: <strong>{agency_note}</strong> See the third chart below."
            ) if agency_note else (
                "Agency x genre query: complete for the full corpus. See the third chart below."
            )}
        </div>

        <div class="chart-section">
            <h2>Zero count &times; genre</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-present);"></div>
                    <span>Present</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-variant);"></div>
                    <span>Variant</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-absent);"></div>
                    <span>Absent</span>
                </div>
            </div>
            {genre_svg}
        </div>

        <div class="table-section">
            <h2>Genre Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>Genre</th>
                        <th>Docs Present</th>
                        <th>Docs Variant</th>
                        <th>Docs Absent</th>
                        <th>Total Nominal</th>
                        <th>Total Variant</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add genre rows
    for genre in GENRES:
        data = genre_data.get(genre, {
            'docs_present': 0,
            'docs_variant': 0,
            'docs_absent': 0,
            'total_nominal': 0,
            'total_variant': 0
        })
        html += f"""                    <tr>
                        <td><strong>{genre}</strong></td>
                        <td>{data['docs_present']}</td>
                        <td>{data['docs_variant']}</td>
                        <td>{data['docs_absent']}</td>
                        <td>{data['total_nominal']}</td>
                        <td>{data['total_variant']}</td>
                    </tr>
"""

    html += f"""                </tbody>
            </table>
        </div>

        <div class="chart-section">
            <h2>Nominal term &times; GDS tier (provisional)</h2>
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-present);"></div>
                    <span>Present</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-variant);"></div>
                    <span>Variant</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-absent);"></div>
                    <span>Absent</span>
                </div>
            </div>
            {tier_svg}
        </div>

        <div class="table-section">
            <h2>GDS Tier Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>GDS Tier</th>
                        <th>Docs Present</th>
                        <th>Docs Variant</th>
                        <th>Docs Absent</th>
                        <th>Total Nominal</th>
                        <th>Total Variant</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add tier rows
    for tier in TIERS:
        data = tier_data.get(tier, {
            'docs_present': 0,
            'docs_variant': 0,
            'docs_absent': 0,
            'total_nominal': 0,
            'total_variant': 0
        })
        html += f"""                    <tr>
                        <td><strong>{tier}</strong></td>
                        <td>{data['docs_present']}</td>
                        <td>{data['docs_variant']}</td>
                        <td>{data['docs_absent']}</td>
                        <td>{data['total_nominal']}</td>
                        <td>{data['total_variant']}</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>
"""

    if agency_svg is not None:
        partial_html = (
            f'<div class="note"><strong>Note:</strong> {agency_note}</div>'
            if agency_note else ""
        )
        html += f"""
        <div class="chart-section">
            <h2>Agency &times; genre</h2>
            {partial_html}
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-present);"></div>
                    <span>Explicit agent</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-variant);"></div>
                    <span>Agentless passive</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: var(--color-absent);"></div>
                    <span>Nominalisation</span>
                </div>
            </div>
            {agency_svg}
        </div>

        <div class="table-section">
            <h2>Agency Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>Genre</th>
                        <th>Explicit Agent</th>
                        <th>Agentless Passive</th>
                        <th>Nominalisation</th>
                    </tr>
                </thead>
                <tbody>
"""
        for genre in GENRES:
            data = agency_data.get(genre, {f: 0 for f in AGENCY_FORMS})
            html += f"""                    <tr>
                        <td><strong>{genre}</strong></td>
                        <td>{data.get('explicit_agent', 0)}</td>
                        <td>{data.get('agentless_passive', 0)}</td>
                        <td>{data.get('nominalisation', 0)}</td>
                    </tr>
"""
        html += """                </tbody>
            </table>
        </div>
"""

    html += """    </div>
</body>
</html>
"""

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

def generate_bar_chart(title, categories, present, variant, absent):
    """Genera un chart SVG de barras agrupadas."""
    num_categories = len(categories)
    bar_width = 20
    group_gap = 10
    group_pad = 28
    group_width = bar_width * 3 + group_gap * 2 + group_pad
    margin_left = 60
    margin_right = 40
    margin_top = 40
    margin_bottom = 60
    chart_width = margin_left + num_categories * group_width + margin_right
    chart_height = 400

    # Scale
    max_value = max(max(present), max(variant), max(absent))
    if max_value == 0:
        max_value = 1
    scale = (chart_height - margin_top - margin_bottom) / max_value

    svg = f'<svg viewBox="0 0 {chart_width} {chart_height}" xmlns="http://www.w3.org/2000/svg">\n'

    # Background
    svg += f'  <rect width="{chart_width}" height="{chart_height}" fill="var(--bg-secondary)"/>\n'

    # Y axis
    svg += f'  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{chart_height - margin_bottom}" stroke="var(--border-color)" stroke-width="1"/>\n'

    # X axis
    svg += f'  <line x1="{margin_left}" y1="{chart_height - margin_bottom}" x2="{chart_width - margin_right}" y2="{chart_height - margin_bottom}" stroke="var(--border-color)" stroke-width="1"/>\n'

    # Grid and Y labels
    for i in range(0, int(max_value) + 2):
        y = chart_height - margin_bottom - i * scale
        if i > 0:
            svg += f'  <line x1="{margin_left}" y1="{y}" x2="{chart_width - margin_right}" y2="{y}" stroke="var(--border-color)" stroke-width="0.5" opacity="0.3"/>\n'
        svg += f'  <text x="{margin_left - 10}" y="{y + 4}" text-anchor="end" font-size="12" fill="var(--text-secondary)">{i}</text>\n'

    # Bars and X labels
    for idx, category in enumerate(categories):
        x_base = margin_left + idx * group_width + group_pad / 2

        # Present bar
        height_present = present[idx] * scale
        svg += f'  <rect x="{x_base}" y="{chart_height - margin_bottom - height_present}" width="{bar_width}" height="{height_present}" fill="var(--color-present)" rx="4" ry="4"/>\n'
        if present[idx] > 0:
            svg += f'  <text x="{x_base + bar_width/2}" y="{chart_height - margin_bottom - height_present - 5}" text-anchor="middle" font-size="11" fill="var(--text-primary)">{present[idx]}</text>\n'

        # Variant bar
        x_variant = x_base + bar_width + group_gap
        height_variant = variant[idx] * scale
        svg += f'  <rect x="{x_variant}" y="{chart_height - margin_bottom - height_variant}" width="{bar_width}" height="{height_variant}" fill="var(--color-variant)" rx="4" ry="4"/>\n'
        if variant[idx] > 0:
            svg += f'  <text x="{x_variant + bar_width/2}" y="{chart_height - margin_bottom - height_variant - 5}" text-anchor="middle" font-size="11" fill="var(--text-primary)">{variant[idx]}</text>\n'

        # Absent bar
        x_absent = x_variant + bar_width + group_gap
        height_absent = absent[idx] * scale
        svg += f'  <rect x="{x_absent}" y="{chart_height - margin_bottom - height_absent}" width="{bar_width}" height="{height_absent}" fill="var(--color-absent)" rx="4" ry="4"/>\n'
        if absent[idx] > 0:
            svg += f'  <text x="{x_absent + bar_width/2}" y="{chart_height - margin_bottom - height_absent - 5}" text-anchor="middle" font-size="11" fill="var(--text-primary)">{absent[idx]}</text>\n'

        # X label
        x_label = x_base + (bar_width * 3 + group_gap * 2) / 2
        svg += f'  <text x="{x_label}" y="{chart_height - margin_bottom + 20}" text-anchor="middle" font-size="12" fill="var(--text-secondary)">{category}</text>\n'

    svg += '</svg>\n'
    return svg

if __name__ == '__main__':
    manifest = load_manifest()
    term_counts = load_term_counts()
    agency_data, agency_note = load_agency_data()

    genre_data = process_by_genre(manifest, term_counts)
    tier_data = process_by_tier(manifest, term_counts)

    write_genre_csv(genre_data)
    write_tier_csv(tier_data)
    generate_html(genre_data, tier_data, agency_data, agency_note)

    print(f"Genre CSV: {OUTPUT_CSV_GENRE}")
    print(f"Tier CSV: {OUTPUT_CSV_TIER}")
    if agency_data is not None:
        status = agency_note if agency_note else "complete"
        print(f"Agency CSV: {AGENCY_CSV_FILE} ({status})")
    else:
        print("Agency CSV: not found -- run scripts/11_agency_query.py first")
    print(f"HTML: {OUTPUT_HTML}")
