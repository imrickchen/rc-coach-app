import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import altair as alt
import os
import re

# --- 1. 設定頁面 ---
st.set_page_config(page_title="RC Sports Performance", layout="wide")

# ==========================================
# 🛠️ 狀態初始化
# ==========================================
if 'workout_df' not in st.session_state:
    st.session_state['workout_df'] = pd.DataFrame()
if 'saved_signatures' not in st.session_state:
    st.session_state['saved_signatures'] = set()
if 'warmup_df' not in st.session_state:
    st.session_state['warmup_df'] = pd.DataFrame()
if 'selected_student' not in st.session_state:
    st.session_state['selected_student'] = None
if 'selected_plan' not in st.session_state:
    st.session_state['selected_plan'] = None
if 'selected_day' not in st.session_state:
    st.session_state['selected_day'] = None

# ==========================================
# 🛠️ 側邊欄與連線
# ==========================================
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)
else:
    st.sidebar.markdown("### RC SPORTS PERFORMANCE")

st.sidebar.divider()

@st.cache_resource
def get_google_sheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception:
        return None

@st.cache_data(ttl=3600)
def load_static_data():
    client = get_google_sheet_client()
    if not client: return {}, pd.DataFrame(), {}, pd.DataFrame(), []
    try:
        sheet = client.open("Coach_System_DB")
        ws_students = sheet.worksheet("Students")
        ws_plan = sheet.worksheet("Plan")
        
        # ExerciseDB
        key_lifts = []
        try:
            ws_ex_db = sheet.worksheet("ExerciseDB")
            ex_rows = ws_ex_db.get_all_values()
            exercise_db = {}
            if ex_rows:
                categories = ex_rows[0]
                for col_idx, cat in enumerate(categories):
                    cat_name = cat.strip()
                    if cat_name:
                        exercises = []
                        for row_idx in range(1, len(ex_rows)):
                            try:
                                val = ex_rows[row_idx][col_idx]
                                if val.strip(): exercises.append(val.strip())
                            except IndexError: break
                        if cat_name == "⭐重點分析": key_lifts = exercises
                        else: exercise_db[cat_name] = exercises
        except: exercise_db = {}

        # Warmup Modules
        try:
            ws_warmup_mod = sheet.worksheet("Warmup_Modules")
            raw_data = ws_warmup_mod.get_all_values()
            if len(raw_data) > 1:
                headers = [str(h).strip() for h in raw_data[0]]
                df_warmup_modules = pd.DataFrame(raw_data[1:], columns=headers)
            else: df_warmup_modules = pd.DataFrame()
        except: df_warmup_modules = pd.DataFrame()

        df_students = pd.DataFrame(ws_students.get_all_records())
        df_plan = pd.DataFrame(ws_plan.get_all_records())

        if not df_students.empty: df_students.columns = df_students.columns.astype(str).str.strip()
        if not df_plan.empty: df_plan.columns = df_plan.columns.astype(str).str.strip()

        students_dict = {}
        if not df_students.empty:
            for _, row in df_students.iterrows():
                name = row.get('Name', 'Unknown')
                sid = row.get('StudentID', '000')
                key = f"{name} ({sid})"
                rm_data = {k.replace("_1RM", ""): v for k, v in row.items() if "_1RM" in k and pd.notna(v) and v != ""}
                raw_cmj = row.get("CMJ_Baseline", 0)
                try: cmj_static = float(raw_cmj)
                except: cmj_static = 0.0
                students_dict[key] = {"rm": rm_data, "cmj_static": cmj_static, "memo": row.get("Memo", "")}

        return students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts
    except: return {}, pd.DataFrame(), {}, pd.DataFrame(), []

def get_history_worksheets():
    client = get_google_sheet_client()
    if not client: return None, None, None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    try:
        sheet = client.open("Coach_System_DB")
        ws_history = sheet.worksheet("History")
        ws_warmup_hist = sheet.worksheet("Warmup_History")
        try:
            ws_body_comp = sheet.worksheet("Body_Composition")
            df_body_comp = pd.DataFrame(ws_body_comp.get_all_records())
            if not df_body_comp.empty: df_body_comp.columns = df_body_comp.columns.astype(str).str.strip()
        except: 
            ws_body_comp = None
            df_body_comp = pd.DataFrame()
        
        df_history = pd.DataFrame(ws_history.get_all_records())
        if not df_history.empty: df_history.columns = df_history.columns.astype(str).str.strip()
        df_warmup_history = pd.DataFrame(ws_warmup_hist.get_all_records())
        if not df_warmup_history.empty: df_warmup_history.columns = df_warmup_history.columns.astype(str).str.strip()
            
        return ws_history, ws_warmup_hist, ws_body_comp, df_history, df_warmup_history, df_body_comp
    except: return None, None, None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# 連線檢查
