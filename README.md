# Synthracer: F1 ABX Test

**Can people tell Formula 1 drivers apart from their telemetry, and is it easier with pictures or with sound? A small online listening/viewing experiment.**

Perceptual evaluation for **Synthracer** → system: [hybrid-driver-demo](https://github.com/lileinsteinbrain/hybrid-driver-demo).

## The idea
If sonified telemetry really carries a driver's style, listeners should be able to match two clips from the same driver. An **ABX test** checks exactly that: you get samples A and B from two different drivers, plus X, and decide whether X matches A or B. The same test runs in three conditions so they can be compared:
- **viz**: a visual "fingerprint" plot of the lap segment
- **heat**: a telemetry heatmap
- **aud**: the sonified version

## How it works
- Stimuli for three drivers (Verstappen, Russell, Norris), cut into lap segments, live in `stim/VER|RUS|NOR/`
- The app builds randomised trials, always pairing X with one correct driver
- Each answer and its response time are logged to Google Sheets, with a CSV download as a backup

## What's in this repo
| Path | What it is |
|---|---|
| `app.py` | Streamlit experiment app |
| `stim/` | Images and audio stimuli per driver, plus analysis material |

## Status
Pilot study.

## Run it
```bash
pip install -r requirements.txt
streamlit run app.py
```
Logging requires a Google service account in Streamlit secrets (`[google_sheets]`).
