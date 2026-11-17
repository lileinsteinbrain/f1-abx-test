# F1 ABX Pilot

## What this is
An online ABX discrimination test asking whether people can tell Formula 1 drivers apart from representations of their telemetry: visual "fingerprints", heatmaps, or sonified audio.

## Input
- Stimuli in `stim/VER`, `stim/RUS`, `stim/NOR`, segmented by lap and segment:
  - `*_fp.png`: driving fingerprint visualisation
  - `*_heat.png`: telemetry heatmap
  - `*.wav`: sonified telemetry
- Participant ID, number of trials, and which modalities to include

## Processing
- Builds a stimulus pool per driver and condition (`viz`, `heat`, `aud`)
- Generates randomised ABX trials: is X the same driver as A or B?
- Records answers and response times

## Output
- One row per trial written to Google Sheets for analysis
- Analysis material in `stim/analysis`

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
```
Results logging needs a Google service account in Streamlit secrets (`[google_sheets]`).

## Related
- [hybrid-driver-demo](https://github.com/lileinsteinbrain/hybrid-driver-demo): telemetry sonification engine
