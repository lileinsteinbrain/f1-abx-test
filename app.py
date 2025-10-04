import gspread
from google.oauth2.service_account import Credentials
import random, time
from pathlib import Path
import pandas as pd
import streamlit as st
from datetime import datetime

# ---------- 基础配置 ----------
ROOT = Path(__file__).parent
STIM = ROOT / "stim"   # stim/VER|RUS|NOR/...

st.set_page_config(page_title="F1 ABX Pilot", page_icon="🏁", layout="wide")
st.title("F1 ABX Pilot Test")

# 你的 Google Sheet ID（只改这里）
SHEET_ID = "1FUp4v1ZlGGY4r4pDeie96TXIp1F9eWnpI_HVc_w5c-M"

@st.cache_resource(show_spinner=False)
def _get_ws():
    """返回 Google Sheet 的第一个工作表连接。"""
    sa = st.secrets["google_sheets"]
    creds = Credentials.from_service_account_info(sa, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.sheet1

# ---------- 刺激扫描 ----------
def scan_stim():
    rows = []
    for drv in ["VER","RUS","NOR"]:
        ddir = STIM / drv
        if not ddir.exists():
            continue
        for p in sorted(ddir.glob("*.png")):
            if p.name.endswith("_fp.png"):
                rows.append(dict(condition="viz", driver=drv, path=str(p.relative_to(ROOT))))
            if p.name.endswith("_heat.png"):
                rows.append(dict(condition="heat", driver=drv, path=str(p.relative_to(ROOT))))
        for p in sorted(ddir.glob("*.wav")):
            if p.name.endswith("_aud.wav"):
                rows.append(dict(condition="aud", driver=drv, path=str(p.relative_to(ROOT))))
    return pd.DataFrame(rows)

@st.cache_data(show_spinner=False)
def load_pool():
    return scan_stim()

pool = load_pool()
if pool.empty:
    st.warning("未找到刺激。确认仓库内有 `stim/VER|RUS|NOR/*_fp.png`, `*_heat.png`, `*_aud.wav`。")
    st.stop()

# ---------- 控制面板 ----------
colL, colR = st.columns([2,1])
with colR:
    participant = st.text_input("被试 ID（必填）", "", placeholder="例如 test01")
    n_trials = st.number_input("正式题量", 5, 60, 20)
    modes = st.multiselect("包含模式", ["viz","heat","aud"], default=["viz","heat","aud"])
    if st.button("🔄 重新扫描刺激"):
        load_pool.clear()
        st.rerun()

if not participant:
    st.info("请输入 被试 ID 开始。")
    st.stop()

# ---------- 构造 ABX 题目 ----------
def make_abx_trials(df, n, modes):
    df = df[df["condition"].isin(modes)].reset_index(drop=True)
    trials = []
    rng = random.Random()
    for i in range(n):
        cond = rng.choice(modes)
        cand = df[df["condition"]==cond].sample(3)
        A, B, X = cand.iloc[0].to_dict(), cand.iloc[1].to_dict(), cand.iloc[2].to_dict()
        # 随机化 A/B 次序
        AB = [A, B]
        rng.shuffle(AB)
        A, B = AB[0], AB[1]
        correct = "A" if A["driver"] == X["driver"] else "B"
        trials.append(dict(
            is_practice=False, condition=cond,
            A_driver=A["driver"], A_path=A["path"],
            B_driver=B["driver"], B_path=B["path"],
            X_driver=X["driver"], X_path=X["path"],
            correct_answer=correct
        ))
    return trials

# ---------- 会话初始化 ----------
if ("trials" not in st.session_state) or (st.session_state.get("participant") != participant):
    st.session_state.participant = participant
    st.session_state.trials = make_abx_trials(pool, int(n_trials), modes)
    st.session_state.i = 0
    st.session_state.logs = []          # 本地日志（dict 列表）
    st.session_state.local_rows = []    # Google 写失败的备份（list 列表）

# ---------- Google Sheet 写入（统一在这里） ----------
def log_trial_row_to_sheet(row_dict):
    """row_dict: 与最终 DataFrame 字段一致的 dict。"""
    # Sheet 的列顺序（与你想要导出的 CSV 一致）
    cols = [
        "participant","trial_index","is_practice","condition",
        "A_driver","A_lap","A_path",
        "B_driver","B_lap","B_path",
        "X_driver","X_lap","X_path",
        "answer","correct_answer","is_correct","rt_ms","timestamp"
    ]
    row_list = [row_dict.get(k, "") for k in cols]
    try:
        ws = _get_ws()
        ws.append_row(row_list, value_input_option="RAW")
        return True, None
    except Exception as e:
        return False, str(e)

# ========== 主流程 ==========
i = st.session_state.i
trials = st.session_state.trials

# —— 全部做完：展示下载按钮（此时 df 已定义）——
if i >= len(trials):
    st.success("✅ 全部完成！下方可下载结果 CSV。")
    df = pd.DataFrame(st.session_state.logs)
    st.download_button(
        "下载结果 CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{participant}_abx.csv",
        mime="text/csv",
        use_container_width=True
    )

    # 若有本地备份，也给一个下载口
    if st.session_state.local_rows:
        cols = [
            "participant","trial_index","is_practice","condition",
            "A_driver","A_lap","A_path",
            "B_driver","B_lap","B_path",
            "X_driver","X_lap","X_path",
            "answer","correct_answer","is_correct","rt_ms","timestamp"
        ]
        df_local = pd.DataFrame(st.session_state.local_rows, columns=cols)
        st.download_button(
            "下载本地备份（写表失败的行）",
            df_local.to_csv(index=False).encode("utf-8"),
            file_name="abx_local_backup.csv",
            mime="text/csv",
            use_container_width=True
        )
    st.stop()

# —— 还在做题：渲染当前题目 —— 
t = trials[i]
st.subheader(f"题目 {i+1}/{len(trials)} — 模式：{t['condition'].upper()}")

# 开始计时
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

# —— 作答 & 记录 —— 
ans_col1, ans_col2 = st.columns(2)
clicked = None
with ans_col1:
    if st.button("选 A", use_container_width=True):
        clicked = "A"
with ans_col2:
    if st.button("选 B", use_container_width=True):
        clicked = "B"

if clicked:
    # RT
    start = st.session_state.start_time or time.time()
    rt_ms = int((time.time() - start) * 1000)

    # 形成一条日志（dict）
    row = dict(
        participant=participant,
        trial_index=i,
        is_practice=False,
        condition=t["condition"],
        A_driver=t["A_driver"], A_lap="", A_path=t["A_path"],
        B_driver=t["B_driver"], B_lap="", B_path=t["B_path"],
        X_driver=t["X_driver"], X_lap="", X_path=t["X_path"],
        answer=clicked,
        correct_answer=t["correct_answer"],
        is_correct=int(clicked == t["correct_answer"]),
        rt_ms=rt_ms,
        timestamp=datetime.utcnow().isoformat(timespec="seconds"),
    )
    # 本地先存
    st.session_state.logs.append(row)

    # 尝试写 Google Sheet（失败就备份）
    ok, err = log_trial_row_to_sheet(row)
    if not ok:
        st.session_state.local_rows.append(row)
        st.info("已落本地备份（稍后可手动上传 Google Sheet）。")

    # 下一题
    st.session_state.i += 1
    st.session_state.start_time = None
    st.rerun()
