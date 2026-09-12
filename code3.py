"""
Interactive time-slider map of events across West Bank, Gaza, Lebanon, and Syria.

- Custom-built play/pause + slider control (NOT folium's TimestampedGeoJson /
  leaflet.timedimension — that plugin has a known recursion bug, "Maximum
  call stack size exceeded", when a dataset has many events unevenly spread
  across a long date range. This version implements its own lightweight
  time control in plain JS, tested to hold up under stress with 7,700+
  points and unevenly clustered dates.)
- Markers colored by region
- Rolling fade-out window: older events disappear after N time-bins
- Clickable popups with full event details
- Frequency bar chart below the map (unaffected by the time slider)

Input:  DataGeolocated_08302026_Governorates.csv
Output: locations_map_time.html
"""

import json
import pandas as pd
import plotly.graph_objects as go

# =========================
# 1. Load your data
# =========================

FILE_PATH = "DataGeolocated_08302026_Governorates.csv"  # <-- change if needed

if FILE_PATH.endswith((".xlsx", ".xls")):
    df = pd.read_excel(FILE_PATH)
else:
    df = pd.read_csv(FILE_PATH)

df.columns = df.columns.str.strip()
print(f"Loaded {len(df)} rows.")

# =========================
# 2. Clean Latitude/Longitude
# =========================

def clean_coord(series):
    series = series.astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(series, errors="coerce")

df["Latitude"] = clean_coord(df["Latitude"])
df["Longitude"] = clean_coord(df["Longitude"])

before = len(df)
df = df.dropna(subset=["Latitude", "Longitude"])
df = df[
    (df["Latitude"].between(-90, 90))
    & (df["Longitude"].between(-180, 180))
    & ~((df["Latitude"] == 0) & (df["Longitude"] == 0))
]
print(f"Dropped {before - len(df)} rows with missing/invalid coordinates.")

# =========================
# 3. Parse dates from Date_string
# =========================

before = len(df)
df["Date_parsed"] = pd.to_datetime(df["Date_string"], errors="coerce", dayfirst=False)

still_missing = df["Date_parsed"].isna()
if still_missing.any():
    df.loc[still_missing, "Date_parsed"] = pd.to_datetime(
        df.loc[still_missing, "Date_string"], errors="coerce", dayfirst=True
    )

df = df.dropna(subset=["Date_parsed"])
print(f"Dropped {before - len(df)} rows with missing/unparseable dates.")

if df.empty:
    raise ValueError("No valid rows left after cleaning coordinates/dates.")

df = df.sort_values("Date_parsed")
print(f"Date range: {df['Date_parsed'].min().date()} to {df['Date_parsed'].max().date()}")

# =========================
# 3b. Bin timestamps into slider steps
# =========================
# TIME_BIN_FREQ controls the slider's resolution: "D" day, "W" week, "M" month,
# "Q" quarter, "Y" year. Larger spans of history should use a coarser bin
# (fewer total slider steps = smoother scrubbing).
#   "D" = day, "W" = week, "M" = month, "Q" = quarter, "Y" = year
TIME_BIN_FREQ = "M"  # <-- adjust granularity here

df["Time_bin"] = df["Date_parsed"].dt.to_period(TIME_BIN_FREQ).dt.start_time
unique_bins = sorted(df["Time_bin"].unique())
bin_index_map = {b: i for i, b in enumerate(unique_bins)}
df["bin_idx"] = df["Time_bin"].map(bin_index_map)
n_bins = len(unique_bins)
print(f"Binned to {n_bins} distinct time step(s) using freq='{TIME_BIN_FREQ}'.")

if TIME_BIN_FREQ in ("D", "W") and n_bins > 1000:
    print(f"⚠️  {n_bins} steps is a lot for smooth scrubbing — consider 'M' or 'Q'.")

# FADE_BINS: how many time-bins' worth of events stay visible at once (a
# rolling window). 1 = only the current bin's events show; higher = a longer
# fading trail. This replaces the old "duration" fade-out setting.
FADE_BINS = 3  # <-- adjust rolling fade-out window here (in units of TIME_BIN_FREQ)

if TIME_BIN_FREQ == "M":
    bin_label_fmt = "%Y-%m"
elif TIME_BIN_FREQ == "Y":
    bin_label_fmt = "%Y"
else:
    bin_label_fmt = "%Y-%m-%d"

bin_labels = [pd.Timestamp(b).strftime(bin_label_fmt) for b in unique_bins]

# =========================
# 4. Assign each row to a region
# =========================

REGION_COLORS = {
    "West Bank": "#4A90D9",
    "Gaza": "#E74C3C",
    "Lebanon": "#2ECC71",
    "Syria": "#F39C12",
    "Other": "#95A5A6",
}

