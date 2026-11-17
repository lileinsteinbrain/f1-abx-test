# app.py  ——— F1 ABX Pilot (ready-to-deploy)

import random, time, re
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

import gspread
from google.oauth2.service_account import Credentials

# ========== Basic config ==========
ROOT = Path(__file__).parent
STIM = ROOT / "stim"   # layout: stim/VER|RUS|NOR/xxx.png|wav

st.set_page_config(page_title="F1 ABX Pilot", page_icon="🏁", layout="wide")
st.title("F1 ABX Pilot Test")

# Google Sheet ID (the only variable to change)
SHEET_ID = "1FUp4v1ZlGGY4r4pDeie96TXIp1F9eWnpI_HVc_w5c-M"

@st.cache_resource(show_spinner=False)
def _get_ws():
    """Return the first worksheet of the Google Sheet. Requires [google_sheets] JSON in Streamlit Cloud secrets."""
    sa = st.secrets["google_sheets"]
    creds = Credentials.from_service_account_info(sa, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.sheet1

# ========== Filename parsing: lap / seg ==========
def parse_lap(path_str: str):
    m = re.search(r'lap(\d+)', str(path_str))
    return int(m.group(1)) if m else None

def parse_seg(path_str: str):
    m = re.search(r'seg(\d+)', str(path_str))
    return int(m.group(1)) if m else None

# ========== Stimulus scan (viz/heat: png; aud: any .wav) ==========
def scan_stim():
    rows = []
    for drv in ["VER", "RUS", "NOR"]:
        ddir = STIM / drv
        if not ddir.exists():
            continue

        # Images (viz / heat)
        for p in sorted(ddir.glob("*.png")):
            name = p.name.lower()
            if name.endswith("_fp.png"):
                rows.append(dict(condition="viz", driver=drv, path=str(p.relative_to(ROOT))))
            elif name.endswith("_heat.png"):
                rows.append(dict(condition="heat", driver=drv, path=str(p.relative_to(ROOT))))

        # Audio (any .wav accepted)
        for p in sorted(ddir.glob("*.wav")):
            rows.append(dict(condition="aud", driver=drv, path=str(p.relative_to(ROOT))))

    return pd.DataFrame(rows)

@st.cache_data(show_spinner=False)
def load_pool():
    return scan_stim()

pool = load_pool()
if pool.empty:
    st.warning("No stimuli found. Make sure the repo contains `stim/VER|RUS|NOR/*_fp.png`, `*_heat.png` and `*.wav`.")
    st.stop()

# ========== Right-hand control panel ==========
colL, colR = st.columns([2,1])
with colR:
    participant = st.text_input("Participant ID (required)", "", placeholder="e.g. test01")
    n_trials = st.number_input("Number of trials", 5, 60, 20)
    modes = st.multiselect("Include conditions", ["viz", "heat", "aud"], default=["viz","heat","aud"])
    if st.button("🔄 Rescan stimuli"):
        load_pool.clear()
        st.rerun()

if not participant:
    st.info("Enter a participant ID to start.")
    st.stop()

# ========== ABX trial generation: X always matches the driver of A or B ==========
def make_abx_trials(df, n, modes):
    df = df[df["condition"].isin(modes)].reset_index(drop=True)

    # Bucket by (condition -> driver)
    buckets = {}
    for cond in df["condition"].unique():
        buckets[cond] = {}
        sub = df[df["condition"] == cond]
        for drv in sub["driver"].unique():
            recs = sub[sub["driver"] == drv].to_dict("records")
            if recs:
                buckets[cond][drv] = recs

    trials = []
    rng = random.Random()

    def sample_not_same_path(records, exclude_path=None):
        if exclude_path is None:
            return rng.choice(records)
        cand = [r for r in records if r["path"] != exclude_path]
        return rng.choice(cand if cand else records)

    for _ in range(n):
        # 1) Pick a usable condition (at least 2 drivers available)
        cond_pool = [c for c, dmap in buckets.items() if (c in modes) and (len(dmap) >= 2)]
        if not cond_pool:
            # Fallback: three random stimuli (when the pairing constraint cannot be met)
            cand = df.sample(min(3, len(df))).to_dict("records")
            if len(cand) < 3:
                break
            A, B, X = cand[0], cand[1], cand[2]
            AB = [A, B]; rng.shuffle(AB); A, B = AB
            correct = "A" if A["driver"] == X["driver"] else "B"
            # Parse lap/seg
            trials.append(dict(
                is_practice=False, condition=cand[0]["condition"],
                A_driver=A["driver"], A_path=A["path"], A_lap=parse_lap(A["path"]), A_seg=parse_seg(A["path"]),
                B_driver=B["driver"], B_path=B["path"], B_lap=parse_lap(B["path"]), B_seg=parse_seg(B["path"]),
                X_driver=X["driver"], X_path=X["path"], X_lap=parse_lap(X["path"]), X_seg=parse_seg(X["path"]),
                correct_answer=correct
            ))
            continue

        cond = rng.choice(cond_pool)
        drivers_here = list(buckets[cond].keys())

        # 2) Choose same / different driver
        driver_same = rng.choice(drivers_here)
        driver_diff = rng.choice([d for d in drivers_here if d != driver_same])

        # 3) Same driver: draw X and its matching sample (never reuse the same file)
        same_bucket = buckets[cond][driver_same]
        if len(same_bucket) < 2:
            # If the same driver has fewer than 2 samples, try another driver
            alt_same = [d for d in drivers_here if d != driver_same and len(buckets[cond][d]) >= 2]
            if alt_same:
                driver_same = rng.choice(alt_same)
                same_bucket = buckets[cond][driver_same]
            else:
                # Fallback: three random stimuli
                cand = df.sample(3).to_dict("records")
                A, B, X = cand[0], cand[1], cand[2]
                AB = [A, B]; rng.shuffle(AB); A, B = AB
                correct = "A" if A["driver"] == X["driver"] else "B"
                trials.append(dict(
                    is_practice=False, condition=cond,
                    A_driver=A["driver"], A_path=A["path"], A_lap=parse_lap(A["path"]), A_seg=parse_seg(A["path"]),
                    B_driver=B["driver"], B_path=B["path"], B_lap=parse_lap(B["path"]), B_seg=parse_seg(B["path"]),
                    X_driver=X["driver"], X_path=X["path"], X_lap=parse_lap(X["path"]), X_seg=parse_seg(X["path"]),
                    correct_answer=correct
                ))
                continue

        X = sample_not_same_path(same_bucket, exclude_path=None)
        A_same = sample_not_same_path(same_bucket, exclude_path=X["path"])

        # 4) Different-driver sample
        diff_bucket = buckets[cond][driver_diff]
        B_diff = sample_not_same_path(diff_bucket, exclude_path=None)

        # 5) Randomise A/B placement (the correct answer shares X's driver)
        if rng.random() < 0.5:
            A, B = A_same, B_diff
            correct = "A"
        else:
            A, B = B_diff, A_same
            correct = "B"

        trials.append(dict(
            is_practice=False, condition=cond,
            A_driver=A["driver"], A_path=A["path"], A_lap=parse_lap(A["path"]), A_seg=parse_seg(A["path"]),
            B_driver=B["driver"], B_path=B["path"], B_lap=parse_lap(B["path"]), B_seg=parse_seg(B["path"]),
            X_driver=X["driver"], X_path=X["path"], X_lap=parse_lap(X["path"]), X_seg=parse_seg(X["path"]),
            correct_answer=correct
        ))

    return trials

# ========== Session initialisation ==========
if ("trials" not in st.session_state) or (st.session_state.get("participant") != participant):
    st.session_state.participant = participant
    st.session_state.trials = make_abx_trials(pool, int(n_trials), modes)
    st.session_state.i = 0
    st.session_state.logs = []          # local log (list of dicts)
    st.session_state.local_rows = []    # backup of rows that failed to write to Google (list of lists)

# ========== Google Sheet writing (single wrapper) ==========
def log_trial_row_to_sheet(row_dict):
    """row_dict: dict with the same fields as the final DataFrame."""
    cols = [
        "participant","trial_index","is_practice","condition",
        "A_driver","A_lap","A_seg","A_path",
        "B_driver","B_lap","B_seg","B_path",
        "X_driver","X_lap","X_seg","X_path",
        "answer","correct_answer","is_correct","rt_ms","timestamp"
    ]
    row_list = [row_dict.get(k, "") for k in cols]
    try:
        ws = _get_ws()
        ws.append_row(row_list, value_input_option="RAW")
        return True, None
    except Exception as e:
        return False, str(e)

# ========== Main flow ==========
i = st.session_state.i
trials = st.session_state.trials

# -- All trials done: download results / backup --
if i >= len(trials):
    st.success("✅ All done! Download the results CSV below.")
    df = pd.DataFrame(st.session_state.logs)
    pname = st.session_state.get("participant", "anon")

    st.download_button(
        "Download results CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{pname}_abx.csv",
        mime="text/csv",
        use_container_width=True
    )

    if st.session_state.local_rows:
        cols = [
            "participant","trial_index","is_practice","condition",
            "A_driver","A_lap","A_seg","A_path",
            "B_driver","B_lap","B_seg","B_path",
            "X_driver","X_lap","X_seg","X_path",
            "answer","correct_answer","is_correct","rt_ms","timestamp"
        ]
        df_local = pd.DataFrame(st.session_state.local_rows, columns=cols)
        st.download_button(
            "Download local backup (rows that failed to write)",
            df_local.to_csv(index=False).encode("utf-8"),
            file_name=f"{pname}_abx_local_backup.csv",
            mime="text/csv",
            use_container_width=True
        )
    st.stop()

# -- Still in progress: render the current trial --
t = trials[i]
st.subheader(f"Trial {i+1}/{len(trials)} — Condition: {t['condition'].upper()}")

# Timer initialisation
if "start_time" not in st.session_state or st.session_state.start_time is None:
    st.session_state.start_time = time.time()

def render_stim(label, rel_path):
    path = ROOT / rel_path
    st.caption(label)
    if rel_path.endswith(".png"):
        st.image(str(path))
    elif rel_path.endswith(".wav"):
        st.audio(path.read_bytes(), format="audio/wav")
    else:
        st.write("⚠️ Unsupported file type:", rel_path)

c1, c2, c3 = st.columns(3, gap="large")
with c3:
    render_stim("X (reference)", t["X_path"])
with c1:
    render_stim("A", t["A_path"])
with c2:
    render_stim("B", t["B_path"])

# -- Answer & record --
ans_col1, ans_col2 = st.columns(2)
clicked = None
with ans_col1:
    if st.button("Choose A", use_container_width=True):
        clicked = "A"
with ans_col2:
    if st.button("Choose B", use_container_width=True):
        clicked = "B"

if clicked:
    start = st.session_state.start_time or time.time()
    rt_ms = int((time.time() - start) * 1000)

    row = dict(
        participant=st.session_state.get("participant", participant),
        trial_index=i,
        is_practice=False,
        condition=t["condition"],
        A_driver=t["A_driver"], A_lap=t.get("A_lap"), A_seg=t.get("A_seg"), A_path=t["A_path"],
        B_driver=t["B_driver"], B_lap=t.get("B_lap"), B_seg=t.get("B_seg"), B_path=t["B_path"],
        X_driver=t["X_driver"], X_lap=t.get("X_lap"), X_seg=t.get("X_seg"), X_path=t["X_path"],
        answer=clicked,
        correct_answer=t["correct_answer"],
        is_correct=int(clicked == t["correct_answer"]),
        rt_ms=rt_ms,
        timestamp=datetime.utcnow().isoformat(timespec="seconds"),
    )

    # Save locally first
    st.session_state.logs.append(row)

    # Try writing to Google Sheet (fall back to local backup on failure)
    ok, err = log_trial_row_to_sheet(row)
    if not ok:
        st.session_state.local_rows.append(row)

    # Next trial
    st.session_state.i += 1
    st.session_state.start_time = None
    st.rerun()
