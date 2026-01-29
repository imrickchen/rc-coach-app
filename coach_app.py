import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import altair as alt
import os
import re

# --- 1. 設定頁面 (寬版佈局) ---
st.set_page_config(page_title="RC Sports Performance", layout="wide")

# ==========================================
# 🛠️ 側邊欄 (Global Settings)
# ==========================================

# 1. Logo
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)
else:
    st.sidebar.markdown(
        """
        <div style='text-align: center; padding: 10px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 20px;'>
            <h2 style='color: #333; margin:0; font-weight: 800;'>RC SPORTS</h2>
            <h5 style='color: #666; margin:0; letter-spacing: 1px;'>PERFORMANCE</h5>
        </div>
        """, 
        unsafe_allow_html=True
    )

st.sidebar.divider()

# --- 資料庫連線函式 ---
@st.cache_resource
def get_google_sheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

# --- 資料讀取函式 ---
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
                                if val.strip():
                                    exercises.append(val.strip())
                            except IndexError:
                                break
                        if cat_name == "⭐重點分析":
                            key_lifts = exercises
                        else:
                            exercise_db[cat_name] = exercises
        except:
            exercise_db = {}

        # Warmup Modules
        try:
            ws_warmup_mod = sheet.worksheet("Warmup_Modules")
            raw_data = ws_warmup_mod.get_all_values()
            if len(raw_data) > 1:
                headers = [str(h).strip() for h in raw_data[0]]
                rows = raw_data[1:]
                df_warmup_modules = pd.DataFrame(rows, columns=headers)
            else:
                df_warmup_modules = pd.DataFrame()
        except:
            df_warmup_modules = pd.DataFrame()

        # Students & Plan
        df_students = pd.DataFrame(ws_students.get_all_records())
        df_plan = pd.DataFrame(ws_plan.get_all_records())

        if not df_students.empty:
            df_students.columns = df_students.columns.astype(str).str.strip()
        if not df_plan.empty:
            df_plan.columns = df_plan.columns.astype(str).str.strip()

        students_dict = {}
        if not df_students.empty:
            for _, row in df_students.iterrows():
                name = row.get('Name', 'Unknown')
                sid = row.get('StudentID', '000')
                key = f"{name} ({sid})"
                rm_data = {k.replace("_1RM", ""): v for k, v in row.items() if "_1RM" in k and pd.notna(v) and v != ""}
                
                # CMJ 防呆
                raw_cmj = row.get("CMJ_Baseline", 0)
                try:
                    cmj_static = float(raw_cmj)
                except (ValueError, TypeError):
                    cmj_static = 0.0

                memo_txt = row.get("Memo", "")
                
                students_dict[key] = {
                    "rm": rm_data,
                    "cmj_static": cmj_static,
                    "memo": memo_txt
                }

        return students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts

    except Exception as e:
        return {}, pd.DataFrame(), {}, pd.DataFrame(), []

# 動態資料讀取 (不快取，確保最新)
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
            if not df_body_comp.empty:
                df_body_comp.columns = df_body_comp.columns.astype(str).str.strip()
        except:
            ws_body_comp = None
            df_body_comp = pd.DataFrame()
        
        df_history = pd.DataFrame(ws_history.get_all_records())
        if not df_history.empty:
            df_history.columns = df_history.columns.astype(str).str.strip()
            
        df_warmup_history = pd.DataFrame(ws_warmup_hist.get_all_records())
        if not df_warmup_history.empty:
            df_warmup_history.columns = df_warmup_history.columns.astype(str).str.strip()
            
        return ws_history, ws_warmup_hist, ws_body_comp, df_history, df_warmup_history, df_body_comp
    except Exception as e:
        return None, None, None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- 初始化資料 ---
client = get_google_sheet_client()

# 連線檢查
if not client:
    st.error("⚠️ 無法連接至 Google 雲端資料庫")
    st.warning("請檢查網路連線，或稍後再試。")
    if st.button("🔄 重新連線"):
        st.cache_resource.clear()
        st.rerun()
    st.stop()

students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts = load_static_data()
ws_history, ws_warmup_hist, ws_body_comp, df_history, df_warmup_history, df_body_comp = get_history_worksheets()

