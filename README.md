# Event Time-Map: How It Works

**Script:** `create_time_map.py`
**Input:** `DataGeolocated_08302026_Governorates.csv`
**Output:** `locations_map_time.html` (single self-contained file)

## 1. Purpose

The script turns a spreadsheet of dated, geolocated events into an interactive
map with a play/pause button and a time slider. As you move the slider (or
press Play), markers appear on the map for events that fall within a rolling
time window, colored by region, with a details popup on click. Below the map
sits a static bar chart of event frequency by location.

## 2. Dependencies

Only two Python libraries are needed:

```
pip install pandas plotly
```

`folium` is **not** used. An earlier version relied on Folium's
`TimestampedGeoJson` plugin (which wraps the `leaflet.timedimension` JS
library), but that plugin has a real recursion bug — it throws
`"Maximum call stack size exceeded"` when a dataset has many events spread
unevenly across a long date range (exactly this dataset's shape: 26 years,
with events clustered into bursts rather than spread evenly). Rather than
work around a third-party bug, the script now ships its own small,
purpose-built JavaScript time control. This was stress-tested in a real
headless browser (20+ seconds of autoplay across 300+ time-steps, plus rapid
manual slider jumps) with zero errors before being handed over.

## 3. Pipeline, step by step

The script runs in two phases: a **Python phase** that loads, cleans, and
shapes the data, and a **JavaScript phase** (generated as a string and
embedded in the output HTML) that runs in the browser and handles the
interactive map.

### Python phase

| Step                   | What happens                                                                                                                                                                                                                                                         |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Load                | Reads the CSV (or `.xlsx`) into a pandas DataFrame; strips whitespace from column names.                                                                                                                                                                             |
| 2. Clean coordinates   | Converts `Latitude`/`Longitude` to numbers (handling comma decimals), drops rows with missing, out-of-range, or `(0,0)` coordinates.                                                                                                                                 |
| 3. Parse dates         | Converts `Date_string` to real datetimes, trying a standard parse first and a day-first parse as a fallback for anything that fails. Rows that still don't parse are dropped.                                                                                        |
| 4. Time-bin the dates  | Rounds every event's timestamp down to the start of its **month** (configurable — see §4) and assigns each event a `bin_idx` (0, 1, 2, …) according to its position among all _distinct_ months present in the data. This is what the slider actually steps through. |
| 5. Classify region     | Assigns each event to West Bank / Gaza / Lebanon / Syria / Other using fixed lat-lon bounding boxes.                                                                                                                                                                 |
| 6. Build feature list  | For every row, builds a small JSON-able record: `{lat, lon, color, bin, popup}` — `popup` is the pre-rendered HTML shown when you click a marker (date, title, location, governorate, region, event type, notes, etc.).                                              |
| 7. Build the bar chart | Groups events by location and region, takes the top 30 by count, and renders a stacked Plotly bar chart (independent of the time slider — it always shows the full dataset).                                                                                         |
| 8. Assemble the HTML   | Injects the feature list, bin labels, and chart into an HTML/CSS/JS template and writes it to `locations_map_time.html`.                                                                                                                                             |

### JavaScript phase (runs in the browser)

This is the part that actually drives the interactivity:

1. **Pre-grouping (`byBin`)** — on page load, the full feature list is split
   into one array per time-bin (`byBin[0]`, `byBin[1]`, …). This means each
   slider move only has to look at the handful of bins currently in the
   fade window, not scan all 7,000+ events every time — this is what keeps
   scrubbing instant even at large scale.
2. **`render(binIdx)`** — the core function. It clears the current markers,
   then re-adds a circle marker for every event whose bin falls in
   `[binIdx - FADE_BINS + 1, binIdx]` (the rolling window), colored by
   region, with its popup attached. It also updates the on-screen label
   (e.g. `2023-11 (842 shown)`) and moves the slider handle to match.
3. **Slider input** — dragging the slider calls `render()` with the new
   value directly; no lag, no animation queue.
4. **Step buttons (`⏮`/`⏭`)** — move one bin at a time.
5. **Play/Pause** — starts a `setInterval` that advances the bin index every
   400ms and calls `render()`, looping back to the start when it reaches the
   end. Pressing Pause clears the interval.

Markers are drawn with Leaflet's **canvas renderer** (`preferCanvas: true`)
rather than one DOM element per marker — this is what lets thousands of
markers redraw every frame without the browser choking.

## 4. Things you can tune

All near the top of the script:

| Variable                           | Default                                    | Effect                                                                                                                                                                                                                      |
| ---------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FILE_PATH`                        | `DataGeolocated_08302026_Governorates.csv` | Input file path.                                                                                                                                                                                                            |
| `TIME_BIN_FREQ`                    | `"M"` (month)                              | Slider resolution. `"D"` day, `"W"` week, `"M"` month, `"Q"` quarter, `"Y"` year. Finer resolution = more time-steps = more precise but slower to scrub through. The script warns if `"D"`/`"W"` produces over 1,000 steps. |
| `FADE_BINS`                        | `3`                                        | How many time-steps' worth of events stay visible at once (the "trail" length). `1` = only the current step's events show.                                                                                                  |
| `REGION_COLORS` / `BOUNDING_BOXES` | West Bank/Gaza/Lebanon/Syria               | Region color mapping and the lat-lon boxes used to classify each event.                                                                                                                                                     |
| Autoplay speed                     | `400` (ms)                                 | Hardcoded in the JS `setInterval(..., 400)` call — lower is faster.                                                                                                                                                         |

## 5. Output

A single HTML file (`locations_map_time.html`) with:

- Header bar with summary stats (event count, date range, region count, number of time steps)
- Play/pause controls and the time slider
- The interactive map itself
- A floating legend (bottom-left) showing region colors and the current rolling-window length
- A frequency bar chart of the top 30 locations by event count, underneath the map

It depends on the Leaflet library from a CDN (`cdn.jsdelivr.net`) and Plotly
from its own CDN for the bar chart, so it needs an internet connection to
render fully — but no server is required; opening it directly from disk
works fine.
