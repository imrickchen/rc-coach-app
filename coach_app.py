import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import altair as alt

# --- 1. 設定頁面 (寬版佈局) ---
st.set_page_config(page_title="RC Sports Performance", layout="wide")

# --- 側邊欄品牌 Logo ---
st.sidebar.markdown(
    """
    <div style='text-align: center; padding: 10px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 20px;'>
        <h2 style='color: #333; margin:0; font-weight: 800;'>RC SPORTS</h2>
        <h5 style='color: #666; margin:0; letter-spacing: 1px;'>PERFORMANCE</h5>
    </div>
    """, 
    unsafe_allow_html=True
)

# --- 2. 連線設定 ---
@st.cache_resource
def get_google_sheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        # 雲端模式 (Streamlit Cloud 專用)
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except:
        # 本地開發模式
        try:
            creds = Credentials.from_service_account_file(".streamlit/secrets.toml", scopes=scopes)
            return None 
        except Exception as e:
            return None

# --- 3. 資料讀取 ---
@st.cache_data(ttl=3600)
def load_static_data():
    client = get_google_sheet_client()
    if not client: return {}, pd.DataFrame(), {}, pd.DataFrame(), []
    
    try:
        sheet = client.open("Coach_System_DB")
        ws_students = sheet.worksheet("Students")
        ws_plan = sheet.worksheet("Plan")
        
        # 1. 讀取 ExerciseDB (重點分析)
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

        # 2. 讀取 Warmup_Modules
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

        # 3. 讀取學生與主課表
        df_students = pd.DataFrame(ws_students.get_all_records())
        df_plan = pd.DataFrame(ws_plan.get_all_records())

        if not df_students.empty:
            df_students.columns = df_students.columns.astype(str).str.strip()
        if not df_plan.empty:
            df_plan.columns = df_plan.columns.astype(str).str.strip()

        # 處理學生資料
        students_dict = {}
        if not df_students.empty:
            for _, row in df_students.iterrows():
                name = row.get('Name', 'Unknown')
                sid = row.get('StudentID', '000')
                key = f"{name} ({sid})"
                rm_data = {k.replace("_1RM", ""): v for k, v in row.items() if "_1RM" in k and pd.notna(v) and v != ""}
                cmj_static = row.get("CMJ_Baseline", 0)
                memo_txt = row.get("Memo", "")
                
                students_dict[key] = {
                    "rm": rm_data,
                    "cmj_static": cmj_static,
                    "memo": memo_txt
                }

        return students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts

    except Exception as e:
        return {}, pd.DataFrame(), {}, pd.DataFrame(), []

# B. 動態資料
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

# --- 初始化 ---
client = get_google_sheet_client()

