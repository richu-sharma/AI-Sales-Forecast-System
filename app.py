import streamlit as st
import mysql.connector
import firebase_admin
from firebase_admin import credentials, db, firestore
from google_auth_oauthlib.flow import Flow
import requests
import pickle
import numpy as np
import hashlib
import os

# PAGE CONFIG

st.set_page_config(page_title="Sales Forecast System", layout="centered")

# ======================================================
# FIREBASE INIT
# ======================================================
if not firebase_admin._apps:
    cred = credentials.Certificate(
        "firebase/sales-forecast-firebase-admin.json"
    )

    firebase_admin.initialize_app(cred, {
        "databaseURL": "https://sales-forecast-96866-default-rtdb.firebaseio.com"
    })

firestore_db = firestore.client()

# ======================================================
# DATABASE
# ======================================================
def connect_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Richa@123",
        database="sales_db"
    )

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ======================================================
# LOAD MODEL
# ======================================================
model = pickle.load(open("model/model.pkl", "rb"))

# ======================================================
# SAVE USER EVERYWHERE
# ======================================================
def save_user_everywhere(user_id, name, email, phone, role):

    db.reference("users/" + str(user_id)).set({
        "id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "role": role
    })

    firestore_db.collection("users").document(str(user_id)).set({
        "id": user_id,
        "name": name,
        "email": email,
        "phone": phone,
        "role": role
    })

# ======================================================
# GOOGLE LOGIN FLOW
# ======================================================
def google_login_flow():

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    flow = Flow.from_client_secrets_file(
        "firebase/sales-forecast-client_secret.json",
        scopes=[
            "https://www.googleapis.com/auth/userinfo.email",
            "openid"
        ],
        redirect_uri="http://localhost:8501/"
    )

    # After Google Redirect
    if "code" in st.query_params:

        flow.fetch_token(code=st.query_params["code"])
        credentials_google = flow.credentials

        user_info = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            params={"access_token": credentials_google.token}
        ).json()

        email = user_info["email"]
        name = user_info.get("name", email.split("@")[0])

        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id,name,phone FROM users WHERE email=%s",
            (email,)
        )
        user = cursor.fetchone()

        if not user:
            cursor.execute("""
                INSERT INTO users(name,email,role)
                VALUES(%s,%s,%s)
            """,(name,email,"user"))
            conn.commit()

            cursor.execute(
                "SELECT id,name,phone FROM users WHERE email=%s",
                (email,)
            )
            user = cursor.fetchone()

        user_id, name, phone = user

        save_user_everywhere(user_id, name, email, phone, "user")

        cursor.close()
        conn.close()

        st.session_state.user_id = user_id
        st.session_state.user_name = name

        st.query_params.clear()
        st.rerun()

    else:
        auth_url, _ = flow.authorization_url(prompt="consent")
        st.markdown(f"[ Continue with Google]({auth_url})")

# ======================================================
# HOME PAGE
# ======================================================
def home():
    st.title("📊 Sales Forecast System")

    col1, col2, col3 = st.columns(3)

    if col1.button("Login"):
        st.session_state.page = "login"
        st.rerun()

    if col2.button("Register"):
        st.session_state.page = "register"
        st.rerun()

    if col3.button("Login with Google"):
        st.session_state.page = "google"
        st.rerun()

# ======================================================
# REGISTER
# ======================================================
def register():

    st.title("Register")

    name = st.text_input("Name")
    email = st.text_input("Email")
    phone = st.text_input("Phone")
    password = st.text_input("Password", type="password")

    if st.button("Register"):

        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE email=%s",(email,))
        if cursor.fetchone():
            st.error("User already exists")
        else:
            cursor.execute("""
                INSERT INTO users(name,email,phone,password,role)
                VALUES(%s,%s,%s,%s,%s)
            """,(name,email,phone,hash_password(password),"user"))
            conn.commit()

            cursor.execute(
                "SELECT id FROM users WHERE email=%s",(email,)
            )
            user_id = cursor.fetchone()[0]

            save_user_everywhere(user_id,name,email,phone,"user")

            st.success("Registered Successfully")
            st.session_state.page = "login"
            st.rerun()

        cursor.close()
        conn.close()

# ======================================================
# LOGIN
# ======================================================
def login():

    st.title("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id,name FROM users
            WHERE email=%s AND password=%s
        """,(email,hash_password(password)))

        user = cursor.fetchone()

        if user:
            st.session_state.user_id = user[0]
            st.session_state.user_name = user[1]
            st.rerun()
        else:
            st.error("Invalid credentials")

        cursor.close()
        conn.close()

# ======================================================
# DASHBOARD
# ======================================================
def dashboard():

    st.title("📈 AI Sales Prediction Dashboard")
    st.sidebar.success("Welcome " + st.session_state.user_name)

    if st.sidebar.button("Logout"):
        st.session_state.user_id = None
        st.session_state.user_name = None
        st.session_state.page = "home"
        st.rerun()

    st.subheader("Enter Product Details")

    col1, col2 = st.columns(2)

    # -------- DATE --------
    sale_date = st.date_input("Select Date")

    year = sale_date.year
    month = sale_date.month
    day = sale_date.day

    # -------- INPUTS --------
    with col1:

        product_category = st.selectbox(
            "Product Category",
            ["Sports", "Toys", "Home Decor", "Fashion", "Electronics"]
        )

        price = st.number_input("Price", min_value=0.0)
        discount = st.number_input("Discount %", min_value=0.0)

    with col2:

        customer_segment = st.selectbox(
            "Customer Segment",
            ["Regular", "Premium", "Occasional"]
        )

        marketing_spend = st.number_input("Marketing Spend", min_value=0.0)
        units_sold = st.number_input("Units Sold", min_value=0)

    # -------- ENCODING --------

    category_map = {
        "Electronics":0,
        "Fashion":1,
        "Home Decor":2,
        "Sports":3,
        "Toys":4
    }

    segment_map = {
        "Occasional":0,
        "Premium":1,
        "Regular":2
    }

    cat = category_map[product_category]
    seg = segment_map[customer_segment]

    # -------- PREDICTION --------

    if st.button("Predict Sales"):

        features = np.array([[
            year,
            month,
            day,
            cat,
            price,
            discount,
            seg,
            marketing_spend,
            units_sold
        ]])

        prediction = model.predict(features)

        predicted_sales = float(prediction[0])

        # -------- SALES LEVEL --------
        if predicted_sales > 25000:
            level = "🔥 Very High Sales"
        elif predicted_sales > 15000:
            level = "📈 Good Sales"
        elif predicted_sales > 7000:
            level = "📊 Moderate Sales"
        else:
            level = "⚠ Low Sales"

        # -------- SAVE REPORT --------

        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports(user_id,current_sales,predicted_sales)
            VALUES(%s,%s,%s)
        """,(st.session_state.user_id, units_sold, predicted_sales))

        conn.commit()
        cursor.close()
        conn.close()

        st.success(f"Predicted Sales: ₹{predicted_sales:,.2f}")
        st.info(level)
# ======================================================
# SESSION DEFAULT
# ======================================================
if "page" not in st.session_state:
    st.session_state.page = "home"

# ======================================================
# ROUTING
# ======================================================
if st.session_state.get("user_id"):
    dashboard()

elif "code" in st.query_params:
    google_login_flow()

elif st.session_state.page == "login":
    login()

elif st.session_state.page == "register":
    register()

elif st.session_state.page == "google":
    google_login_flow()

else:
    home()