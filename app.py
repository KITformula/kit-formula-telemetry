import streamlit as st
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt
import os
from datetime import datetime

# --- 設定 ---
# MQTT_BROKER = "8560a3bce8ff43bb92829fea55036ac1.s1.eu.hivemq.cloud"
# MQTT_PORT = 8883
# MQTT_USER = "kitformula"
# MQTT_PASSWORD = "Kitformula-2026"
# TOPIC = "vehicle/telemetry/#"

# データ保存先フォルダ
DATA_DIR = "lap_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

st.set_page_config(page_title="KitFormula Telemetry", layout="wide")

# --- 関数: CSVへの保存 ---
def save_lap_record(record):
    today_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(DATA_DIR, f"laps_{today_str}.csv")
    df = pd.DataFrame([record])
    if not os.path.exists(file_path):
        df.to_csv(file_path, index=False)
    else:
        df.to_csv(file_path, mode='a', header=False, index=False)

# --- 関数: スタイリング (ベストタイムの色付け) ---
def highlight_bests(df):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    # 対象カラム: Total Time と Sector XX
    target_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
    
    for col in target_cols:
        try:
            # 数値に変換できるものだけ抽出
            valid_values = pd.to_numeric(df[col], errors='coerce').dropna()
            if valid_values.empty: continue
            
            # その列の最小値（ベストタイム）を取得
            min_val = valid_values.min()
            
            for idx in df.index:
                val = df.loc[idx, col]
                if pd.isna(val): continue
                try:
                    # 誤差を考慮して比較
                    if abs(float(val) - min_val) < 0.0001:
                        if col == "Total Time":
                            # トータルベスト: 濃い緑
                            styles.loc[idx, col] = 'background-color: #006400; color: white; font-weight: bold;'
                        else:
                            # セクターベスト: 薄い緑
                            styles.loc[idx, col] = 'background-color: #d0f0c0; color: black; font-weight: bold;'
                except: pass
        except: pass
    return styles

# --- セッションステート初期化 ---
if "lap_history" not in st.session_state:
    st.session_state.lap_history = []
if "current_lap_data" not in st.session_state:
    st.session_state.current_lap_data = {"rpm": 0, "spd": 0}
if "last_lap_count" not in st.session_state:
    st.session_state.last_lap_count = 0

# --- MQTTコールバック ---
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        current_lc = payload.get("lc", 0)
        
        # 現在のセクターデータ抽出
        current_sectors = {k: v for k, v in st.session_state.current_lap_data.items() if k.startswith('s') and k[1:].isdigit()}
        
        if current_lc > st.session_state.last_lap_count:
            if st.session_state.last_lap_count > 0:
                llt = payload.get("llt", None)
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                last_lap_record = {
                    "Timestamp": timestamp,
                    "Lap": st.session_state.last_lap_count,
                    "Total Time": llt,
                }
                for key, val in current_sectors.items():
                    sector_num = key[1:]
                    last_lap_record[f"Sector {sector_num}"] = val
                
                st.session_state.lap_history.append(last_lap_record)
                save_lap_record(last_lap_record)
            
            st.session_state.current_lap_data = {k: v for k, v in st.session_state.current_lap_data.items() if not k.startswith('s')}
            st.session_state.last_lap_count = current_lc

        for key, value in payload.items():
            if key.startswith('s') and key[1:].isdigit():
                st.session_state.current_lap_data[key] = value
        
        st.session_state.current_lap_data["rpm"] = payload.get("rpm", 0)
        st.session_state.current_lap_data["spd"] = payload.get("spd", 0)

    except Exception as e:
        print(f"Error: {e}")

# --- MQTT接続 ---
if "mqtt_client" not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set()
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.subscribe(TOPIC)
        client.loop_start()
        st.session_state.mqtt_client = client
        st.toast("Connected!", icon="✅")
    except Exception as e:
        st.error(f"Connection Error: {e}")


# ==========================================
#  画面レイアウト
# ==========================================

st.sidebar.title("Menu")

# ★追加機能: 基準タイム設定エリア (サイドバー)
with st.sidebar.expander("⏱️ 基準タイム設定 (Reference)", expanded=True):
    ref_times = {}
    # セクター1〜5までの入力欄を作成（値は何でもいいので適当な初期値を設定）
    default_values = [15.0, 25.0, 20.0, 18.5, 16.5] # 合計95.0秒
    
    for i in range(1, 6):
        val = st.number_input(f"Sector {i} (sec)", value=default_values[i-1], step=0.1, format="%.2f")
        ref_times[f"S{i}"] = val
    
    total_ref = sum(ref_times.values())
    st.markdown(f"**Total Target:** `{total_ref:.2f} s`")

