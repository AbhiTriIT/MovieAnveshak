import os
import sqlite3
import random
import string
import datetime
import streamlit as st
from fpdf import FPDF
import qrcode
from PIL import Image

# --- Page Setup ---
st.set_page_config(page_title="Python Cinema Booking System", layout="wide")

DB_PATH = "cinema.db"
PRICES = {"Gold": 20.0, "Silver": 15.0, "Standard": 10.0}
ROWS = "ABCDEFGHIJ"

def get_db_connection():
    return sqlite3.connect(DB_PATH)

# ==========================================
# 1. DATABASE INITIALIZATION
# ==========================================
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('SELECT COUNT(*) FROM admin_settings WHERE key="password"')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO admin_settings (key, value) VALUES ("password", "admin123")')

    cursor.execute('''CREATE TABLE IF NOT EXISTS shows 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, show_date TEXT, 
                       show_time TEXT, description TEXT, image_path TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS registered_ids 
                      (user_id TEXT PRIMARY KEY, name TEXT, category TEXT, password TEXT, max_limit INTEGER)''')
                      
    cursor.execute('''CREATE TABLE IF NOT EXISTS booked_seats 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER, seat_num TEXT, user_id TEXT, booking_ref TEXT)''')
    
    cursor.execute('SELECT COUNT(*) FROM shows')
    if cursor.fetchone()[0] == 0:
        default_shows = [
            ('Inception', '2026-11-20', '18:00', 'A thief who steals corporate secrets through the use of dream-sharing technology...', ''),
            ('The Matrix', '2026-11-20', '21:00', 'When a beautiful stranger leads computer hacker Neo to a forbidding underworld...', ''),
            ('Interstellar', '2026-11-21', '19:30', 'A team of explorers travel through a wormhole in space in an attempt to ensure humanity\'s survival.', '')
        ]
        cursor.executemany('INSERT INTO shows (title, show_date, show_time, description, image_path) VALUES (?, ?, ?, ?, ?)', default_shows)
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. PDF & QR UTILITIES
# ==========================================
def generate_receipt_pdf(ref_code, user_name, user_id, user_category, show_title, seats, total_cost):
    qr_payload = f"VERIFIED TICKET\nRef: {ref_code}\nUser: {user_name} ({user_id})\nShow: {show_title}\nSeats: {', '.join(sorted(seats))}"
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    os.makedirs("temp", exist_ok=True)
    temp_qr_path = os.path.join("temp", f"qr_{ref_code}.png")
    qr_img.save(temp_qr_path)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="PYTHON CINEMA - OFFICIAL TICKET", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(200, 10, txt="-"*50, ln=True, align='C')
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt=f"VERIFICATION CODE: {ref_code}", ln=True, align='C')
    
    pdf.ln(10)
    pdf.cell(130, 10, txt=f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    pdf.cell(130, 10, txt=f"Name: {user_name} (ID: {user_id})", ln=True)
    pdf.cell(130, 10, txt=f"Tier: {user_category}", ln=True)
    
    pdf.ln(5)
    pdf.cell(130, 10, txt=f"SHOW DETAILS: {show_title}", ln=True)
    pdf.cell(130, 10, txt=f"SEATS BOOKED: {', '.join(sorted(seats))}", ln=True)
    pdf.cell(130, 10, txt=f"TOTAL PAID: ${total_cost:.2f}", ln=True)
    
    pdf.image(temp_qr_path, x=140, y=40, w=50)
    
    pdf_path = os.path.join("temp", f"Ticket_{ref_code}.pdf")
    pdf.output(pdf_path)
    
    if os.path.exists(temp_qr_path):
        os.remove(temp_qr_path)
        
    return pdf_path

# ==========================================
# 3. SESSION MANAGEMENT & NAVIGATION
# ==========================================
if "role" not in st.session_state:
    st.session_state.role = "landing"
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "current_page" not in st.session_state:
    st.session_state.current_page = None

def logout():
    st.session_state.role = "landing"
    st.session_state.user_data = None
    st.session_state.current_page = None
    st.rerun()

# ==========================================
# 4. PORTAL VIEWS
# ==========================================

# LANDING PAGE
if st.session_state.role == "landing":
    st.title("🎬 Cinema Web Booking System")
    st.subheader("Please select your portal below")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👤 User Portal", use_container_width=True):
            st.session_state.role = "user_login"
            st.rerun()
    with col2:
        if st.button("⚙️ Admin Portal", use_container_width=True):
            st.session_state.role = "admin_login"
            st.rerun()

# ADMIN LOGIN
elif st.session_state.role == "admin_login":
    st.subheader("⚙️ Admin Login")
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        conn = get_db_connection()
        real_pwd = conn.execute("SELECT value FROM admin_settings WHERE key='password'").fetchone()[0]
        conn.close()
        if password == real_pwd:
            st.session_state.role = "admin_dashboard"
            st.rerun()
        else:
            st.error("Incorrect Admin Password.")
    if st.button("← Back to Home"):
        st.session_state.role = "landing"
        st.rerun()

# ADMIN DASHBOARD
elif st.session_state.role == "admin_dashboard":
    st.title("⚙️ Admin Dashboard")
    if st.button("Logout", type="secondary"):
        logout()
        
    tab1, tab2, tab3, tab4 = st.tabs(["Manage Shows", "Manage Users", "Door Manifest & Bookings", "Settings"])
    
    # Tab 1: Manage Shows
    with tab1:
        st.subheader("Current Shows")
        conn = get_db_connection()
        shows = conn.execute("SELECT * FROM shows").fetchall()
        
        with st.expander("+ Add New Show"):
            new_title = st.text_input("Movie Title")
            new_date = st.text_input("Date (YYYY-MM-DD)", value="2026-11-20")
            new_time = st.text_input("Time (HH:MM)", value="18:00")
            new_desc = st.text_area("Synopsis/Description")
            new_poster = st.file_uploader("Upload Poster", type=["png", "jpg", "jpeg"])
            
            if st.button("Save New Show"):
                img_name = ""
                if new_poster:
                    os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
                    img_name = new_poster.name
                    with open(os.path.join("static", "uploads", img_name), "wb") as f:
                        f.write(new_poster.getbuffer())
                conn.execute("INSERT INTO shows (title, show_date, show_time, description, image_path) VALUES (?, ?, ?, ?, ?)",
                             (new_title, new_date, new_time, new_desc, img_name))
                conn.commit()
                st.success("Show added successfully!")
                st.rerun()

        for s in shows:
            col_img, col_info, col_act = st.columns([1, 3, 2])
            with col_img:
                if s[5] and os.path.exists(os.path.join("static", "uploads", s[5])):
                    st.image(os.path.join("static", "uploads", s[5]), width=80)
                else:
                    st.write("No Poster")
            with col_info:
                st.markdown(f"**{s[1]}** — {s[2]} at {s[3]}")
                st.caption(s[4])
            with col_act:
                if st.button(f"Delete Show {s[0]}", key=f"del_show_{s[0]}"):
                    conn.execute("DELETE FROM shows WHERE id=?", (s[0],))
                    conn.execute("DELETE FROM booked_seats WHERE show_id=?", (s[0],))
                    conn.commit()
                    st.rerun()
        conn.close()

    # Tab 2: Manage Users
    with tab2:
        st.subheader("Registered Users")
        conn = get_db_connection()
        
        with st.expander("+ Generate New User"):
            u_name = st.text_input("Full Name")
            u_cat = st.selectbox("Access Tier", ["Standard", "Silver", "Gold"])
            u_lim = st.number_input("Max Booking Limit", min_value=1, value=4)
            if st.button("Generate User ID"):
                new_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                conn.execute("INSERT INTO registered_ids (user_id, name, category, password, max_limit) VALUES (?, ?, ?, ?, ?)",
                             (new_id, u_name, u_cat, "1234", u_lim))
                conn.commit()
                st.success(f"Generated User ID: {new_id} | Temp Pass: 1234")
                st.rerun()
                
        users = conn.execute("SELECT user_id, name, category, max_limit FROM registered_ids").fetchall()
        for u in users:
            col_u1, col_u2, col_u3, col_u4 = st.columns([2, 1, 2, 1])
            with col_u1:
                st.write(f"ID: **{u[0]}** | Name: {u[1]}")
                st.write(f"Tier: {u[2]} | Current Limit: {u[3]}")
            with col_u2:
                new_limit = st.number_input("New Limit", min_value=1, value=u[3], key=f"lim_in_{u[0]}")
            with col_u3:
                if st.button("Update Limit", key=f"upd_lim_{u[0]}"):
                    conn = get_db_connection()
                    conn.execute("UPDATE registered_ids SET max_limit=? WHERE user_id=?", (new_limit, u[0]))
                    conn.commit()
                    conn.close()
                    st.toast(f"Limit for {u[0]} updated to {new_limit}!")
                    st.rerun()
            with col_u4:
                if st.button("Delete User", key=f"del_usr_{u[0]}", type="primary"):
                    conn.execute("DELETE FROM registered_ids WHERE user_id=?", (u[0],))
                    conn.commit()
                    st.rerun()
        conn.close()

    # Tab 3: Door Manifest & Bookings
    with tab3:
        st.subheader("Door Verification Manifest")
        conn = get_db_connection()
        shows_list = conn.execute("SELECT id, title FROM shows").fetchall()
        show_options = {s[1]: s[0] for s in shows_list}
        selected_show_name = st.selectbox("Filter by Show", ["-- All Shows --"] + list(show_options.keys()))
        
        query = '''SELECT b.booking_ref, s.title, b.seat_num, b.user_id, r.name, b.show_id
                   FROM booked_seats b 
                   JOIN shows s ON b.show_id = s.id 
                   JOIN registered_ids r ON b.user_id = r.user_id'''
        
        if selected_show_name != "-- All Shows --":
            query += f" WHERE b.show_id = {show_options[selected_show_name]}"
            
        bookings = conn.execute(query).fetchall()
        for b in bookings:
            col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
            with col_b1:
                st.write(f"Ref: **{b[0]}** | Seat: **{b[2]}**")
                st.caption(f"Show: {b[1]}")
            with col_b2:
                st.write(f"User: {b[4]} ({b[3]})")
            with col_b3:
                new_seat = st.text_input("Move Seat", key=f"move_txt_{b[0]}_{b[2]}", max_chars=4).upper()
                if st.button("Change", key=f"move_btn_{b[0]}_{b[2]}"):
                    if new_seat:
                        conn.execute("UPDATE booked_seats SET seat_num=? WHERE booking_ref=? AND seat_num=?", (new_seat, b[0], b[2]))
                        conn.commit()
                        st.rerun()
                if st.button("Cancel Seat", key=f"can_btn_{b[0]}_{b[2]}"):
                    conn.execute("DELETE FROM booked_seats WHERE booking_ref=? AND seat_num=?", (b[0], b[2]))
                    conn.commit()
                    st.rerun()
        conn.close()

    # Tab 4: Settings
    with tab4:
        st.subheader("Change Admin Password")
        new_admin_p = st.text_input("New Admin Password", type="password")
        if st.button("Update Password"):
            if new_admin_p:
                conn = get_db_connection()
                conn.execute("UPDATE admin_settings SET value=? WHERE key='password'", (new_admin_p,))
                conn.commit()
                conn.close()
                st.success("Admin password successfully updated.")

# USER LOGIN
elif st.session_state.role == "user_login":
    st.subheader("👤 User Portal Login")
    u_id = st.text_input("Booking ID (6 characters)").strip().upper()
    u_pass = st.text_input("Password", type="password")
    
    if st.button("Login", type="primary"):
        conn = get_db_connection()
        user = conn.execute("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=? AND password=?", (u_id, u_pass)).fetchone()
        conn.close()
        if user:
            st.session_state.user_data = user
            st.session_state.role = "user_dashboard"
            st.rerun()
        else:
            st.error("Invalid ID or Password.")
            
    if st.button("← Back to Home"):
        st.session_state.role = "landing"
        st.rerun()

# USER DASHBOARD
elif st.session_state.role == "user_dashboard":
    # Refresh user data to grab any admin-modified max_limit
    conn = get_db_connection()
    user = conn.execute("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=?", (st.session_state.user_data[0],)).fetchone()
    conn.close()
    
    st.title(f"Welcome, {user[1]}!")
    st.markdown(f"Access Tier: **{user[2]}** | Account ID: `{user[0]}`")
    
    if st.button("Logout"):
        logout()
        
    utab1, utab2, utab3 = st.tabs(["Now Showing", "My Tickets & Receipts", "Account Settings"])
    
    # Tab 1: Now Showing / Seat Booking
    with utab1:
        if st.session_state.current_page is None:
            conn = get_db_connection()
            shows = conn.execute("SELECT * FROM shows").fetchall()
            conn.close()
            
            for s in shows:
                with st.container():
                    st.markdown("---")
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        if s[5] and os.path.exists(os.path.join("static", "uploads", s[5])):
                            st.image(os.path.join("static", "uploads", s[5]), use_container_width=True)
                        else:
                            st.write("🎬 [No Image]")
                    with col2:
                        st.subheader(s[1])
                        st.write(f"📅 **Date:** {s[2]} | ⏰ **Time:** {s[3]}")
                        st.write(s[4])
                        if st.button(f"Book Seats for {s[1]}", key=f"book_page_{s[0]}"):
                            st.session_state.current_page = ("book", s[0], s[1])
                            st.rerun()
        else:
            # Interactive Seat Booking System Screen 
            page_type, show_id, show_title = st.session_state.current_page
            st.subheader(f"Booking Map: {show_title}")
            
            conn = get_db_connection()
            booked = [r[0] for r in conn.execute("SELECT seat_num FROM booked_seats WHERE show_id=?", (show_id,)).fetchall()]
            user_booked_count = len(conn.execute("SELECT seat_num FROM booked_seats WHERE show_id=? AND user_id=?", (show_id, user[0])).fetchall())
            conn.close()
            
            remaining_quota = user[4] - user_booked_count
            st.info(f"Your Tier Quota remaining: {remaining_quota} seats (Max allowance: {user[4]})")
            
            # Wrap the entire seat selection in an st.form to stop page reloads on every click
            with st.form(key=f"seat_booking_form_{show_id}"):
                
                # FIXED TYPO HERE
                st.markdown("<div style='background-color:black;color:white;text-align:center;padding:10px;'>SCREEN</div><br>", unsafe_allow_html=True)
                
                selected_seats = []
                
                # Draw the interactive grid matrix matching rows A-J and 1-28 columns
                for row in ROWS:
                    cat = 'Gold' if row == 'J' else ('Silver' if row in ['G','H','I'] else 'Standard')
                    is_disabled = (cat != user[2])
                    
                    cols = st.columns(30)
                    cols[0].write(f"**{row}**")
                    
                    for c in range(1, 29):
                        seat_id = f"{row}{c}"
                        col_index = c if c <= 14 else c + 1  
                        
                        with cols[col_index]:
                            if seat_id in booked:
                                st.markdown("🔴") # Booked
                            elif is_disabled:
                                st.markdown("⚪") # Not allowed for tier
                            else:
                                # Render Checkbox. State is captured on form submission.
                                if st.checkbox(f"{c}", key=f"chk_{seat_id}", label_visibility="collapsed"):
                                    selected_seats.append(seat_id)
                                
                    cols[29].write(f"**{row}**")
                    
                st.write("")
                
                # The form submit button processes all the checkboxes at once
                submitted = st.form_submit_button("Confirm & Pay Booking", type="primary")
                
                if submitted:
                    if not selected_seats:
                        st.error("No seats selected.")
                    elif len(selected_seats) > remaining_quota:
                        st.error(f"You selected {len(selected_seats)} seats, but your remaining tier quota is only {remaining_quota}.")
                    else:
                        # Save Bookings
                        conn = get_db_connection()
                        booking_ref = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        for seat in selected_seats:
                            conn.execute("INSERT INTO booked_seats (show_id, seat_num, user_id, booking_ref) VALUES (?, ?, ?, ?)",
                                         (show_id, seat, user[0], booking_ref))
                        conn.commit()
                        conn.close()
                        st.success("Booking saved successfully! Check the 'Tickets & Receipts' tab to fetch your receipt.")
                        st.session_state.current_page = None
                        st.rerun()
                        
            # Outside the form (Cancel button)
            if st.button("Cancel & Go Back"):
                st.session_state.current_page = None
                st.rerun()

    # Tab 2: Tickets Management
    with utab2:
        st.subheader("My Past Bookings")
        conn = get_db_connection()
        query = '''SELECT b.booking_ref, s.title, s.show_date, s.show_time, GROUP_CONCAT(b.seat_num, ', ')
                   FROM booked_seats b JOIN shows s ON b.show_id = s.id
                   WHERE b.user_id = ? GROUP BY b.booking_ref'''
        my_books = conn.execute(query, (user[0],)).fetchall()
        conn.close()
        
        for mb in my_books:
            st.markdown(f"**Receipt Reference:** `{mb[0]}`")
            st.write(f"🎬 Movie: {mb[1]} | ⏰ {mb[2]} at {mb[3]}")
            st.write(f"🎟️ Seats: {mb[4]}")
            
            seats_arr = mb[4].split(", ")
            cost = len(seats_arr) * PRICES.get(user[2], 10)
            full_title_str = f"{mb[1]} ({mb[2]} {mb[3]})"
            
            pdf_out = generate_receipt_pdf(mb[0], user[1], user[0], user[2], full_title_str, seats_arr, cost)
            
            with open(pdf_out, "rb") as pdf_file:
                st.download_button(label="📥 Download PDF Ticket Receipt", 
                                   data=pdf_file, 
                                   file_name=f"Ticket_{mb[0]}.pdf", 
                                   mime="application/pdf", 
                                   key=f"dl_{mb[0]}")
            st.markdown("---")

    # Tab 3: Account Settings
    with utab3:
        st.subheader("Change Password")
        old_p = st.text_input("Current Password", type="password", key="u_old")
        new_p = st.text_input("New Password", type="password", key="u_new")
        if st.button("Update Profile Password"):
            if old_p != user[3]:
                st.error("Incorrect current password.")
            elif new_p:
                conn = get_db_connection()
                conn.execute("UPDATE registered_ids SET password=? WHERE user_id=?", (new_p, user[0]))
                conn.commit()
                conn.close()
                st.success("Password changed successfully!")
