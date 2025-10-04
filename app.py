import gspread
from google.oauth2.service_account import Credentials
import random, time
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
STIM = ROOT / "stim"   # stim/VER|RUS|NOR/...

st.set_page_config(page_title="F1 ABX Pilot", page_icon="🏁", layout="wide")
st.title("F1 ABX Pilot Test")

# --- 读取刺激 ---
def scan_stim():
    rows = []
    for drv in ["VER","RUS","NOR"]:
        ddir = STIM / drv
        if not ddir.exists(): 
            continue
        for p in sorted(ddir.glob("*.png")):
            if p.name.endswith("_fp.png"):    # 指纹图
                rows.append(dict(condition="viz", driver=drv, path=str(p.relative_to(ROOT))))
            if p.name.endswith("_heat.png"):  # 热力图
                rows.append(dict(condition="heat", driver=drv, path=str(p.relative_to(ROOT))))
        for p in sorted((STIM/drv).glob("*.wav")):
            if p.name.endswith("_aud.wav"):
                rows.append(dict(condition="aud", driver=drv, path=str(p.relative_to(ROOT))))
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=False)
def load_pool():
    df = scan_stim()
    return df

pool = load_pool()
if pool.empty:
    st.warning("未找到刺激。确认仓库内有 `stim/VER|RUS|NOR/*_fp.png`, `*_heat.png`, `*_aud.wav`。")
    st.stop()

# --- 控制面板 ---
colL, colR = st.columns([2,1])
with colR:
    participant = st.text_input("被试 ID（必填）", "", placeholder="例如 test01")
    n_trials = st.number_input("正式题量", 5, 60, 20)
    modes = st.multiselect("包含模式", ["viz","heat","aud"], default=["viz","heat","aud"])
    if st.button("🔄 重新扫描刺激"):
        load_pool.clear()
        st.experimental_rerun()

if not participant:
    st.info("请输入 被试 ID 开始。")
    st.stop()

# --- 生成 ABX 列表（简单随即） ---
def make_abx_trials(df, n, modes):
    df = df[df["condition"].isin(modes)].reset_index(drop=True)
    trials = []
    rng = random.Random()
    for i in range(n):
        # 抽一个模式
        cond = rng.choice(modes)
        cand = df[df["condition"]==cond].sample(3, random_state=None).to_dict("records")
        A, B, X = cand[0], cand[1], cand[2]
        rng.shuffle([A,B])  # 随机化 A/B 次序
        correct = "A" if A["driver"]==X["driver"] else "B"
        trials.append(dict(
            is_practice=False, condition=cond,
            A_driver=A["driver"], A_path=A["path"],
            B_driver=B["driver"], B_path=B["path"],
            X_driver=X["driver"], X_path=X["path"],
            correct_answer=correct
        ))
    return trials

if "trials" not in st.session_state or st.session_state.get("participant") != participant:
    st.session_state.participant = participant
    st.session_state.trials = make_abx_trials(pool, int(n_trials), modes)
    st.session_state.i = 0
    st.session_state.logs = []

# --- 渲染一题 ---
i = st.session_state.i
trials = st.session_state.trials
if i >= len(trials):
    st.success("✅ 全部完成！下方可下载结果 CSV。")
    df = pd.DataFrame(st.session_state.logs)
    # --- 上传到 Google Sheet
for _, row in df.iterrows():
    SHEET.append_row(row.tolist())
st.success("✅ 数据已自动上传至 Google Sheet！")
    st.download_button("下载结果 CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{participant}_abx.csv", mime="text/csv")
    st.stop()

t = trials[i]
st.subheader(f"题目 {i+1}/{len(trials)} — 模式：{t['condition'].upper()}")
# —— 确保这一题有 start_time —— 
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
        st.write("⚠️ 不支持的类型：", rel_path)

c1, c2, c3 = st.columns(3, gap="large")
with c3:
    render_stim("X（参考）", t["X_path"])
with c1:
    render_stim("A", t["A_path"])
with c2:
    render_stim("B", t["B_path"])

# --- 作答 & 计时 ---
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

ans_col1, ans_col2 = st.columns(2)
clicked = None
with ans_col1:
    if st.button("选 A", use_container_width=True):
        clicked = "A"
with ans_col2:
    if st.button("选 B", use_container_width=True):
        clicked = "B"

if clicked:
    # 容错：若 start_time 丢了，就以当前时间当起点，至少不报错
    start = st.session_state.start_time or time.time()
    rt_ms = int((time.time() - start) * 1000)

    row = dict(
        participant=participant, trial_index=i, is_practice=False, condition=t["condition"],
        A_driver=t["A_driver"], A_lap="", A_path=t["A_path"],
        B_driver=t["B_driver"], B_lap="", B_path=t["B_path"],
        X_driver=t["X_driver"], X_lap="", X_path=t["X_path"],
        answer=clicked, correct_answer=t["correct_answer"],
        is_correct=int(clicked == t["correct_answer"]),
        rt_ms=rt_ms, timestamp=pd.Timestamp.utcnow().isoformat(timespec="seconds")
    )
    st.session_state.logs.append(row)

    # 不显示对/错反馈，直接进入下一题
    st.session_state.i += 1
    st.session_state.start_time = None
    st.rerun()

    # --- Google Sheet 连接
    SCOPE = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    CREDS = Credentials.from_service_account_info(st.secrets["google_sheets"], scopes=SCOPE)
    CLIENT = gspread.authorize(CREDS)
    SHEET = CLIENT.open_by_key("你的SheetID").sheet1

