import streamlit as st
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt

# --- 設定 ---
# config.py の設定を反映
MQTT_BROKER = "8560a3bce8ff43bb92829fea55036ac1.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "kitformula"
MQTT_PASSWORD = "Kitformula-2026"
TOPIC = "vehicle/telemetry/#"

st.set_page_config(page_title="KitFormula Telemetry", layout="wide")

# --- 1. セッションステート初期化 ---
if "lap_history" not in st.session_state:
    st.session_state.lap_history = []

if "current_lap_data" not in st.session_state:
    st.session_state.current_lap_data = {
        "s1": None, "s2": None, "s3": None, "rpm": 0, "spd": 0
    }

if "last_lap_count" not in st.session_state:
    st.session_state.last_lap_count = 0

# --- 2. MQTT受信コールバック ---
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        current_lc = payload.get("lc", 0)
        
        # 周回更新時の処理
        if current_lc > st.session_state.last_lap_count:
            if st.session_state.last_lap_count > 0:
                llt = payload.get("llt", None)
                last_lap_record = {
                    "Lap": st.session_state.last_lap_count,
                    "Total Time": llt,
                    "Sector 1": st.session_state.current_lap_data.get("s1"),
                    "Sector 2": st.session_state.current_lap_data.get("s2"),
                    "Sector 3": st.session_state.current_lap_data.get("s3"), 
                }
                st.session_state.lap_history.append(last_lap_record)
            
            st.session_state.current_lap_data = {"s1": None, "s2": None, "s3": None}
            st.session_state.last_lap_count = current_lc

        # データ更新
        if "s1" in payload: st.session_state.current_lap_data["s1"] = payload["s1"]
        if "s2" in payload: st.session_state.current_lap_data["s2"] = payload["s2"]
        if "s3" in payload: st.session_state.current_lap_data["s3"] = payload["s3"]
        
        st.session_state.current_lap_data["rpm"] = payload.get("rpm", 0)
        st.session_state.current_lap_data["spd"] = payload.get("spd", 0)

    except Exception as e:
        print(f"Error: {e}")

# --- 3. MQTT接続 ---
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
        st.toast("Connected to Telemetry!", icon="✅")
    except Exception as e:
        st.error(f"Connection Error: {e}")

# --- 4. スタイリング関数 ---
def highlight_bests(df):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    numeric_cols = ["Total Time", "Sector 1", "Sector 2", "Sector 3"]
    
    for col in numeric_cols:
        if col not in df.columns: continue
        try:
            valid_values = df[col].dropna()
            if valid_values.empty: continue
            
            min_val = valid_values.min()
            for idx in df.index:
                val = df.loc[idx, col]
                if pd.isna(val): continue
                if val == min_val:
                    if col == "Total Time":
                        styles.loc[idx, col] = 'background-color: #006400; color: white; font-weight: bold;'
                    else:
                        styles.loc[idx, col] = 'background-color: #d0f0c0; color: black; font-weight: bold;'
        except:
            pass
    return styles

# --- 5. 画面描画ループ ---
st.title("Formula Telemetry")

header_metrics = st.empty()
table_placeholder = st.empty()

if "mqtt_client" not in st.session_state:
    st.warning("Connecting...")
    time.sleep(1)
    st.rerun()

while True:
    # A. ヘッダー情報
    curr = st.session_state.current_lap_data
    lap = st.session_state.last_lap_count
    
    with header_metrics.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Current Lap", f"Lap {lap}")
        c2.metric("RPM", f"{curr.get('rpm', 0)}")
        c3.metric("Speed", f"{curr.get('spd', 0)} km/h")

    # B. テーブルデータ作成
    data_list = st.session_state.lap_history.copy()
    current_row = {
        "Lap": lap,
        "Total Time": None,
        "Sector 1": curr.get("s1"),
        "Sector 2": curr.get("s2"),
        "Sector 3": curr.get("s3")
    }
    display_data = data_list + [current_row]
    
    if len(display_data) > 0:
        df = pd.DataFrame(display_data)
        
        # ★重要: データを数値型に強制変換（これでNoneがNaNになりエラーが消える）
        cols_to_fix = ["Total Time", "Sector 1", "Sector 2", "Sector 3"]
        for c in cols_to_fix:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        df.set_index("Lap", inplace=True)
        
        # スタイリングして表示
        try:
            styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", na_rep="--")
            table_placeholder.dataframe(styled_df, use_container_width=True, height=400)
        except Exception as e:
            # もしスタイリングでコケても、生の表だけは表示する（安全策）
            table_placeholder.dataframe(df, use_container_width=True, height=400)
            
    else:
        table_placeholder.info("Waiting for data...")

    time.sleep(0.5)