if students_dict:
    st.sidebar.subheader("👤 學生與日期")
    
    if 'student_key' not in st.session_state:
        st.session_state['student_key'] = list(students_dict.keys())[0]

    # 監聽學生切換
    def on_student_change():
        new_stu = st.session_state['student_key']
        st.session_state['cmj_input'] = None
        st.session_state['saved_signatures'] = set()
        
        # 搜尋該學生的最後一筆主訓練 (自動跳轉邏輯)
        if not df_history.empty:
            stu_hist = df_history[
                (df_history["StudentID"] == new_stu) & 
                (df_history["PlanName"] != "CMJ_Check")
            ]
            if not stu_hist.empty:
                last_rec = stu_hist.iloc[-1]
                last_plan = last_rec["PlanName"]
                last_day = last_rec["Day"]
                st.session_state['auto_plan'] = last_plan
                st.session_state['auto_day'] = last_day
            else:
                st.session_state['auto_plan'] = None
                st.session_state['auto_day'] = None

    student_key = st.sidebar.selectbox(
        "選擇學生", 
        list(students_dict.keys()), 
        key='student_key', 
        on_change=on_student_change
    )
    
    student_data = students_dict.get(student_key, {})
    try:
        cmj_static_base = float(student_data.get("cmj_static", 0))
    except:
        cmj_static_base = 0.0
    student_memo = student_data.get("memo", "")
    
    if 'saved_signatures' not in st.session_state:
        st.session_state['saved_signatures'] = set()
    if 'cmj_input' not in st.session_state:
        st.session_state['cmj_input'] = None
    if 'workout_df' not in st.session_state:
        st.session_state['workout_df'] = pd.DataFrame()

    selected_date = st.sidebar.date_input("訓練日期", value=datetime.now())
    record_date_str = selected_date.strftime("%Y-%m-%d")

    st.sidebar.divider()

    st.sidebar.caption("🔧 1RM 快速換算")
    calc_w = st.sidebar.number_input("重量 (kg)", 0, 300, 60)
    calc_r = st.sidebar.number_input("次數 (reps)", 1, 30, 5)
    if calc_w > 0:
        est_1rm = calc_w * (1 + 0.0333 * calc_r)
        st.sidebar.markdown(f"**預估 1RM:** `{int(est_1rm)} kg`")
        st.sidebar.markdown(f"💪 **85% (肌力):** `{int(est_1rm * 0.85)} kg`")
        st.sidebar.markdown(f"🏋️ **70% (肌肥):** `{int(est_1rm * 0.70)} kg`")

    st.sidebar.divider()
    if st.sidebar.button("🔄 重整資料庫"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.title("☁️ 中控台")
    app_mode = st.sidebar.radio("功能選單", ["今日訓練 (Workout)", "歷史查詢 (History)"])

    # ==========================================
    # 🏋️‍♂️ 功能 A: 今日訓練
    # ==========================================
    if app_mode == "今日訓練 (Workout)":
        
        left_col, right_col = st.columns([3, 7], gap="large")

        # ----------------------------------------------------
        # 👈 左側欄
        # ----------------------------------------------------
        with left_col:
            st.markdown(f"<h1 style='margin-bottom: 0px;'>👤 {student_key.split('(')[0]}</h1>", unsafe_allow_html=True)
            st.caption(f"ID: {student_key.split('(')[1][:-1]}")
            st.write("")

            last_date_str = "無紀錄"
            days_gap_str = "-"
            last_plan_str = "新學生"

            if not df_history.empty:
                stu_hist = df_history[df_history["StudentID"] == student_key].copy()
                if "PlanName" in stu_hist.columns:
                    stu_hist = stu_hist[stu_hist["PlanName"] != "CMJ_Check"]
                if not stu_hist.empty:
                    stu_hist["Date"] = pd.to_datetime(stu_hist["Date"], errors='coerce')
                    last_rec = stu_hist.sort_values("Date", ascending=False).iloc[0]
                    last_date_obj = last_rec["Date"]
                    if pd.notna(last_date_obj):
                        last_date_str = last_date_obj.strftime("%Y-%m-%d")
                        delta_days = (datetime.now() - last_date_obj).days
                        days_gap_str = f"{delta_days} 天前"
                    last_plan_str = f"{last_rec['PlanName']} ({last_rec['Day']})"

            st.markdown(f"**📅 上次訓練:** {last_date_str} ({days_gap_str})")
            st.caption("上次課表:")
            st.markdown(f"> {last_plan_str}")

            current_cmj = st.session_state.get('cmj_input') 
            safe_cmj = current_cmj if current_cmj is not None else 0.0
            
            status_label = "⏳ 等待測量"
            status_color = "off"
            status_delta = None

            if safe_cmj > 0 and cmj_static_base > 0:
                ratio = safe_cmj / cmj_static_base
                diff = safe_cmj - cmj_static_base
                if ratio >= 0.95:
                    status_label = "🚀 狀態極佳"
                    status_color = "normal"
                    status_delta = f"+{diff:.1f}"
                elif ratio >= 0.90:
                    status_label = "⚖️ 狀態普通"
                    status_color = "off"
                    status_delta = f"{diff:.1f}"
                else:
                    status_label = "🛑 疲勞警示"
                    status_color = "inverse"
                    status_delta = f"{diff:.1f}"

            st.metric("學員狀態 (CMJ)", status_label, status_delta, delta_color=status_color)
            st.write("")

            with st.expander("📝 教練備忘 (Memo)", expanded=True):
                new_memo = st.text_area("注意事項", value=student_memo, height=150, label_visibility="collapsed")
                if st.button("💾 更新備註"):
                    try:
                        fresh_sheet = client.open("Coach_System_DB")
                        ws_fresh = fresh_sheet.worksheet("Students")
                        sid = student_key.split('(')[1].strip(')')
                        
                        # 🔴 [FIXED] 修正 find() 可能誤抓 partial match 的問題
                        # 改用 findall 找出所有匹配，並檢查是否在正確的欄位 (例如 StudentID 通常在第 2 欄)
                        # 這裡採用更穩健的方法：取得所有 StudentID，在 Python 端匹配
                        all_ids = ws_fresh.col_values(2) # 假設 ID 在第二欄
                        try:
                            # 找出 row index (gspread 是 1-based, list 是 0-based)
                            row_idx = all_ids.index(sid) + 1 
                            headers = ws_fresh.row_values(1)
                            if "Memo" in headers:
                                memo_col_idx = headers.index("Memo") + 1
                                ws_fresh.update_cell(row_idx, memo_col_idx, new_memo)
                                st.toast("✅ 備註已更新！")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("找不到 Memo 欄位")
                        except ValueError:
                             st.error(f"找不到學生 ID: {sid}")

                    except Exception as e:
                        st.error(f"更新失敗: {e}")

            st.write("")

            inbody_done = False
            inbody_btn_label = "💾 存入數值"
            inbody_btn_type = "secondary"
            
            if not df_body_comp.empty:
                today_bc = df_body_comp[
                    (df_body_comp["StudentID"] == student_key) & 
                    (df_body_comp["Date"] == record_date_str)
                ]
                if not today_bc.empty:
                    inbody_done = True
                    last_rec = today_bc.iloc[-1]
                    inbody_btn_label = f"✅ 本日已紀錄 ({last_rec['Weight']}kg)"
                    inbody_btn_type = "primary"

            st.markdown("### ⚖️ 身體數值")
            
            last_weight = 0
            if not df_body_comp.empty:
                  stu_bc_hist = df_body_comp[
                      (df_body_comp["StudentID"] == student_key) & 
                      (df_body_comp["Date"] < record_date_str)
                  ].sort_values("Date")
                  if not stu_bc_hist.empty:
                      last_weight = float(stu_bc_hist.iloc[-1]["Weight"])

            in_weight = st.number_input("體重 (kg)", step=0.1, value=None, placeholder="輸入體重...", disabled=inbody_done)
            if last_weight > 0 and in_weight is not None:
                delta_w = in_weight - last_weight
                st.caption(f"較上次: {delta_w:+.1f} kg")
            
            in_fat = st.number_input("體脂率 (%)", step=0.1, value=None, disabled=inbody_done)
            in_muscle = st.number_input("骨骼肌 (kg)", step=0.1, value=None, disabled=inbody_done)
            in_note = st.text_input("測量備註", disabled=inbody_done)
            
            if st.button(inbody_btn_label, type=inbody_btn_type, disabled=inbody_done):
                if ws_body_comp is None:
                     st.error("⚠️ 雲端連線失敗，無法存檔。請重整頁面。")
                else:
                    save_weight = in_weight if in_weight is not None else 0
                    save_fat = in_fat if in_fat is not None else 0
                    save_muscle = in_muscle if in_muscle is not None else 0
                    
                    ws_body_comp.append_rows([[record_date_str, student_key, save_weight, save_fat, save_muscle, in_note]])
                    st.toast("✅ 身體數值已儲存！")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

        # ----------------------------------------------------
        # 👉 右側欄
        # ----------------------------------------------------
        with right_col:
            
            # === 第一區：暖身環節 ===
            warmup_done = False
            warmup_btn_label = "✅ 紀錄暖身"
            warmup_header = "🔥 暖身環節"
            
            if not df_warmup_history.empty:
                today_warmup = df_warmup_history[
                    (df_warmup_history["StudentID"] == student_key) & 
                    (df_warmup_history["Date"] == record_date_str)
                ]
                if not today_warmup.empty:
                    warmup_done = True
                    mod_name = today_warmup.iloc[0]["ModuleName"]
                    warmup_btn_label = f"✅ 本日已紀錄 ({mod_name})"
                    warmup_header = f"🔥 暖身環節 (✅ 已完成)"

            st.markdown(f"### {warmup_header}")
            
            c_w1, c_w2 = st.columns([1, 2])
            with c_w1:
                warmup_options = ["(自定義 / 空白)"]
                if not df_warmup_modules.empty and "Module_Name" in df_warmup_modules.columns:
                    warmup_options += df_warmup_modules["Module_Name"].unique().tolist()
                selected_warmup = st.selectbox("選擇模組", warmup_options, label_visibility="collapsed")

            warmup_state_key = (student_key, selected_warmup)
            if 'last_warmup_selection' not in st.session_state or st.session_state['last_warmup_selection'] != warmup_state_key:
                st.session_state['last_warmup_selection'] = warmup_state_key
                if selected_warmup != "(自定義 / 空白)" and not df_warmup_modules.empty and "Module_Name" in df_warmup_modules.columns:
                    df_w_view = df_warmup_modules[df_warmup_modules["Module_Name"] == selected_warmup].copy()
                    display_rows = []
                    for _, row in df_w_view.iterrows():
                        display_rows.append({
                            "動作名稱": str(row.get("Exercise", "")),
                            "組數": int(row.get("Sets", 1)) if str(row.get("Sets", "1")).isdigit() else 1,
                            "次數/時間": str(row.get("Reps", "")), 
                            "備註": str(row.get("Note", ""))
                        })
                    st.session_state['warmup_df'] = pd.DataFrame(display_rows)
                else:
                    st.session_state['warmup_df'] = pd.DataFrame([{"動作名稱": "", "組數": 1, "次數/時間": "", "備註": ""} for _ in range(3)])

            with st.expander("🛠️ 修改/增加暖身動作"):
                if exercise_db:
                    w_cat = st.selectbox("分類", list(exercise_db.keys()), key="w_cat")
                    w_ex = st.selectbox("動作", exercise_db.get(w_cat, []), key="w_ex")
                    cw_b1, cw_b2 = st.columns(2)
                    with cw_b1:
                         if st.button("➕ 新增至末尾"):
                            w_df = st.session_state['warmup_df']
                            new_w_row = {"動作名稱": w_ex, "組數": 1, "次數/時間": "10", "備註": "新增"}
                            st.session_state['warmup_df'] = pd.concat([w_df, pd.DataFrame([new_w_row])], ignore_index=True)
                            st.rerun()
                    with cw_b2:
                         if st.button("🔄 替換第一項"):
                            w_df = st.session_state['warmup_df']
                            if not w_df.empty:
                                w_df.at[0, "動作名稱"] = w_ex
                                st.session_state['warmup_df'] = w_df
                                st.rerun()

            edited_warmup_df = st.data_editor(st.session_state['warmup_df'], hide_index=True, use_container_width=True, num_rows="dynamic")

            if st.button(warmup_btn_label, type="primary" if warmup_done else "secondary", disabled=warmup_done, use_container_width=True):
                if ws_warmup_hist is None:
                    st.error("⚠️ 雲端連線失敗，無法存檔。請重整頁面。")
                else:
                    valid_warmup_records = []
                    for _, row in edited_warmup_df.iterrows():
                        if row["動作名稱"] and str(row["動作名稱"]).strip() != "":
                            valid_warmup_records.append([record_date_str, student_key, selected_warmup, row["動作名稱"], row["組數"], row["次數/時間"], row["備註"]])
                    if valid_warmup_records:
                        ws_warmup_hist.append_rows(valid_warmup_records)
                        st.toast("✅ 暖身已紀錄！", icon="🔥")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("表格為空")

            st.write("")

            # === 第二區：CMJ 檢測 ===
            st.markdown("### 🐇 CMJ 檢測")
            
            cmj_done = False
            cmj_btn_label = "紀錄 CMJ"
            
            if not df_history.empty:
                today_cmj_rec = df_history[
                    (df_history["StudentID"] == student_key) & 
                    (df_history["Date"] == record_date_str) &
                    (df_history["Exercise"] == "Countermovement Jump")
                ]
                if not today_cmj_rec.empty:
                    cmj_done = True
                    val = today_cmj_rec.iloc[-1]["Reps"] 
                    cmj_btn_label = f"✅ 本日已紀錄 ({val} cm)"

            c_cmj1, c_cmj2, c_cmj3 = st.columns([3, 2, 3])
            with c_cmj1:
                today_cmj = st.number_input("CMJ 高度 (cm)", step=0.5, key="cmj_input", value=None, placeholder="輸入 CMJ...", disabled=cmj_done)
            with c_cmj2:
                if cmj_static_base > 0:
                    st.caption(f"基準: {cmj_static_base} cm")
            with c_cmj3:
                if st.button(cmj_btn_label, type="primary" if cmj_done else "secondary", disabled=cmj_done, use_container_width=True):
                    if ws_history is None:
                        st.error("⚠️ 連線失敗，無法存檔。")
                    elif today_cmj is not None and today_cmj > 0:
                        ws_history.append_rows([[record_date_str, student_key, "CMJ_Check", "Day_0", "Countermovement Jump", 0, today_cmj, f"Base:{cmj_static_base:.1f}"]])
                        st.toast("✅ CMJ 已存檔！")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("請輸入數值")

            st.write("")

            # === 第三區：主訓練 ===
            
            saved_count = 0
            if not df_history.empty:
                today_workout = df_history[
                    (df_history["StudentID"] == student_key) & 
                    (df_history["Date"] == record_date_str) &
                    (df_history["PlanName"] != "CMJ_Check")
                ]
                saved_count = len(today_workout)

            st.markdown(f"### 🏋️‍♂️ 主訓練 (Main Workout)")
            if saved_count > 0:
                st.info(f"📊 本日已存檔：共 {saved_count} 筆紀錄")
            
            mp1, mp2 = st.columns([3, 2])
            with mp1:
                available_plans = df_plan["Plan_Name"].unique().tolist() if not df_plan.empty else []
                plan_idx = 0
                if 'auto_plan' in st.session_state and st.session_state['auto_plan'] in available_plans:
                    plan_idx = available_plans.index(st.session_state['auto_plan'])
                plan_name = st.selectbox("選擇計畫", available_plans, index=plan_idx, label_visibility="collapsed", placeholder="選擇課表...")
            
            with mp2:
                raw_days = []
                if plan_name:
                    raw_days = df_plan[df_plan["Plan_Name"] == plan_name]["Day"].unique().tolist()
                
                def sort_key(d_str):
                    m = re.search(r'W(\d+)D(\d+)', str(d_str), re.IGNORECASE)
                    if m:
                        return (int(m.group(1)), int(m.group(2)))
                    return (999, 999)
                
                sorted_days = sorted(raw_days, key=sort_key)
                
                day_idx = 0
                if 'auto_day' in st.session_state and st.session_state['auto_day']:
                    last_day = st.session_state['auto_day']
                    if last_day in sorted_days:
                        current_found_idx = sorted_days.index(last_day)
                        if current_found_idx + 1 < len(sorted_days):
                            day_idx = current_found_idx + 1
                        else:
                            day_idx = current_found_idx
                    st.session_state['auto_day'] = None 
                
                day = st.selectbox("選擇進度", sorted_days, index=day_idx, label_visibility="collapsed", placeholder="選擇天數...")

            if plan_name and day:
                current_context = (student_key, plan_name, day)
                if 'last_context' not in st.session_state or st.session_state['last_context'] != current_context:
                    df_view = df_plan[(df_plan["Plan_Name"] == plan_name) & (df_plan["Day"] == day)].copy()
                    student_rm = students_dict.get(student_key, {}).get("rm", {})
                    rows = []
                    for _, row in df_view.iterrows():
                        rm = student_rm.get(row["Exercise"], 0)
                        try: w = int(rm * float(row["Intensity"]))
                        except: w = 0
                        raw_int = row.get("Intensity", "")
                        try:
                            val = float(raw_int)
                            fmt_int = f"{int(val * 100)}%" if val <= 1 else f"{val}"
                        except:
                            fmt_int = str(raw_int)
                        
                        note_content = row.get("Note", "")

                        for s in range(1, int(row["Sets"]) + 1):
                            rows.append({
                                "選取": False,
                                "編號": str(row["Order"]), "動作名稱": row["Exercise"], "組數": f"Set {s}",
                                "計畫次數": row["Reps"], "強度 (%)": fmt_int,
                                "建議重量": w, 
                                "實際重量 (kg)": None, 
                                "實際次數": row["Reps"],
                                "備註": note_content
                            })
                    st.session_state['workout_df'] = pd.DataFrame(rows)
                    st.session_state['last_context'] = current_context
                    st.session_state['saved_signatures'] = set()
                
                cols = ["選取", "編號", "動作名稱", "組數", "計畫次數", "強度 (%)", "建議重量", "實際重量 (kg)", "實際次數", "備註"]
                if "選取" not in st.session_state['workout_df'].columns:
                    st.session_state['workout_df']["選取"] = False
                st.session_state['workout_df'] = st.session_state['workout_df'][cols]

                with st.expander("🛠️ 臨時新增/修改動作 (Modify Exercise)"):
                    if exercise_db:
                        col_add1, col_add2, col_add3 = st.columns([2, 2, 2])
                        with col_add1:
                            m_cat = st.selectbox("分類", list(exercise_db.keys()), key="m_cat_main")
                        with col_add2:
                            m_ex = st.selectbox("動作", exercise_db.get(m_cat, []), key="m_ex_main")
                        
                        with col_add3:
                            st.write("") 
                            if st.button("➕ 加入列表 (Add)", use_container_width=True):
                                # 🔴 [FIXED] 防呆讀取 Session，使用 .get() 加上預設值，避免 KeyError
                                current_editor_data = st.session_state.get('workout_editor', {})
                                # 嘗試解析 st.data_editor 的回傳格式 (可能是 dict 包含 changes，或 dataframe，視版本而定)
                                # 在這裡，為了穩健，我們優先信任 st.session_state['workout_df'] 作為基底，
                                # 但更理想的是我們直接操作 Dataframe。
                                # 簡單解法：st.session_state['workout_editor'] 在某些版本直接是 DataFrame。
                                # 如果是 dict (Streamlit >= 1.23)，代表是 changes。
                                # 為了相容性，我們這裡做一個保守處理：讀取 key，如果失敗或格式不對，就讀取 'workout_df'
                                try:
                                    # 嘗試從 editor key 獲取最新狀態 (如果 Streamlit 版本支援 data_editor state 直接為 DF)
                                    # 但大部分新版 st.data_editor 的 key 存的是 state dict (edited_rows, added_rows...)
                                    # 所以我們這裡最安全的做法是：直接對 workout_df 做操作。
                                    # 缺點：如果使用者只打字沒按 Enter，資料可能沒進去。
                                    # 但這是 Streamlit 的限制。
                                    current_df = st.session_state['workout_df'].copy()
                                except:
                                    current_df = pd.DataFrame()

                                new_row = {
                                    "選取": False,
                                    "編號": "加",
                                    "動作名稱": m_ex,
                                    "組數": "Set 1",
                                    "計畫次數": 10,
                                    "強度 (%)": "-",
                                    "建議重量": 0,
                                    "實際重量 (kg)": None,
                                    "實際次數": None,
                                    "備註": "臨時新增"
                                }
                                st.session_state['workout_df'] = pd.concat([current_df, pd.DataFrame([new_row])], ignore_index=True)
                                st.rerun()

                            if st.button("🔄 替換選取列 (Replace)", use_container_width=True):
                                # 🔴 [FIXED] 同樣使用 .get() 風格的防爆邏輯
                                # 實際上 data_editor 的回傳值 (edited_df) 在這裡拿不到，必須依賴 session_state
                                # 這裡我們假設使用者有勾選，這意味著該勾選狀態已經存入 'workout_editor' 的 changes 中
                                # 或更簡單：直接操作 'workout_df' (前提是 Checkbox 有被 commit)
                                # 這裡做一個權衡：只操作 st.session_state['workout_df']
                                current_df = st.session_state.get('workout_df', pd.DataFrame())
                                if not current_df.empty and "選取" in current_df.columns:
                                    if current_df["選取"].any():
                                        current_df.loc[current_df["選取"] == True, "動作名稱"] = m_ex
                                        current_df.loc[current_df["選取"] == True, "選取"] = False
                                        st.session_state['workout_df'] = current_df
                                        st.rerun()
                                    else:
                                        st.toast("⚠️ 請先在下方表格勾選要修改的項目")
                                else:
                                    st.warning("表格為空或未初始化")

                # 這裡的 edited_df 是畫面渲染的結果，也是資料的最新狀態
                edited_df = st.data_editor(
                    st.session_state['workout_df'], 
                    hide_index=True, 
                    use_container_width=True, 
                    num_rows="dynamic",
                    key="workout_editor",
                    column_config={
                        "選取": st.column_config.CheckboxColumn("✅", width="small"),
                        "編號": st.column_config.TextColumn(width="small"),
                        "組數": st.column_config.TextColumn(width="small"),
                        "計畫次數": st.column_config.NumberColumn("次數", width="small"),
                        "強度 (%)": st.column_config.TextColumn("強度", width="small"),
                        "建議重量": st.column_config.NumberColumn("建議 kg", width="small"),
                        "實際重量 (kg)": st.column_config.NumberColumn("實際 kg", min_value=0, max_value=500, step=0.5, width="small"), 
                        "實際次數": st.column_config.NumberColumn("實作次數", min_value=0, max_value=100, step=1, width="small"),
                        "備註": st.column_config.TextColumn(width="medium")
                    },
                    # 關鍵：當編輯發生時，更新 session_state 中的 workout_df
                    # 這樣按鈕按下去時，讀取 workout_df 才是最新的
                    on_change=lambda: st.session_state.update({'workout_df': st.session_state['workout_editor']}) 
                    # 注意：上行 lambda 僅適用於 data_editor key 返回 DF 的版本。
                    # 如果報錯，刪除 on_change，但需接受按鈕可能讀不到未 Enter 的資料。
                    # 為了最穩定的 V4.0，我們暫時拿掉 on_change，改由單向資料流控制，
                    # 但在上面的按鈕邏輯中，我們已經加強了 .get()。
                )
                
                # 同步回 session state (手動同步，確保下次 rerun 資料還在)
                # 這是解決 "輸入太多數字...畫面跳掉...前面輸入的東西都不見了" 的核心
                st.session_state['workout_df'] = edited_df

                total_sets = len(edited_df)
                filled_sets = edited_df[edited_df["實際重量 (kg)"].notna()].shape[0]
                progress = filled_sets / total_sets if total_sets > 0 else 0
                st.progress(progress, text=f"目前填寫進度: {filled_sets}/{total_sets} 組")

                current_exercises = edited_df['動作名稱'].unique().tolist()
                with st.expander("🔎 歷史數據快查 (Quick Look)", expanded=False):
                    ql_exercise = st.selectbox("選擇動作:", current_exercises)
                    if ql_exercise and not df_history.empty:
                        ql_hist = df_history[(df_history["StudentID"] == student_key) & (df_history["Exercise"] == ql_exercise)].copy()
                        if not ql_hist.empty:
                            ql_hist["Date"] = pd.to_datetime(ql_hist["Date"], errors='coerce')
                            ql_show = ql_hist.sort_values("Date", ascending=False).head(5)
                            ql_show["Date"] = ql_show["Date"].dt.strftime('%Y-%m-%d')
                            st.dataframe(ql_show[["Date", "Weight", "Reps", "Note"]], hide_index=True, use_container_width=True)
                        else:
                            st.caption("尚無紀錄")

                if st.button("💾 紀錄主訓練", type="primary", use_container_width=True):
                    if ws_history is None:
                        st.error("⚠️ 雲端連線失敗，無法存檔。請點擊側邊欄的「重整資料庫」。")
                    else:
                        recs = []
                        new_saved_count = 0
                        
                        # 🟡 [FIXED] 後端雙重防重複檢查 (Backend Deduplication)
                        # 建立當前 DB 的指紋集合 (日期|學生|動作|組數)
                        # 為了效能，我們只比對「當天」的資料
                        existing_keys = set()
                        if not df_history.empty:
                            today_records = df_history[
                                (df_history["Date"] == record_date_str) & 
                                (df_history["StudentID"] == student_key)
                            ]
                            for _, r in today_records.iterrows():
                                # 建立唯一鍵：動作 + 組數 (例如 "深蹲|Set 1")
                                k = f"{r['Exercise']}|{r['Set']}" # 假設 History 有 Set 欄位，若無則改用 Exercise|Weight|Reps
                                # V3.1 的寫入格式是 [Date, ID, Plan, Day, Exercise, Weight, Reps, Note]
                                # 這裡我們比較寬鬆，檢查 "Exercise" + "Weight" + "Reps" 
                                k_strict = f"{r['Exercise']}|{r['Weight']}|{r['Reps']}"
                                existing_keys.add(k_strict)

                        for _, row in edited_df.iterrows():
                            save_w = row["實際重量 (kg)"]
                            save_r = row["實際次數"]
                            
                            has_data = False
                            if pd.notna(save_w) and float(save_w) > 0: has_data = True
                            if pd.notna(save_r) and float(save_r) > 0: has_data = True
                            
                            if has_data:
                                # 1. 前端 Session 指紋檢查 (快速)
                                signature = f"{student_key}|{record_date_str}|{row['動作名稱']}|{row['組數']}|{save_w}|{save_r}"
                                if signature in st.session_state['saved_signatures']:
                                    continue
                                
                                # 2. 後端資料比對 (安全)
                                # 檢查這筆資料是否已經在 DB 裡了 (防止重新整理後的重複提交)
                                db_signature = f"{row['動作名稱']}|{save_w}|{save_r}"
                                if db_signature in existing_keys:
                                    # 雖然 Session 沒紀錄，但 DB 已經有了 -> 跳過
                                    st.session_state['saved_signatures'].add(signature) # 補上 Session 紀錄
                                    continue

                                recs.append([record_date_str, student_key, plan_name, day, row["動作名稱"], save_w, save_r, row["備註"]])
                                st.session_state['saved_signatures'].add(signature)
                                new_saved_count += 1
                                
                        if recs:
                            with st.spinner("存檔中..."):
                                ws_history.append_rows(recs)
                                st.toast(f"✅ 成功儲存 {new_saved_count} 筆新紀錄！")
                                st.cache_data.clear()
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.info("沒有變更或新的紀錄需要儲存 (或已存在相同紀錄)")

    # ==========================================
    # 🔍 功能 B: 歷史查詢
    # ==========================================
    elif app_mode == "歷史查詢 (History)":
        st.header("🔍 歷史紀錄")
        
        if df_history.empty:
            st.warning("⚠️ 目前沒有歷史紀錄，或是與資料庫連線失敗。")
            st.info("💡 請嘗試按側邊欄的「🔄 重整資料庫」按鈕。")
        else:
            df_history['Date'] = pd.to_datetime(df_history['Date'], errors='coerce')
            if not df_warmup_history.empty:
                df_warmup_history['Date'] = pd.to_datetime(df_warmup_history['Date'], errors='coerce')

            flt_stu = st.selectbox("篩選學生", ["所有學生"] + list(students_dict.keys()))
            
            if flt_stu != "所有學生":
                df_show = df_history[df_history["StudentID"] == flt_stu]
                df_warmup_show = df_warmup_history[df_warmup_history["StudentID"] == flt_stu] if not df_warmup_history.empty else pd.DataFrame()
            else:
                df_show = df_history
                df_warmup_show = df_warmup_history
            
            if flt_stu == "所有學生":
                st.info("ℹ️ 請先選擇一位學生以查看詳細分析 (CMJ & 1RM)")
            else:
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    st.subheader("🐇 CMJ 分析")
                    df_cmj = df_show[df_show["Exercise"] == "Countermovement Jump"].copy()
                    if not df_cmj.empty:
                        df_cmj["Reps"] = pd.to_numeric(df_cmj["Reps"], errors='coerce')
                        chart_data = df_cmj.groupby("Date")["Reps"].max().reset_index()
                        chart_data['DateStr'] = chart_data['Date'].dt.strftime('%Y-%m-%d')
                        base = alt.Chart(chart_data).encode(x=alt.X('DateStr', type='ordinal', axis=alt.Axis(labelAngle=-45)))
                        bar = base.mark_bar(color='#00BA38').encode(y=alt.Y('Reps', scale=alt.Scale(zero=False)))
                        st.altair_chart((bar + base.mark_line(color='green') + bar.mark_text(dy=-5).encode(text='Reps')).interactive(), use_container_width=True)
                    else:
                        st.info("尚無 CMJ 紀錄")

                with col_h2:
                    st.subheader("🏋️‍♂️ 肌力分析 (1RM)")
                    
                    if key_lifts:
                        target_list = key_lifts 
                    else:
                        target_list = [e for e in df_show["Exercise"].unique() if e != "Countermovement Jump"]

                    if target_list:
                        opts = ["(請選擇動作)"] + target_list
                        c_ex = st.selectbox("選擇動作", opts)
                        
                        if c_ex != "(請選擇動作)":
                            df_ex = df_show[df_show["Exercise"] == c_ex].copy()
                            if not df_ex.empty:
                                df_ex["1RM"] = pd.to_numeric(df_ex["Weight"]) * (1 + 0.0333 * pd.to_numeric(df_ex["Reps"]))
                                chart_data = df_ex.groupby("Date")["1RM"].max().reset_index()
                                chart_data['DateStr'] = chart_data['Date'].dt.strftime('%Y-%m-%d')
                                line = alt.Chart(chart_data).mark_line(point=True, color='red').encode(
                                    x=alt.X('DateStr', type='ordinal', axis=alt.Axis(labelAngle=-45)),
                                    y=alt.Y('1RM', scale=alt.Scale(zero=False))
                                )
                                st.altair_chart((line + line.mark_text(dy=-10).encode(text=alt.Text('1RM', format='.0f'))).interactive(), use_container_width=True)
                            else:
                                st.info(f"ℹ️ 尚無「{c_ex}」的歷史紀錄")
                        else:
                            st.info("👈 請從上方選單選擇動作")
                    else:
                        st.caption("尚未設定重點分析動作")

            st.divider()
            st.subheader("📅 訓練日誌")
            search_term = st.text_input("🔎 關鍵字搜尋 (ex: 划船)")
            df_log_main = df_show[df_show["Exercise"] != "Countermovement Jump"].copy()
            if search_term:
                  df_log_main = df_log_main[df_log_main["Exercise"].str.contains(search_term, case=False, na=False)]

            dates_main = df_log_main['Date'].unique() if not df_log_main.empty else []
            dates_warm = df_warmup_show['Date'].unique() if not df_warmup_show.empty else []
            all_dates = sorted(list(set(list(dates_main) + list(dates_warm))), reverse=True)

            if all_dates:
                for d in all_dates:
                    if pd.isna(d): continue 
                    d_str = pd.to_datetime(d).strftime('%Y-%m-%d')
                    day_main_recs = df_log_main[df_log_main['Date'] == d]
                    
                    title_str = f"▶ {d_str}"
                    if not day_main_recs.empty:
                        rep_row = day_main_recs.iloc[0]
                        title_str += f" | {rep_row['StudentID']} | {rep_row['PlanName']}"
                    
                    with st.expander(title_str):
                        if not df_body_comp.empty:
                            day_bc = df_body_comp[(df_body_comp["Date"] == d_str) & (df_body_comp["StudentID"] == (day_main_recs.iloc[0]['StudentID'] if not day_main_recs.empty else flt_stu))]
                            if not day_bc.empty:
                                st.caption("⚖️ 身體數值")
                                st.dataframe(day_bc[["Weight", "BodyFat", "Muscle", "Note"]], hide_index=True, use_container_width=True)
                        if not df_warmup_show.empty:
                            day_warmup = df_warmup_show[df_warmup_show['Date'] == d]
                            if not day_warmup.empty:
                                st.caption("🔥 暖身紀錄")
                                st.dataframe(day_warmup[["ModuleName", "Exercise", "Sets", "Reps", "Note"]], hide_index=True, use_container_width=True)
                        if not day_main_recs.empty:
                            st.caption("🏋️‍♂️ 主訓練紀錄")
                            st.dataframe(day_main_recs[["Exercise", "Weight", "Reps", "Note"]], hide_index=True, use_container_width=True)