if client:
    students_dict, df_plan, exercise_db, df_warmup_modules, key_lifts = load_static_data()
    ws_history, ws_warmup_hist, ws_body_comp, df_history, df_warmup_history, df_body_comp = get_history_worksheets()

    if students_dict:
        # --- 側邊欄工具 ---
        st.sidebar.title("⏱️ 休息計時")
        timer_cols = st.sidebar.columns(3)
        if timer_cols[0].button("60s"): st.sidebar.info("⏳ 60s...")
        if timer_cols[1].button("90s"): st.sidebar.info("⏳ 90s...")
        if timer_cols[2].button("120s"): st.sidebar.info("⏳ 120s...")
        
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
        # 🏋️‍♂️ 功能 A: 今日訓練 (雙欄 + 緊湊版)
        # ==========================================
        if app_mode == "今日訓練 (Workout)":
            st.markdown("<h1 style='text-align: center; color: #333;'>📋 RC Sports - iPad 上課模式</h1>", unsafe_allow_html=True)
            st.write("")
            
            # 建立雙欄位佈局
            left_col, right_col = st.columns([3, 7], gap="large")

            # ----------------------------------------------------
            # 👈 左側欄 (準備區)
            # ----------------------------------------------------
            with left_col:
                st.subheader("👤 學生與設定")
                student_key = st.selectbox("選擇學生", list(students_dict.keys()))
                student_data = students_dict.get(student_key, {})
                cmj_static_base = float(student_data.get("cmj_static", 0))
                student_memo = student_data.get("memo", "")

                # CMJ 輸入重置邏輯 (修正警告版)
                if 'last_student_key' not in st.session_state:
                    st.session_state['last_student_key'] = student_key
                if st.session_state['last_student_key'] != student_key:
                    st.session_state['cmj_input'] = 0.0 # 切換學生歸零
                    st.session_state['last_student_key'] = student_key
                
                # 確保初始化
                if 'cmj_input' not in st.session_state:
                    st.session_state['cmj_input'] = 0.0

                selected_date = st.date_input("訓練日期", value=datetime.now())
                record_date_str = selected_date.strftime("%Y-%m-%d")

                st.write("") 

                # --- 📝 教練備忘錄 ---
                with st.expander("📝 教練備忘 (Memo)", expanded=True):
                    new_memo = st.text_area("注意事項", value=student_memo, height=100, label_visibility="collapsed")
                    if st.button("💾 更新備註"):
                        try:
                            fresh_sheet = client.open("Coach_System_DB")
                            ws_students_fresh = fresh_sheet.worksheet("Students")
                            sid = student_key.split('(')[1].strip(')')
                            cell = ws_students_fresh.find(sid)
                            if cell:
                                headers = ws_students_fresh.row_values(1)
                                if "Memo" in headers:
                                    memo_col_idx = headers.index("Memo") + 1
                                    ws_students_fresh.update_cell(cell.row, memo_col_idx, new_memo)
                                    st.toast("✅ 備註已更新！")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                        except Exception as e:
                            st.error(f"更新失敗: {e}")

                # --- ⚖️ 身體組成 ---
                with st.expander("⚖️ 身體數值 (Body Comp)", expanded=False):
                    last_weight = 0
                    if not df_body_comp.empty:
                         stu_bc = df_body_comp[df_body_comp["StudentID"] == student_key].sort_values("Date")
                         if not stu_bc.empty:
                             last_weight = float(stu_bc.iloc[-1]["Weight"])

                    in_weight = st.number_input("體重 (kg)", step=0.1)
                    if last_weight > 0 and in_weight > 0:
                        delta_w = in_weight - last_weight
                        st.metric("體重變化", f"{in_weight} kg", f"{delta_w:.1f} kg", delta_color="inverse")
                    
                    in_fat = st.number_input("體脂率 (%)", step=0.1)
                    in_muscle = st.number_input("骨骼肌 (kg)", step=0.1)
                    in_note = st.text_input("測量備註")
                    
                    if st.button("✅ 存入數值"):
                        if ws_body_comp:
                            ws_body_comp.append_rows([[record_date_str, student_key, in_weight, in_fat, in_muscle, in_note]])
                            st.toast("✅ 身體數值已儲存！")
                            time.sleep(1)
                            st.rerun()

                st.write("") 

                # --- 🔥 暖身系統 ---
                st.markdown("""
                    <div style="background-color: #FFF5F5; padding: 20px; border-radius: 15px; border: 1px solid #FFEEEE;">
                    <h3 style="margin-top:0;">🔥 暖身環節</h3>
                """, unsafe_allow_html=True)

                warmup_options = ["(自定義 / 空白)"]
                if not df_warmup_modules.empty and "Module_Name" in df_warmup_modules.columns:
                    warmup_options += df_warmup_modules["Module_Name"].unique().tolist()
                
                selected_warmup = st.selectbox("選擇模組", warmup_options)

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

                with st.expander("🛠️ 修改暖身表"):
                    if exercise_db:
                        w_cat = st.selectbox("分類", list(exercise_db.keys()), key="w_cat")
                        w_ex = st.selectbox("動作", exercise_db.get(w_cat, []), key="w_ex")
                        c_w1, c_w2 = st.columns(2)
                        with c_w1:
                             if st.button("➕ 新增"):
                                w_df = st.session_state['warmup_df']
                                new_w_row = {"動作名稱": w_ex, "組數": 1, "次數/時間": "10", "備註": "新增"}
                                st.session_state['warmup_df'] = pd.concat([w_df, pd.DataFrame([new_w_row])], ignore_index=True)
                                st.rerun()
                        with c_w2:
                             if st.button("🔄 替換首項"):
                                w_df = st.session_state['warmup_df']
                                if not w_df.empty:
                                    w_df.at[0, "動作名稱"] = w_ex
                                    st.session_state['warmup_df'] = w_df
                                    st.rerun()

                edited_warmup_df = st.data_editor(st.session_state['warmup_df'], hide_index=True, use_container_width=True, num_rows="dynamic")

                if st.button("✅ 紀錄暖身", type="secondary", use_container_width=True):
                    valid_warmup_records = []
                    for _, row in edited_warmup_df.iterrows():
                        if row["動作名稱"] and str(row["動作名稱"]).strip() != "":
                            valid_warmup_records.append([record_date_str, student_key, selected_warmup, row["動作名稱"], row["組數"], row["次數/時間"], row["備註"]])
                    if valid_warmup_records:
                        if ws_warmup_hist:
                            ws_warmup_hist.append_rows(valid_warmup_records)
                            st.toast("✅ 暖身已紀錄！", icon="🔥")
                    else:
                        st.warning("表格為空")
                
                st.markdown("</div>", unsafe_allow_html=True)

            # ----------------------------------------------------
            # 👉 右側欄 (訓練區)
            # ----------------------------------------------------
            with right_col:
                # --- 1. 頂部儀表板 ---
                st.subheader("📊 訓練概況")
                m1, m2, m3 = st.columns(3)
                
                last_date_str = "無紀錄"
                days_gap_str = "-"
                last_plan_str = "新學生"

                if not df_history.empty:
                    stu_hist = df_history[df_history["StudentID"] == student_key].copy()
                    if "PlanName" in stu_hist.columns:
                        stu_hist = stu_hist[stu_hist["PlanName"] != "CMJ_Check"]
                    if not stu_hist.empty:
                        stu_hist["Date"] = pd.to_datetime(stu_hist["Date"])
                        last_rec = stu_hist.sort_values("Date", ascending=False).iloc[0]
                        last_date_obj = last_rec["Date"]
                        last_date_str = last_date_obj.strftime("%Y-%m-%d")
                        delta_days = (datetime.now() - last_date_obj).days
                        days_gap_str = f"{delta_days} 天前"
                        last_plan_str = f"{last_rec['PlanName']} ({last_rec['Day']})"

                m1.metric("上次訓練", last_date_str, days_gap_str, delta_color="inverse")
                m2.metric("上次課表", last_plan_str)
                
                # 智慧狀態判斷
                current_cmj = st.session_state.get('cmj_input', 0.0)
                status_label = "⏳ 等待測量"
                status_val = "-"
                status_delta = None
                status_color = "off"

                if current_cmj > 0 and cmj_static_base > 0:
                    ratio = current_cmj / cmj_static_base
                    diff = current_cmj - cmj_static_base
                    status_val = f"{current_cmj} cm"
                    if ratio >= 0.95:
                        status_label = "🚀 狀態極佳"
                        status_delta = f"+{diff:.1f} cm"
                        status_color = "normal"
                    elif ratio >= 0.90:
                        status_label = "⚖️ 狀態普通"
                        status_delta = f"{diff:.1f} cm"
                        status_color = "off"
                    else:
                        status_label = "🛑 疲勞警示"
                        status_delta = f"{diff:.1f} cm"
                        status_color = "inverse"

                m3.metric("學員狀態", status_label, status_delta, delta_color=status_color)

                st.divider()

                # --- 2. CMJ 檢測 ---
                with st.container():
                    st.caption("🐇 賽前/訓前 CMJ 狀態檢測")
                    c_cmj1, c_cmj2, c_cmj3 = st.columns([2, 2, 2])
                    baseline_val = cmj_static_base
                    with c_cmj1:
                        # 🔥 修正警告：這裡移除了 value=0.0，完全依靠 session_state 的 'cmj_input'
                        today_cmj = st.number_input("CMJ (cm)", step=0.5, label_visibility="collapsed", key="cmj_input")
                    with c_cmj2:
                        if baseline_val > 0:
                            st.caption(f"基準: {baseline_val} cm")
                    with c_cmj3:
                         if st.button("紀錄 CMJ", use_container_width=True):
                            if today_cmj > 0:
                                ws_history.append_rows([[record_date_str, student_key, "CMJ_Check", "Day_0", "Countermovement Jump", 0, today_cmj, f"Base:{baseline_val:.1f}"]])
                                st.toast("✅ CMJ 已存檔！")

                st.write("") 

                # --- 3. 主訓練課表 ---
                st.markdown("""
                    <div style="background-color: #F0F8FF; padding: 20px; border-radius: 15px; border: 1px solid #E6F3FF;">
                    <h3 style="margin-top:0;">🏋️‍♂️ 主訓練 (Main Workout)</h3>
                """, unsafe_allow_html=True)
                
                mp1, mp2 = st.columns(2)
                with mp1:
                    available_plans = df_plan["Plan_Name"].unique().tolist() if not df_plan.empty else []
                    plan_name = st.selectbox("選擇計畫", available_plans, label_visibility="collapsed", placeholder="選擇課表...")
                with mp2:
                    days = df_plan[df_plan["Plan_Name"] == plan_name]["Day"].unique().tolist() if plan_name else []
                    day = st.selectbox("選擇進度", days, label_visibility="collapsed", placeholder="選擇天數...")

                if plan_name and day:
                    # 🔥 頁面切換防丟失邏輯 (Anti-Loss Logic)
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
                            for s in range(1, int(row["Sets"]) + 1):
                                rows.append({
                                    "編號": str(row["Order"]), "動作名稱": row["Exercise"], "組數": f"Set {s}",
                                    "計畫次數": row["Reps"], "強度 (%)": fmt_int,
                                    "建議重量": w, 
                                    "實際重量 (kg)": None, 
                                    "實際次數": row["Reps"],
                                    "備註": ""
                                })
                        st.session_state['workout_df'] = pd.DataFrame(rows)
                        st.session_state['last_context'] = current_context
                    
                    cols = ["編號", "動作名稱", "組數", "計畫次數", "強度 (%)", "建議重量", "實際重量 (kg)", "實際次數", "備註"]
                    st.session_state['workout_df'] = st.session_state['workout_df'][cols]

                    edited_df = st.data_editor(
                        st.session_state['workout_df'], 
                        hide_index=True, 
                        use_container_width=True, 
                        num_rows="dynamic",
                        column_config={
                            "強度 (%)": st.column_config.TextColumn(disabled=True),
                            "實際重量 (kg)": st.column_config.NumberColumn(min_value=0, max_value=500, step=0.5), 
                            "實際次數": st.column_config.NumberColumn(min_value=0, max_value=100, step=1)
                        }
                    )
                    
                    st.session_state['workout_df'] = edited_df

                    # 進度條
                    total_sets = len(edited_df)
                    filled_sets = edited_df[edited_df["實際重量 (kg)"].notna()].shape[0]
                    progress = filled_sets / total_sets if total_sets > 0 else 0
                    st.progress(progress, text=f"目前進度: {filled_sets}/{total_sets} 組")

                    # 歷史快查
                    current_exercises = st.session_state['workout_df']['動作名稱'].unique().tolist()
                    with st.expander("🔎 歷史數據快查 (Quick Look)", expanded=False):
                        ql_exercise = st.selectbox("選擇動作:", current_exercises)
                        if ql_exercise and not df_history.empty:
                            ql_hist = df_history[(df_history["StudentID"] == student_key) & (df_history["Exercise"] == ql_exercise)].copy()
                            if not ql_hist.empty:
                                ql_hist["Date"] = pd.to_datetime(ql_hist["Date"])
                                ql_show = ql_hist.sort_values("Date", ascending=False).head(5)
                                ql_show["Date"] = ql_show["Date"].dt.strftime('%Y-%m-%d')
                                st.dataframe(ql_show[["Date", "Weight", "Reps", "Note"]], hide_index=True, use_container_width=True)
                            else:
                                st.caption("尚無紀錄")

                    if st.button("💾 紀錄主訓練", type="primary", use_container_width=True):
                        recs = []
                        for _, row in edited_df.iterrows():
                            w_val = row["實際重量 (kg)"]
                            r_val = row["實際次數"]
                            
                            has_weight = False
                            if pd.notna(w_val):
                                try:
                                    if float(w_val) > 0: has_weight = True
                                except: pass
                            
                            has_reps = False
                            if pd.notna(r_val):
                                try:
                                    if float(r_val) > 0: has_reps = True
                                except: pass

                            if has_weight or has_reps:
                                save_w = w_val if pd.notna(w_val) else 0
                                save_r = r_val if pd.notna(r_val) else 0
                                recs.append([record_date_str, student_key, plan_name, day, row["動作名稱"], save_w, save_r, row["備註"]])
                        if recs:
                            with st.spinner("存檔中..."):
                                ws_history.append_rows(recs)
                                st.toast("✅ 主訓練已儲存！")
                                time.sleep(1)
                                st.rerun()
                
                st.markdown("</div>", unsafe_allow_html=True)

        # ==========================================
        # 🔍 功能 B: 歷史查詢 (漸進式揭露版)
        # ==========================================
        elif app_mode == "歷史查詢 (History)":
            st.header("🔍 歷史紀錄")
            
            if not df_history.empty:
                df_history['Date'] = pd.to_datetime(df_history['Date'])
                if not df_warmup_history.empty:
                    df_warmup_history['Date'] = pd.to_datetime(df_warmup_history['Date'])

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