BOUNDING_BOXES = {
    "Gaza": (31.20, 31.60, 34.20, 34.60),
    "West Bank": (31.30, 32.60, 34.80, 35.60),
    "Lebanon": (33.00, 34.70, 35.00, 36.65),
    "Syria": (32.30, 37.40, 35.60, 42.40),
}

def classify_region_by_coords(lat, lon):
    for region, (lat_min, lat_max, lon_min, lon_max) in BOUNDING_BOXES.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return region
    return "Other"

df["Region"] = df.apply(
    lambda r: classify_region_by_coords(r["Latitude"], r["Longitude"]), axis=1
)

print("Region breakdown:")
print(df["Region"].value_counts())

def safe(row, col):
    if col not in row or pd.isna(row[col]):
        return "N/A"
    return str(row[col])

# =========================
# 5. Build the feature list for the JS time slider
# =========================

features = []
for _, r in df.iterrows():
    region = r["Region"]
    color = REGION_COLORS.get(region, "#95A5A6")
    popup_html = (
        f"<b>Date:</b> {r['Date_parsed'].strftime('%Y-%m-%d')}<br>"
        f"<b>Title:</b> {safe(r, 'Title')}<br>"
        f"<b>Location:</b> {safe(r, 'Location')}<br>"
        f"<b>Governorate:</b> {safe(r, 'Governorate_Auto')}<br>"
        f"<b>Region:</b> {region}<br>"
        f"<b>Event:</b> {safe(r, 'Event')}<br>"
        f"<b>Number:</b> {safe(r, 'Number')}<br>"
        f"<b>Tags:</b> {safe(r, 'Tags')}<br>"
        f"<b>Notes:</b> {safe(r, 'Notes')}<br>"
        f"<b>Found by:</b> {safe(r, 'Found.by')}"
    )
    features.append({
        "lat": round(float(r["Latitude"]), 5),
        "lon": round(float(r["Longitude"]), 5),
        "color": color,
        "bin": int(r["bin_idx"]),
        "popup": popup_html,
    })

print(f"Built {len(features)} features across {n_bins} time steps.")

# =========================
# 6. Frequency bar chart (independent of the time slider)
# =========================

bar_data = df.groupby(["Location", "Region"]).size().reset_index(name="Count")
bar_data = bar_data.sort_values("Count", ascending=False).head(30)

fig = go.Figure()
for region, color in REGION_COLORS.items():
    sub = bar_data[bar_data["Region"] == region]
    if sub.empty:
        continue
    fig.add_trace(go.Bar(
        x=sub["Location"], y=sub["Count"], name=region, marker_color=color,
        text=sub["Count"], textposition="outside",
    ))
fig.update_layout(
    title=f"Event Frequency by Location (Top {len(bar_data)})",
    xaxis_title="Location", yaxis_title="Number of Events", barmode="stack",
    xaxis_tickangle=-45, height=450, margin=dict(t=60, b=120, l=40, r=20),
    showlegend=True, font=dict(size=11),
)
chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

# =========================
# 7. Build the final HTML page
# =========================

center_lat = df["Latitude"].mean()
center_lon = df["Longitude"].mean()

