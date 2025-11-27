import streamlit as st
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt

# --- 設定 ---
MQTT_BROKER = "YOUR_BROKER_URL"  # HiveMQなどのURL
MQTT_PORT = 8883
MQTT_USER = "kitformula"
MQTT_PASSWORD = "YOUR_PASSWORD"
TOPIC = "vehicle/telemetry/#"

# --- 1. セッションステート初期化（履歴保存用） ---
if "lap_history" not in st.session_state:
    # 過去のラップデータを保存するリスト
    # 構造: {'Lap': 1, 'Total Time': 64.5, 'Sector 1': 16.0, ...}
    st.session_state.lap_history = []

if "current_lap_data" not in st.session_state:
    # 現在走行中のラップの一時データ
    st.session_state.current_lap_data = {
        "s1": None, "s2": None, "s3": None, "rpm": 0, "spd": 0
    }

if "last_lap_count" not in st.session_state:
    st.session_state.last_lap_count = 0

# --- 2. MQTT受信コールバック ---
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        
        # 現在のラップ数
        current_lc = payload.get("lc", 0)
        
        # --- 周回が変わった瞬間の処理 ---
        if current_lc > st.session_state.last_lap_count:
            # 前の周回が完了したとみなして履歴に追加
            if st.session_state.last_lap_count > 0:
                # 直前の周の確定データ (llt: Last Lap Time)
                llt = payload.get("llt", None)
                
                # 直前の周のセクタータイム (バッファから取得、なければpayloadから)
                # ※実際は車両側が周回切り替わり時に全セクターを送るか、
                # ここで保持していたデータを使います。今回は簡易的に保持データを使用。
                last_lap_record = {
                    "Lap": st.session_state.last_lap_count,
                    "Total Time": llt,
                    "Sector 1": st.session_state.current_lap_data.get("s1"),
                    "Sector 2": st.session_state.current_lap_data.get("s2"),
                    "Sector 3": st.session_state.current_lap_data.get("s3"), 
                    # Sector3は (Total - S1 - S2) で計算しても良い
                }
                st.session_state.lap_history.append(last_lap_record)
            
            # 新しい周回用に一時データをリセット
            st.session_state.current_lap_data = {"s1": None, "s2": None, "s3": None}
            st.session_state.last_lap_count = current_lc

        # --- 走行中のデータ更新 ---
        # セクタータイムが送られてきたら保存
        if "s1" in payload: st.session_state.current_lap_data["s1"] = payload["s1"]
        if "s2" in payload: st.session_state.current_lap_data["s2"] = payload["s2"]
        if "s3" in payload: st.session_state.current_lap_data["s3"] = payload["s3"]
        
        # RPMなどは表示用
        st.session_state.current_lap_data["rpm"] = payload.get("rpm", 0)
        st.session_state.current_lap_data["spd"] = payload.get("spd", 0)

    except Exception as e:
        print(f"Error: {e}")

# --- 3. MQTT接続 (初回のみ) ---
if "mqtt_client" not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.tls_set()
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.subscribe(TOPIC)
    client.loop_start()
    st.session_state.mqtt_client = client

# --- 4. スタイリング関数 (ここが色の肝) ---
def highlight_bests(df):
    # データフレームと同じ大きさのスタイル指定用DFを作る
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    
    # 数値列だけ抽出
    numeric_cols = ["Total Time", "Sector 1", "Sector 2", "Sector 3"]
    
    for col in numeric_cols:
        if col not in df.columns: continue
        
        # その列の最小値（ベストタイム）を探す
        try:
            min_val = df[col].min()
            
            # 列ごとに判定
            for idx in df.index:
                val = df.loc[idx, col]
                if pd.isna(val): continue
                
                if val == min_val:
                    if col == "Total Time":
                        # トータルベスト = 濃い緑 (#006400), 文字白
                        styles.loc[idx, col] = 'background-color: #006400; color: white; font-weight: bold;'
                    else:
                        # セクターベスト = 薄い緑 (#d0f0c0), 文字黒
                        styles.loc[idx, col] = 'background-color: #d0f0c0; color: black; font-weight: bold;'
        except:
            pass
            
    return styles

# --- 5. 画面描画ループ ---
st.title(" Formula Telemetry")

# プレースホルダー作成
header_metrics = st.empty()
table_placeholder = st.empty()

while True:
    # A. 現在の状態表示
    curr = st.session_state.current_lap_data
    lap = st.session_state.last_lap_count
    
    with header_metrics.container():
        c1, c2, c3 = st.columns(3)
        c1.metric("Current Lap", f"Lap {lap}")
        c2.metric("RPM", curr["rpm"])
        c3.metric("Speed", f"{curr['spd']} km/h")

    # B. テーブルデータの作成
    # 履歴データをコピー
    data_list = st.session_state.lap_history.copy()
    
    # 現在走行中の行を追加 (Running...)
    current_row = {
        "Lap": lap,
        "Total Time": None, # まだ確定してないのでNone
        "Sector 1": curr["s1"],
        "Sector 2": curr["s2"],
        "Sector 3": curr["s3"]
    }
    # 表示用にリストに一時的に足す
    display_data = data_list + [current_row]
    
    if len(display_data) > 0:
        df = pd.DataFrame(display_data)
        
        # スタイリング適用
        # 数値フォーマット指定 (小数点以下3桁など)
        styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", subset=["Total Time", "Sector 1", "Sector 2", "Sector 3"])
        
        # テーブル描画 (use_container_widthで横幅いっぱい)
        table_placeholder.dataframe(styled_df, use_container_width=True, height=400)
    else:
        table_placeholder.info("Waiting for start...")

    time.sleep(0.5) # 更新頻度
