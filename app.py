import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import os

# 環境変数から設定を読み込む (セキュリティ対策)
BROKER = st.secrets["MQTT_BROKER"]
PORT = int(st.secrets["MQTT_PORT"])
USERNAME = st.secrets["MQTT_USERNAME"]
PASSWORD = st.secrets["MQTT_PASSWORD"]
TOPIC = "vehicle/telemetry/1"

st.set_page_config(page_title="KitFormula Telemetry", page_icon="🏎️", layout="wide")

# セッションステート初期化
if 'telemetry' not in st.session_state:
    st.session_state.telemetry = {}

# MQTTコールバック
def on_message(client, userdata, message):
    try:
        payload = str(message.payload.decode("utf-8"))
        data = json.loads(payload)
        st.session_state.telemetry = data
    except Exception as e:
        print(f"Error: {e}")

@st.cache_resource
def start_mqtt():
    client = mqtt.Client()
    client.tls_set()
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT)
        client.loop_start()
        client.subscribe(TOPIC)
        return client
    except Exception as e:
        st.error(f"MQTT Connection Failed: {e}")
        return None

# 接続開始
start_mqtt()

# --- GUI表示 ---
st.title("🏎️ KitFormula Live Telemetry")

data = st.session_state.telemetry

if data:
    # 3カラムレイアウト
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(label="RPM", value=f"{data.get('rpm', 0)}", delta=None)
        st.metric(label="Speed", value=f"{data.get('spd', 0)} km/h")
    
    with col2:
        st.metric(label="Water Temp", value=f"{data.get('wt', 0)} °C")
        st.metric(label="Oil Temp", value=f"{data.get('ot', 0)} °C")
        
    with col3:
        st.metric(label="Lap Time", value=f"{data.get('clt', 0.0):.2f}")
        st.metric(label="Lap Count", value=data.get('lc', 0))

    st.divider()
    st.caption(f"Raw Data: {data}")

else:
    st.info("Waiting for vehicle data... (Check 4G connection)")

# 1秒ごとに画面をリフレッシュして最新ステートを表示
time.sleep(1)
st.rerun()