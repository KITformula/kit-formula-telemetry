import streamlit as st
import pandas as pd
import json
import time
import paho.mqtt.client as mqtt
import os
from datetime import datetime

# --- 設定 ---
MQTT_BROKER = "8560a3bce8ff43bb92829fea55036ac1.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "kitformula"
MQTT_PASSWORD = "Kitformula-2026"
TOPIC = "vehicle/telemetry/#"

# データ保存先フォルダ
DATA_DIR = "lap_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

st.set_page_config(page_title="KitFormula Telemetry", layout="wide")

# --- 関数: CSVへの保存 ---
def save_lap_record(record):
    """ラップデータを日付ごとのCSVに追記保存する"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(DATA_DIR, f"laps_{today_str}.csv")
    
    df = pd.DataFrame([record])
    
    # ファイルがなければヘッダー付きで新規作成、あれば追記(header=False)
    if not os.path.exists(file_path):
        df.to_csv(file_path, index=False)
    else:
        df.to_csv(file_path, mode='a', header=False, index=False)

# --- 関数: スタイリング ---
def highlight_bests(df):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    target_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
    
    for col in target_cols:
        try:
            valid_values = pd.to_numeric(df[col], errors='coerce').dropna()
            if valid_values.empty: continue
            
            min_val = valid_values.min()
            for idx in df.index:
                val = df.loc[idx, col]
                if pd.isna(val): continue
                try:
                    if abs(float(val) - min_val) < 0.0001:
                        if col == "Total Time":
                            styles.loc[idx, col] = 'background-color: #006400; color: white; font-weight: bold;'
                        else:
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
        
        # --- 周回更新時の処理 ---
        if current_lc > st.session_state.last_lap_count:
            if st.session_state.last_lap_count > 0:
                llt = payload.get("llt", None)
                
                # 記録用データの作成
                # 時刻も記録しておくと便利
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                last_lap_record = {
                    "Timestamp": timestamp,
                    "Lap": st.session_state.last_lap_count,
                    "Total Time": llt,
                }
                # セクタータイムの転記
                for key, val in current_sectors.items():
                    sector_num = key[1:]
                    last_lap_record[f"Sector {sector_num}"] = val
                
                # 1. メモリ上の履歴に追加 (画面表示用)
                st.session_state.lap_history.append(last_lap_record)
                
                # 2. ファイルに保存 (永続化用) ★ここが追加ポイント
                save_lap_record(last_lap_record)
            
            # リセット
            st.session_state.current_lap_data = {k: v for k, v in st.session_state.current_lap_data.items() if not k.startswith('s')}
            st.session_state.last_lap_count = current_lc

        # --- データ更新 ---
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
#  画面レイアウト (サイドバーでモード切替)
# ==========================================

st.sidebar.title("Menu")
mode = st.sidebar.radio("表示モード", ["リアルタイム計測", "📂 過去ログ閲覧"])

# ------------------------------------------
#  A. リアルタイム計測モード
# ------------------------------------------
if mode == "リアルタイム計測":
    st.title("KIT Real-time Telemetry")
    
    header_metrics = st.empty()
    table_placeholder = st.empty()

    while True:
        # モードが切り替わったらループを抜ける
        # (これがないとサイドバー操作しても画面が変わらない)
        if st.session_state.get("current_mode") != mode:
            st.session_state["current_mode"] = mode
            st.rerun()

        curr = st.session_state.current_lap_data
        lap = st.session_state.last_lap_count
        
        with header_metrics.container():
            st.metric("Current Lap", f"Lap {lap}")

        # データ作成
        data_list = st.session_state.lap_history.copy()
        
        # 現在走行中の行
        current_row = {"Lap": lap, "Total Time": None}
        for key, val in curr.items():
            if key.startswith('s') and key[1:].isdigit():
                current_row[f"Sector {key[1:]}"] = val
        
        display_data = data_list + [current_row]
        
        if len(display_data) > 0:
            df = pd.DataFrame(display_data)
            
            # 数値変換 & ソート
            numeric_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
            for c in numeric_cols:
                df[c] = pd.to_numeric(df[c], errors='coerce')

            # Lapをインデックスに
            if "Lap" in df.columns:
                df.set_index("Lap", inplace=True)
            
            # 列の並び替え
            def sort_cols(col_name):
                if col_name == "Timestamp": return -1
                if col_name == "Total Time": return 0
                if col_name.startswith("Sector"):
                    try: return int(col_name.split(" ")[1])
                    except: return 999
                return 999
            
            sorted_cols = sorted(df.columns, key=sort_cols)
            df = df[sorted_cols]

            try:
                styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", subset=numeric_cols, na_rep="--")
                table_placeholder.dataframe(styled_df, use_container_width=True, height=600)
            except:
                table_placeholder.dataframe(df, use_container_width=True, height=600)
        else:
            table_placeholder.info("Waiting for data start...")

        time.sleep(0.5)

# ------------------------------------------
#  B. 過去ログ閲覧モード
# ------------------------------------------
elif mode == "📂 過去ログ閲覧":
    st.session_state["current_mode"] = mode
    st.title("📂 History Viewer")
    
    # フォルダ内のCSVファイルを探す
    if os.path.exists(DATA_DIR):
        files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
        files.sort(reverse=True) # 新しい順
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
                
                # Lapをインデックスにセット（もし列にあれば）
                if "Lap" in df.columns:
                    df.set_index("Lap", inplace=True)
                
                # 列の並び替え（リアルタイムと同じロジック）
                def sort_cols(col_name):
                    if col_name == "Timestamp": return -1
                    if col_name == "Total Time": return 0
                    if col_name.startswith("Sector"):
                        try: return int(col_name.split(" ")[1])
                        except: return 999
                    return 999
                sorted_cols = sorted(df.columns, key=sort_cols)
                df = df[sorted_cols]

                st.markdown(f"### 📅 {selected_file}")
                
                # 色付けして表示
                numeric_cols = [c for c in df.columns if c == "Total Time" or c.startswith("Sector")]
                styled_df = df.style.apply(highlight_bests, axis=None).format("{:.3f}", subset=numeric_cols, na_rep="--")
                st.dataframe(styled_df, use_container_width=True, height=600)
                
                # ダウンロードボタン
                with open(file_path, "rb") as f:
                    st.download_button(
                        label="📥 CSVをダウンロード",
                        data=f,
                        file_name=selected_file,
                        mime="text/csv"
                    )
            except Exception as e:
                st.error(f"ファイルの読み込みに失敗しました: {e}")