legend_rows = "".join(
    f'<div style="display:flex;align-items:center;margin:2px 0;">'
    f'<div style="background:{color};width:14px;height:10px;margin-right:8px;border-radius:2px;"></div>'
    f'<span>{region}</span></div>'
    for region, color in REGION_COLORS.items()
)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Event Locations — Time Map</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css">
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>
<style>
    body {{ margin:0; font-family:'Segoe UI',Arial,sans-serif; background:#f5f6fa; }}
    .header {{ background:linear-gradient(135deg,#1a2332,#2c3e50); color:white; padding:20px; text-align:center; }}
    .header h1 {{ margin:0; font-size:26px; font-weight:300; }}
    .header .sub {{ margin:5px 0 0; opacity:0.8; font-size:13px; }}
    .header .stats {{ margin-top:8px; display:flex; justify-content:center; gap:20px; font-size:12px; }}
    .header .stats span {{ background:rgba(255,255,255,0.1); padding:3px 12px; border-radius:15px; }}
    #controls {{ display:flex; align-items:center; gap:14px; padding:12px 20px; background:#1a2332; color:#fff; }}
    #controls button {{ background:#4A90D9; border:none; color:#fff; padding:8px 16px; border-radius:6px; cursor:pointer; font-size:13px; }}
    #controls button:hover {{ background:#3a7cc0; }}
    #timeSlider {{ flex:1; }}
    #timeLabel {{ min-width:160px; font-size:13px; font-weight:600; text-align:right; }}
    #map {{ width:100%; height:600px; }}
    .legend-box {{ position:fixed; bottom:20px; left:20px; z-index:9999; background:rgba(255,255,255,0.95); padding:10px 14px; border:1px solid #ccc; border-radius:8px; font-size:12px; box-shadow:0 2px 10px rgba(0,0,0,0.2); }}
    .section-title {{ text-align:center; margin:20px 10px 10px; color:#2c3e50; font-weight:300; font-size:22px; }}
    .chart-container {{ width:95%; max-width:1200px; margin:10px auto 30px; background:white; padding:15px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }}
</style>
</head>
<body>
    <div class="header">
        <h1>Event Locations — Time Map</h1>
        <div class="sub">West Bank · Gaza · Lebanon · Syria</div>
        <div class="stats">
            <span>📍 {len(df)} events</span>
            <span>📅 {df['Date_parsed'].min().date()} → {df['Date_parsed'].max().date()}</span>
            <span>🏷️ {df['Region'].nunique()} regions</span>
            <span>⏱️ {n_bins} time steps ({TIME_BIN_FREQ})</span>
        </div>
    </div>

    <div id="controls">
        <button id="playBtn">▶ Play</button>
        <button id="stepBackBtn">⏮</button>
        <input type="range" id="timeSlider" min="0" max="{n_bins - 1}" value="0" step="1">
        <button id="stepFwdBtn">⏭</button>
        <span id="timeLabel">{bin_labels[0] if bin_labels else ''}</span>
    </div>

    <div id="map"></div>
    <div class="legend-box">
        <b style="display:block;margin-bottom:6px;">📊 Regions</b>
        <div style="font-size:10px;color:#666;margin-bottom:6px;">rolling window: last {FADE_BINS} step(s)</div>
        {legend_rows}
    </div>

    <h2 class="section-title">📊 Event Frequency by Location</h2>
    <div class="chart-container">
        {chart_html}
    </div>

<script>
const FEATURES = {json.dumps(features)};
const BIN_LABELS = {json.dumps(bin_labels)};
const FADE_BINS = {FADE_BINS};
const N_BINS = {n_bins};

const map = L.map('map', {{ preferCanvas: true }}).setView([{center_lat}, {center_lon}], 8);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

// Pre-group features by bin so each slider step is an O(1) lookup instead of
// scanning the full array every frame.
const byBin = Array.from({{length: N_BINS}}, () => []);
for (const f of FEATURES) {{
    if (f.bin >= 0 && f.bin < N_BINS) byBin[f.bin].push(f);
}}

let layerGroup = L.layerGroup().addTo(map);

function render(binIdx) {{
    layerGroup.clearLayers();
    const minBin = Math.max(0, binIdx - FADE_BINS + 1);
    let count = 0;
    for (let b = minBin; b <= binIdx; b++) {{
        for (const f of byBin[b]) {{
            L.circleMarker([f.lat, f.lon], {{
                radius: 5, color: f.color, fillColor: f.color,
                fillOpacity: 0.8, weight: 1
            }}).bindPopup(f.popup).addTo(layerGroup);
            count++;
        }}
    }}
    document.getElementById('timeLabel').textContent = BIN_LABELS[binIdx] + ' (' + count + ' shown)';
    document.getElementById('timeSlider').value = binIdx;
}}

render(0);

const slider = document.getElementById('timeSlider');
slider.addEventListener('input', () => render(parseInt(slider.value)));

document.getElementById('stepBackBtn').addEventListener('click', () => {{
    render(Math.max(0, parseInt(slider.value) - 1));
}});
document.getElementById('stepFwdBtn').addEventListener('click', () => {{
    render(Math.min(N_BINS - 1, parseInt(slider.value) + 1));
}});

let playing = false;
let playTimer = null;
const playBtn = document.getElementById('playBtn');
playBtn.addEventListener('click', () => {{
    playing = !playing;
    playBtn.textContent = playing ? '⏸ Pause' : '▶ Play';
    if (playing) {{
        playTimer = setInterval(() => {{
            let v = parseInt(slider.value) + 1;
            if (v > N_BINS - 1) v = 0;  // loop
            render(v);
        }}, 400);
    }} else {{
        clearInterval(playTimer);
    }}
}});
</script>
</body>
</html>
"""

output_file = "locations_map_time.html"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✅ Map created! Open '{output_file}' in your browser (single self-contained file)")
print(f"   - Total events: {len(df)}")
print(f"   - Date range: {df['Date_parsed'].min().date()} to {df['Date_parsed'].max().date()}")
print(f"   - Time steps: {n_bins} (freq='{TIME_BIN_FREQ}')  |  Rolling window: {FADE_BINS} step(s)")