mode = st.sidebar.radio("表示モード", ["📡 リアルタイム計測", "📂 過去ログ閲覧"])

# ------------------------------------------
#  A. リアルタイム計測モード
# ------------------------------------------
if mode == "📡 リアルタイム計測":
    st.title("🏎️ Real-time Telemetry")
    
    # ★追加機能: 基準タイムを画面上部に表示
    st.markdown("### 🎯 Reference Times")
    cols = st.columns(6) # S1~S5 + Total で6カラム
    for i in range(1, 6):
        cols[i-1].metric(f"Sector {i}", f"{ref_times[f'S{i}']:.2f}")
    cols[5].metric("Total Target", f"{total_ref:.2f}")
    
    st.divider() # 区切り線

    header_metrics = st.empty()
    table_placeholder = st.empty()
    chart_placeholder = st.empty()

    while True:
        if st.session_state.get("current_mode") != mode:
            st.session_state["current_mode"] = mode
            st.rerun()

        curr = st.session_state.current_lap_data
        lap = st.session_state.last_lap_count
        
        with header_metrics.container():
            st.metric("Current Lap", f"Lap {lap}")

        data_list = st.session_state.lap_history.copy()
        
        # 現在行データ
        current_row = {"Lap": lap, "Total Time": None}
        for key, val in curr.items():
            if key.startswith('s') and key[1:].isdigit():
                current_row[f"Sector {key[1:]}"] = val
        
        display_data = data_list + [current_row]
        
        if len(display_data) > 0:
            df = pd.DataFrame(display_data)
            
            numeric_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
            for c in numeric_cols:
                df[c] = pd.to_numeric(df[c], errors='coerce')

            if "Lap" in df.columns:
                df.set_index("Lap", inplace=True)
            
            def sort_cols(col_name):
                if col_name == "Timestamp": return -1
                if col_name == "Total Time": return 0
                if col_name.startswith("Sector"):
                    try: return int(col_name.split(" ")[1])
                    except: return 999
                return 999
            
            sorted_cols = sorted(df.columns, key=sort_cols)
            df = df[sorted_cols]

            # テーブル描画（ハイライト適用）
            try:
                styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", subset=numeric_cols, na_rep="--")
                table_placeholder.dataframe(styled_df, use_container_width=True, height=400)
            except:
                table_placeholder.dataframe(df, use_container_width=True, height=400)
            
            # グラフ描画
            sector_cols = [c for c in df.columns if c.startswith("Sector")]
            if sector_cols:
                chart_placeholder.markdown("### 📈 Sector Trends")
                chart_placeholder.line_chart(df[sector_cols])

        else:
            table_placeholder.info("Waiting for data start...")

        time.sleep(0.5)

# ------------------------------------------
#  B. 過去ログ閲覧モード
# ------------------------------------------
elif mode == "📂 過去ログ閲覧":
    st.session_state["current_mode"] = mode
    st.title("📂 History Viewer")
    
    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
        files.sort(reverse=True)
    else:
        files = []

    if not files:
        st.info("まだ記録されたデータがありません。")
    else:
        selected_file = st.selectbox("日付を選択してください", files)
        
        if selected_file:
            file_path = os.path.join(DATA_DIR, selected_file)
            try:
                df = pd.read_csv(file_path)
                if "Lap" in df.columns:
                    df.set_index("Lap", inplace=True)
                
                def sort_cols(col_name):
                    if col_name == "Timestamp": return -1
                    if col_name == "Total Time": return 0
                    if col_name.startswith("Sector"):
                        try: return int(col_name.split(" ")[1])
                        except: return 999
                    return 999
                df = df[sorted(df.columns, key=sort_cols)]

                st.markdown(f"### 📅 {selected_file}")
                
                numeric_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
                styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", subset=numeric_cols, na_rep="--")
                st.dataframe(styled_df, use_container_width=True, height=400)
                
                st.markdown("### 📈 Sector Trends")
                sector_cols = [c for c in df.columns if c.startswith("Sector")]
                if sector_cols:
                    st.line_chart(df[sector_cols])
                
                with open(file_path, "rb") as f:
                    st.download_button("📥 CSVをダウンロード", f, file_name=selected_file, mime="text/csv")
            except Exception as e:
                st.error(f"エラー: {e}")

