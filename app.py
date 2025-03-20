import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime
import time
import random
import string
from PIL import Image
import io

# Application configuration
st.set_page_config(
    page_title="学生合コンマッチング",
    page_icon="🍻",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection and initialization
def init_db():
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    # Create users table with gender
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        gender TEXT NOT NULL,
        age INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create requests table with group_size
    c.execute('''
    CREATE TABLE IF NOT EXISTS requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        area TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        group_size INTEGER NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Create matches table
    c.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id_1 INTEGER NOT NULL,
        request_id_2 INTEGER NOT NULL,
        matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (request_id_1) REFERENCES requests (request_id),
        FOREIGN KEY (request_id_2) REFERENCES requests (request_id)
    )
    ''')
    
    # Create messages table
    c.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        sender_user_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (match_id) REFERENCES matches (match_id),
        FOREIGN KEY (sender_user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User registration
def register_user(username, password, gender, age):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    try:
        hashed_password = hash_password(password)
        c.execute("INSERT INTO users (username, password, gender, age) VALUES (?, ?, ?, ?)",
                 (username, hashed_password, gender, age))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# User login
def login_user(username, password):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    hashed_password = hash_password(password)
    c.execute("SELECT user_id, username, gender FROM users WHERE username = ? AND password = ?", 
             (username, hashed_password))
    user = c.fetchone()
    conn.close()
    
    if user:
        return user[0], user[1], user[2]  # Return user_id, username, and gender
    return None, None, None

# Get user details
def get_user_details(user_id):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("SELECT username, gender, age FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {"username": user[0], "gender": user[1], "age": user[2]}
    return None

# Create matching request
def create_request(user_id, area, time_slot, group_size):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    # Check if user has a pending request
    c.execute("SELECT request_id FROM requests WHERE user_id = ? AND status = 'pending'", (user_id,))
    existing_request = c.fetchone()
    
    if existing_request:
        conn.close()
        return False, "既に待機中のリクエストがあります。"
    
    # Get user gender
    c.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,))
    user_gender = c.fetchone()[0]
    
    # Create new request
    c.execute("INSERT INTO requests (user_id, area, time_slot, group_size, status) VALUES (?, ?, ?, ?, 'pending')",
             (user_id, area, time_slot, group_size))
    conn.commit()
    
    # Get the new request ID
    request_id = c.lastrowid
    
    # Find opposite gender for matching
    opposite_gender = "女性" if user_gender == "男性" else "男性"
    
    # Try to find a match with opposite gender
    c.execute("""
    SELECT r.request_id, r.user_id, r.group_size
    FROM requests r
    JOIN users u ON r.user_id = u.user_id
    WHERE r.status = 'pending' 
    AND r.area = ? 
    AND r.time_slot = ? 
    AND r.user_id != ?
    AND u.gender = ?
    ORDER BY r.created_at ASC
    LIMIT 1
    """, (area, time_slot, user_id, opposite_gender))
    
    match = c.fetchone()
    
    if match:
        # Create a match
        match_request_id = match[0]
        match_user_id = match[1]
        match_group_size = match[2]
        
        c.execute("INSERT INTO matches (request_id_1, request_id_2) VALUES (?, ?)",
                 (match_request_id, request_id))
        match_id = c.lastrowid
        
        # Update both requests to matched status
        c.execute("UPDATE requests SET status = 'matched' WHERE request_id IN (?, ?)",
                 (match_request_id, request_id))
        
        conn.commit()
        conn.close()
        
        return True, match_id
    
    conn.close()
    return True, None  # Request created but no match yet

# Get user's active matches
def get_user_matches(user_id):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("""
    SELECT m.match_id, r1.area, r1.time_slot, r1.user_id as match_user_id, u.username, r1.group_size, r2.group_size as my_group_size
    FROM matches m
    JOIN requests r1 ON (m.request_id_1 = r1.request_id)
    JOIN requests r2 ON (m.request_id_2 = r2.request_id)
    JOIN users u ON (CASE WHEN r1.user_id = ? THEN r2.user_id ELSE r1.user_id END = u.user_id)
    WHERE r1.user_id = ? OR r2.user_id = ?
    ORDER BY m.matched_at DESC
    """, (user_id, user_id, user_id))
    
    matches = []
    for row in c.fetchall():
        match_id, area, time_slot, match_user_id, match_username, group_size, my_group_size = row
        
        # Determine which group size is the match's and which is the user's
        if match_user_id == user_id:
            match_group_size = my_group_size
            my_group_size = group_size
        else:
            match_group_size = group_size
        
        matches.append({
            "match_id": match_id,
            "area": area,
            "time_slot": time_slot,
            "match_user_id": match_user_id,
            "match_username": match_username,
            "match_group_size": match_group_size,
            "my_group_size": my_group_size
        })
    
    conn.close()
    return matches

# Get all messages for a match
def get_messages(match_id):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("""
    SELECT m.message_id, m.sender_user_id, u.username, m.message_text, m.timestamp
    FROM messages m
    JOIN users u ON m.sender_user_id = u.user_id
    WHERE m.match_id = ?
    ORDER BY m.timestamp ASC
    """, (match_id,))
    
    messages = []
    for row in c.fetchall():
        message_id, sender_id, sender_username, text, timestamp = row
        messages.append({
            "message_id": message_id,
            "sender_id": sender_id,
            "sender_username": sender_username,
            "text": text,
            "timestamp": timestamp
        })
    
    conn.close()
    return messages

# Send a message
def send_message(match_id, sender_id, message_text):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("INSERT INTO messages (match_id, sender_user_id, message_text) VALUES (?, ?, ?)",
             (match_id, sender_id, message_text))
    
    conn.commit()
    conn.close()
    return True

# Get pending request for a user
def get_pending_request(user_id):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("SELECT request_id, area, time_slot, group_size, created_at FROM requests WHERE user_id = ? AND status = 'pending'", 
             (user_id,))
    request = c.fetchone()
    
    conn.close()
    
    if request:
        return {
            "request_id": request[0],
            "area": request[1],
            "time_slot": request[2],
            "group_size": request[3],
            "created_at": request[4]
        }
    return None

# Cancel a pending request
def cancel_request(request_id):
    conn = sqlite3.connect('meetup_app.db')
    c = conn.cursor()
    
    c.execute("DELETE FROM requests WHERE request_id = ? AND status = 'pending'", (request_id,))
    conn.commit()
    conn.close()
    return True

# UI Components
def show_login_page():
    st.markdown("<h1 style='text-align: center; color: #ff5a5f;'>学生合コンマッチング</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>ログイン</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            username = st.text_input("ユーザー名")
            password = st.text_input("パスワード", type="password")
            
            if st.button("ログイン", key="login_button", use_container_width=True):
                user_id, username, gender = login_user(username, password)
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.username = username
                    st.session_state.gender = gender
                    st.session_state.page = "dashboard"
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが間違っています")
            
            st.markdown("<div style='text-align: center; padding: 10px;'>アカウントをお持ちでない場合は</div>", unsafe_allow_html=True)
            
            if st.button("新規登録へ", key="goto_register", use_container_width=True):
                st.session_state.page = "register"
                st.rerun()

def show_register_page():
    st.markdown("<h1 style='text-align: center; color: #ff5a5f;'>学生合コンマッチング</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>新規登録</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            username = st.text_input("ユーザー名（ログイン用）")
            password = st.text_input("パスワード", type="password")
            confirm_password = st.text_input("パスワード（確認）", type="password")
            gender = st.radio("性別", ["男性", "女性"], horizontal=True)
            age = st.number_input("年齢", min_value=18, max_value=100, value=20)
            
            if st.button("登録", key="register_button", use_container_width=True):
                if password != confirm_password:
                    st.error("パスワードが一致しません")
                elif not username or not password:
                    st.error("すべての項目を入力してください")
                else:
                    success = register_user(username, password, gender, age)
                    if success:
                        st.success("登録が完了しました！ログインしてください。")
                        st.session_state.page = "login"
                        st.rerun()
                    else:
                        st.error("そのユーザー名は既に使用されています")
            
            if st.button("ログインへ戻る", key="back_to_login", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()

def show_dashboard():
    st.markdown(f"<h1 style='text-align: center; color: #ff5a5f;'>こんにちは {st.session_state.username} さん！</h1>", unsafe_allow_html=True)
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["マッチング", "メッセージ", "プロフィール"])
    
    with tab1:
        show_matching_tab()
    
    with tab2:
        show_messages_tab()
    
    with tab3:
        show_profile_tab()

def show_matching_tab():
    st.header("マッチング")
    
    # Check if user has pending request
    pending_request = get_pending_request(st.session_state.user_id)
    
    if pending_request:
        with st.container(border=True):
            st.info(f"現在、{pending_request['area']}の{pending_request['time_slot']}で{pending_request['group_size']}人のマッチングを待っています。")
            
            if st.button("キャンセル", key="cancel_request", use_container_width=True):
                cancel_request(pending_request['request_id'])
                st.success("リクエストをキャンセルしました。")
                st.rerun()
    else:
        with st.container(border=True):
            st.subheader("新しいマッチングリクエスト")
            
            area = st.selectbox("エリア選択", ["池袋", "新宿", "渋谷"])
            time_slot = st.selectbox("時間帯", ["18:00-20:00", "20:00-22:00", "22:00-24:00", "24:00-26:00"])
            group_size = st.number_input("募集人数", min_value=1, max_value=10, value=3)
            
            if st.button("マッチングリクエストを送信", key="send_request", use_container_width=True):
                success, result = create_request(st.session_state.user_id, area, time_slot, group_size)
                
                if not success:
                    st.error(result)  # Error message
                elif result:  # Match found
                    st.success("マッチングが成立しました！")
                    st.session_state.active_match = result
                    st.session_state.page = "chat"
                    st.rerun()
                else:  # No match yet
                    st.success("リクエストを送信しました。マッチングを待っています...")
                    st.rerun()

def show_messages_tab():
    st.header("メッセージ")
    
    matches = get_user_matches(st.session_state.user_id)
    
    if not matches:
        st.info("まだマッチングがありません。")
        return
    
    for match in matches:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**{match['match_username']}** さん")
                st.write(f"エリア: {match['area']} / 時間帯: {match['time_slot']}")
                st.write(f"人数: あなた {match['my_group_size']}人 / 相手 {match['match_group_size']}人")
            
            with col2:
                if st.button("チャットを開く", key=f"chat_{match['match_id']}", use_container_width=True):
                    st.session_state.active_match = match['match_id']
                    st.session_state.page = "chat"
                    st.rerun()

def show_profile_tab():
    st.header("プロフィール")
    
    user = get_user_details(st.session_state.user_id)
    
    if user:
        with st.container(border=True):
            st.write(f"**ユーザー名**: {user['username']}")
            st.write(f"**性別**: {user['gender']}")
            st.write(f"**年齢**: {user['age']}")
        
        if st.button("ログアウト", key="logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

def show_chat_page():
    if "active_match" not in st.session_state:
        st.error("マッチングが選択されていません")
        if st.button("ダッシュボードに戻る", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()
        return
    
    match_id = st.session_state.active_match
    messages = get_messages(match_id)
    
    # Get match details
    matches = get_user_matches(st.session_state.user_id)
    current_match = next((m for m in matches if m["match_id"] == match_id), None)
    
    if not current_match:
        st.error("マッチングが見つかりません")
        if st.button("ダッシュボードに戻る", use_container_width=True):
            st.session_state.page = "dashboard"
            st.rerun()
        return
    
    st.header(f"{current_match['match_username']} さんとのチャット")
    st.subheader(f"{current_match['area']} / {current_match['time_slot']}")
    st.write(f"人数: あなた {current_match['my_group_size']}人 / 相手 {current_match['match_group_size']}人")
    
    # Display messages
    with st.container(border=True):
        for msg in messages:
            is_me = msg["sender_id"] == st.session_state.user_id
            
            if is_me:
                message_container = st.container()
                with message_container:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: flex-end;">
                        <div style="background-color: #dcf8c6; padding: 10px; border-radius: 10px; max-width: 70%;">
                            {msg["text"]}
                            <div style="font-size: 0.8em; color: #888; text-align: right;">
                                {msg["timestamp"]}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                message_container = st.container()
                with message_container:
                    st.markdown(f"""
                    <div style="display: flex; justify-content: flex-start;">
                        <div style="background-color: #f1f0f0; padding: 10px; border-radius: 10px; max-width: 70%;">
                            <strong>{msg["sender_username"]}</strong><br>
                            {msg["text"]}
                            <div style="font-size: 0.8em; color: #888;">
                                {msg["timestamp"]}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    # Send new message
    with st.form(key="message_form"):
        message = st.text_area("メッセージを入力", height=100)
        col1, col2 = st.columns([3, 1])
        with col2:
            submit = st.form_submit_button("送信", use_container_width=True)
        
        if submit and message:
            send_message(match_id, st.session_state.user_id, message)
            st.success("メッセージを送信しました")
            st.rerun()
    
    if st.button("ダッシュボードに戻る", key="back_to_dashboard", use_container_width=True):
        st.session_state.page = "dashboard"
        st.rerun()

def main():
    # Initialize the database
    init_db()
    
    # Initialize session state
    if "page" not in st.session_state:
        st.session_state.page = "login"
    
    # Apply CSS for modern UI
    st.markdown("""
    <style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
        font-family: 'Helvetica Neue', Arial, sans-serif;
    }
    .stButton>button {
        background-color: #ff5a5f;
        color: white;
        border-radius: 25px;
        padding: 10px 20px;
        border: none;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #ff3a3f;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .stTextInput>div>div>input {
        border-radius: 25px;
        border: 1px solid #ddd;
        padding: 10px 15px;
    }
    .stSelectbox>div>div>select {
        border-radius: 25px;
        border: 1px solid #ddd;
        padding: 10px 15px;
    }
    h1, h2, h3 {
        font-weight: 600;
        color: #484848;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 1px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        border-radius: 15px 15px 0 0;
        background-color: #f8f8f8;
        padding: 10px 20px;
        color: #484848;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ff5a5f;
        color: white;
    }
    .stForm [data-testid="stFormSubmitButton"] > button {
        background-color: #ff5a5f;
        color: white;
    }
    [data-testid="stForm"] {
        background-color: #f9f9f9;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Show the appropriate page based on session state
    if st.session_state.page == "login":
        show_login_page()
    elif st.session_state.page == "register":
        show_register_page()
    elif st.session_state.page == "dashboard":
        if "user_id" not in st.session_state:
            st.warning("ログインが必要です")
            st.session_state.page = "login"
            st.rerun()
        else:
            show_dashboard()
    elif st.session_state.page == "chat":
        if "user_id" not in st.session_state:
            st.warning("ログインが必要です")
            st.session_state.page = "login"
            st.rerun()
        else:
            show_chat_page()

if __name__ == "__main__":
    main()