client = get_google_sheet_client()
if not client:
    st.error("⚠️ 無法連接至 Google 雲端資料庫，請重整頁面。")
    st.stop()

students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts = load_static_data()
ws_history, ws_warmup_hist, ws_body_comp, df_history, df_warmup_history, df_body_comp = get_history_worksheets()

if students_dict:
    # 🌟 Callback Functions (狀態鎖定的核心)
    def on_student_change():
        st.session_state['workout_df'] = pd.DataFrame() # 換人才清空
        st.session_state['saved_signatures'] = set()
        st.session_state['cmj_input'] = None

    def on_plan_change():
        st.session_state['workout_df'] = pd.DataFrame() # 換課表才清空
        st.session_state['selected_day'] = None 

    def on_day_change():
        st.session_state['workout_df'] = pd.DataFrame() # 換天數才清空

    # 🌟 關鍵修正：當表格內容改變時，立刻同步到 Session State
    def on_editor_change():
        # 這個 callback 會在 Rerun 之前執行，確保資料被保存
        # 從 editor key 取得最新的 edited dataframe
        new_state = st.session_state.get('workout_editor')
        if new_state is not None:
            st.session_state['workout_df'] = new_state

    # --- 側邊欄 ---
    st.sidebar.subheader("👤 學生與日期")
    # 排序學生清單，確保順序穩定
    student_list = sorted(list(students_dict.keys()))
    
    if st.session_state['selected_student'] not in student_list:
        st.session_state['selected_student'] = student_list[0] if student_list else None

    student_key = st.sidebar.selectbox(
        "選擇學生", 
        student_list, 
        key='selected_student', 
        on_change=on_student_change
    )
    
    student_data = students_dict.get(student_key, {})
    student_memo = student_data.get("memo", "")
    cmj_static_base = float(student_data.get("cmj_static", 0))

    selected_date = st.sidebar.date_input("訓練日期", value=datetime.now())
    record_date_str = selected_date.strftime("%Y-%m-%d")
    st.sidebar.divider()
    
    st.sidebar.caption("🔧 1RM 快速換算")
    calc_w = st.sidebar.number_input("重量 (kg)", 0, 300, 60)
    calc_r = st.sidebar.number_input("次數 (reps)", 1, 30, 5)
    if calc_w > 0:
        est_1rm = calc_w * (1 + 0.0333 * calc_r)
        st.sidebar.markdown(f"**預估 1RM:** `{int(est_1rm)}` / **85%:** `{int(est_1rm * 0.85)}`")

    st.sidebar.divider()
    if st.sidebar.button("🔄 重整資料庫"):
        st.cache_data.clear()
        st.rerun()

    app_mode = st.sidebar.radio("功能選單", ["今日訓練 (Workout)", "歷史查詢 (History)"])

    if app_mode == "今日訓練 (Workout)":
        left_col, right_col = st.columns([3, 7], gap="large")

        # --- 左側欄 ---
        with left_col:
            st.markdown(f"## {student_key.split('(')[0]}")
            st.caption(f"ID: {student_key.split('(')[1][:-1]}")
            
            with st.expander("📝 教練備忘 (Memo)", expanded=True):
                new_memo = st.text_area("Memo", value=student_memo, height=100, label_visibility="collapsed")
                if st.button("💾 更新備註"):
                    try:
                        fresh_sheet = client.open("Coach_System_DB")
                        ws_fresh = fresh_sheet.worksheet("Students")
                        sid = student_key.split('(')[1].strip(')')
                        all_ids = ws_fresh.col_values(2) 
                        try:
                            row_idx = all_ids.index(sid) + 1 
                            ws_fresh.update_cell(row_idx, 9, new_memo) 
                            st.toast("✅ 備註已更新！")
                            time.sleep(1)
                            st.cache_data.clear()
                            st.rerun()
                        except: st.error("找不到此 ID")
                    except Exception as e: st.error(f"Error: {e}")

            st.markdown("### ⚖️ 身體數值")
            in_weight = st.number_input("體重 (kg)", step=0.1)
            in_fat = st.number_input("體脂率 (%)", step=0.1)
            in_muscle = st.number_input("骨骼肌 (kg)", step=0.1)
            
            if st.button("💾 存入數值"):
                if ws_body_comp:
                    ws_body_comp.append_rows([[record_date_str, student_key, in_weight, in_fat, in_muscle, ""]])
                    st.toast("✅ 已儲存")
                    st.cache_data.clear()

        # --- 右側欄 (主操作區) ---
        with right_col:
            st.markdown("### 🔥 暖身環節")
            warmup_opts = ["(自定義)"] + (df_warmup_modules["Module_Name"].unique().tolist() if not df_warmup_modules.empty else [])
            sel_warmup = st.selectbox("選擇模組", warmup_opts)
            
            if 'warmup_key' not in st.session_state or st.session_state['warmup_key'] != (student_key, sel_warmup):
                if sel_warmup != "(自定義)" and not df_warmup_modules.empty:
                    df_w = df_warmup_modules[df_warmup_modules["Module_Name"] == sel_warmup][["Exercise", "Sets", "Reps", "Note"]]
                    df_w.columns = ["動作名稱", "組數", "次數/時間", "備註"]
                    st.session_state['warmup_df'] = df_w
                else:
                    st.session_state['warmup_df'] = pd.DataFrame([{"動作名稱":"", "組數":1, "次數/時間":"", "備註":""}]*3)
                st.session_state['warmup_key'] = (student_key, sel_warmup)

            edited_warmup = st.data_editor(st.session_state['warmup_df'], num_rows="dynamic", use_container_width=True)
            if st.button("✅ 紀錄暖身"):
                recs = []
                for _, r in edited_warmup.iterrows():
                    if r["動作名稱"]: recs.append([record_date_str, student_key, sel_warmup, r["動作名稱"], r["組數"], r["次數/時間"], r["備註"]])
                if recs and ws_warmup_hist:
                    ws_warmup_hist.append_rows(recs)
                    st.toast("✅ 暖身已存")

            st.divider()

            st.markdown("### 🐇 CMJ 檢測")
            c1, c2 = st.columns([2, 1])
            with c1: cmj_val = st.number_input("CMJ 高度", step=0.5, key="cmj_input")
            with c2:
                if st.button("紀錄 CMJ", type="primary"):
                    if cmj_val > 0 and ws_history:
                        ws_history.append_rows([[record_date_str, student_key, "CMJ_Check", "Day_0", "Countermovement Jump", 0, cmj_val, f"Base:{cmj_static_base}"]])
                        st.toast("✅ CMJ 已存")

            st.divider()
            st.markdown("### 🏋️‍♂️ 主訓練")
            
            available_plans = df_plan["Plan_Name"].unique().tolist() if not df_plan.empty else []
            
            c_p1, c_p2 = st.columns([3, 2])
            
            if st.session_state['selected_plan'] not in available_plans:
                 st.session_state['selected_plan'] = available_plans[0] if available_plans else None

            with c_p1:
                plan_name = st.selectbox(
                    "選擇計畫", 
                    available_plans, 
                    key='selected_plan', 
                    on_change=on_plan_change
                )

            with c_p2:
                raw_days = df_plan[df_plan["Plan_Name"] == plan_name]["Day"].unique().tolist()
                def sort_key(d_str):
                    m = re.search(r'W(\d+)D(\d+)', str(d_str), re.IGNORECASE)
                    return (int(m.group(1)), int(m.group(2))) if m else (999, 999)
                sorted_days = sorted(raw_days, key=sort_key)
                
                if st.session_state['selected_day'] not in sorted_days:
                    st.session_state['selected_day'] = sorted_days[0] if sorted_days else None

                day = st.selectbox(
                    "選擇進度", 
                    sorted_days, 
                    key='selected_day', 
                    on_change=on_day_change
                )

            # --- 資料讀取 ---
            # 邏輯：只在 workout_df 為空時 (代表剛切換選項) 讀取資料
            if st.session_state['workout_df'].empty:
                df_view = df_plan[(df_plan["Plan_Name"] == plan_name) & (df_plan["Day"] == day)].copy()
                student_rm = students_dict.get(student_key, {}).get("rm", {})
                final_rows = []
                for _, row in df_view.iterrows():
                    rm = student_rm.get(row["Exercise"], 0)
                    try: w = int(rm * float(row["Intensity"]))
                    except: w = 0
                    try: sets_count = int(row['Sets'])
                    except: sets_count = 1
                    
                    for i in range(1, sets_count + 1):
                        final_rows.append({
                            "選取": False, "編號": str(row["Order"]), "動作名稱": row["Exercise"], 
                            "組數": f"Set {i}", "計畫次數": row["Reps"], "強度": str(row["Intensity"]), 
                            "建議重量": w, "實際重量": None, "實際次數": row["Reps"], "備註": row.get("Note", "")
                        })
                st.session_state['workout_df'] = pd.DataFrame(final_rows)

            # --- 新增/修改區 ---
            with st.expander("🛠️ 臨時新增/修改"):
                if exercise_db:
                    col_a1, col_a2, col_a3 = st.columns([2, 2, 2])
                    with col_a1: m_cat = st.selectbox("分類", list(exercise_db.keys()))
                    with col_a2: m_ex = st.selectbox("動作", exercise_db.get(m_cat, []))
                    with col_a3:
                        st.write("")
                        if st.button("➕ 加入列表"):
                            new_row = {"選取":False, "編號":"加", "動作名稱":m_ex, "組數":"Set 1", "計畫次數":10, "強度":"-", "建議重量":0, "實際重量":None, "實際次數":None, "備註":""}
                            st.session_state['workout_df'] = pd.concat([st.session_state['workout_df'], pd.DataFrame([new_row])], ignore_index=True)
                            st.rerun()
                        if st.button("🔄 替換選取"):
                            df_curr = st.session_state['workout_df']
                            if "選取" in df_curr.columns and df_curr["選取"].any():
                                df_curr.loc[df_curr["選取"]==True, "動作名稱"] = m_ex
                                df_curr.loc[df_curr["選取"]==True, "選取"] = False
                                st.session_state['workout_df'] = df_curr
                                st.rerun()
                            else: st.toast("⚠️ 請先勾選下方項目")

            # --- 主表格 (綁定 on_change) ---
            edited_df = st.data_editor(
                st.session_state['workout_df'],
                hide_index=True, use_container_width=True, num_rows="dynamic",
                key="workout_editor", # Key 綁定 session state
                on_change=on_editor_change, # 🌟 資料變更時，觸發狀態更新
                column_config={
                    "選取": st.column_config.CheckboxColumn("✅", width="small"),
                    "實際重量": st.column_config.NumberColumn("實際 kg", step=0.5),
                    "實際次數": st.column_config.NumberColumn("實際次數", step=1)
                }
            )

            if st.button("💾 紀錄主訓練", type="primary", use_container_width=True):
                recs = []
                count = 0
                for _, r in edited_df.iterrows():
                    if (pd.notna(r["實際重量"]) and r["實際重量"] > 0) or (pd.notna(r["實際次數"]) and r["實際次數"] > 0):
                        sig = f"{student_key}|{record_date_str}|{r['動作名稱']}|{r['組數']}|{r['實際重量']}|{r['實際次數']}"
                        if sig not in st.session_state['saved_signatures']:
                            recs.append([record_date_str, student_key, plan_name, day, r["動作名稱"], r["實際重量"], r["實際次數"], r["備註"]])
                            st.session_state['saved_signatures'].add(sig)
                            count += 1
                if recs and ws_history:
                    ws_history.append_rows(recs)
                    st.toast(f"✅ 成功儲存 {count} 筆")
                    st.cache_data.clear()
                    time.sleep(1)
                else: st.info("無新資料或已重複")

    elif app_mode == "歷史查詢 (History)":
        st.header("🔍 歷史紀錄")
        if df_history.empty:
            st.warning("⚠️ 目前無歷史紀錄或連線失敗")
        else:
            df_history['Date'] = pd.to_datetime(df_history['Date'], errors='coerce')
            flt_stu = st.selectbox("篩選學生", ["所有學生"] + student_list)
            
            if flt_stu != "所有學生":
                df_show = df_history[df_history["StudentID"] == flt_stu]
            else:
                df_show = df_history

            col_h1, col_h2 = st.columns(2)
            with col_h1:
                st.subheader("🐇 CMJ 分析")
                df_cmj = df_show[df_show["Exercise"] == "Countermovement Jump"]
                if not df_cmj.empty:
                    chart_data = df_cmj.groupby("Date")["Reps"].max().reset_index()
                    c = alt.Chart(chart_data).mark_bar(color='#00BA38').encode(x='Date', y='Reps')
                    st.altair_chart(c, use_container_width=True)
                else: st.caption("無數據")

            with col_h2:
                st.subheader("🏋️‍♂️ 肌力分析 (1RM)")
                if key_lifts:
                    t_ex = st.selectbox("動作", key_lifts)
                    df_ex = df_show[df_show["Exercise"] == t_ex]
                    if not df_ex.empty:
                        df_ex["1RM"] = pd.to_numeric(df_ex["Weight"]) * (1 + 0.0333 * pd.to_numeric(df_ex["Reps"]))
                        chart_data = df_ex.groupby("Date")["1RM"].max().reset_index()
                        c = alt.Chart(chart_data).mark_line(point=True, color='red').encode(x='Date', y='1RM')
                        st.altair_chart(c, use_container_width=True)
                    else: st.caption("無數據")
                else: st.caption("請至 ExerciseDB 設定 ⭐重點分析")

            st.divider()
            st.subheader("📅 訓練日誌")
            if not df_show.empty:
                df_show["DateStr"] = df_show["Date"].dt.strftime('%Y-%m-%d')
                for d_str in sorted(df_show["DateStr"].unique(), reverse=True):
                    d_recs = df_show[df_show["DateStr"] == d_str]
                    with st.expander(f"{d_str} ({len(d_recs)} 筆)"):
                        st.dataframe(d_recs[["StudentID", "Exercise", "Weight", "Reps", "Note"]], hide_index=True)
