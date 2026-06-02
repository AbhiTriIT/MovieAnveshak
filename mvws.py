import os
import psycopg2
import random
import string
import datetime
import streamlit as st
from fpdf import FPDF
import qrcode
from PIL import Image

# --- Page Setup ---
st.set_page_config(page_title="Python Cinema Booking System", layout="wide")

PRICES = {"Gold": 20.0, "Silver": 15.0, "Standard": 10.0}
ROWS = "ABCDEFGHIJ"

# ==========================================
# 1. DATABASE UTILITIES (PostgreSQL via Supabase)
# ==========================================
def run_query(query, params=None, fetch=None, execute_many=False):
    """Helper function to cleanly execute database queries."""
    # CORRECT
    conn = psycopg2.connect(st.secrets["DATABASE_URL"])
    conn.autocommit = True
    cursor = conn.cursor()
    
    try:
        if execute_many and params:
            cursor.executemany(query, params)
        elif params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        result = None
        if fetch == "one":
            result = cursor.fetchone()
        elif fetch == "all":
            result = cursor.fetchall()
            
        return result
    finally:
        cursor.close()
        conn.close()

def init_db():
    run_query('''CREATE TABLE IF NOT EXISTS admin_settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    count_admin = run_query("SELECT COUNT(*) FROM admin_settings WHERE key='password'", fetch="one")[0]
    if count_admin == 0:
        run_query("INSERT INTO admin_settings (key, value) VALUES ('password', 'admin123')")

    run_query('''CREATE TABLE IF NOT EXISTS shows 
                 (id SERIAL PRIMARY KEY, title TEXT, show_date TEXT, 
                  show_time TEXT, description TEXT, image_path TEXT)''')
                  
    # --- NEW: Safely add the status column to existing tables ---
    run_query("ALTER TABLE shows ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    
    run_query('''CREATE TABLE IF NOT EXISTS registered_ids 
                 (user_id TEXT PRIMARY KEY, name TEXT, category TEXT, password TEXT, max_limit INTEGER)''')
                      
    run_query('''CREATE TABLE IF NOT EXISTS booked_seats 
                 (id SERIAL PRIMARY KEY, show_id INTEGER, seat_num TEXT, user_id TEXT, booking_ref TEXT)''')
    
    count_shows = run_query("SELECT COUNT(*) FROM shows", fetch="one")[0]
    if count_shows == 0:
        default_shows = [
            ('Inception', '2026-11-20', '18:00', 'A thief who steals corporate secrets...', '', True),
            ('The Matrix', '2026-11-20', '21:00', 'When a beautiful stranger leads...', '', True),
            ('Interstellar', '2026-11-21', '19:30', 'A team of explorers travel...', '', True)
        ]
        run_query("INSERT INTO shows (title, show_date, show_time, description, image_path, is_active) VALUES (%s, %s, %s, %s, %s, %s)", default_shows, execute_many=True)
# Initialize the database on startup
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

def generate_users_pdf():
    users = run_query("SELECT user_id, name, category, max_limit FROM registered_ids", fetch="all")
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="CINEMA REGISTERED USERS", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 10, "User ID", 1)
    pdf.cell(70, 10, "Full Name", 1)
    pdf.cell(40, 10, "Access Tier", 1)
    pdf.cell(30, 10, "Seat Limit", 1, ln=True)
    
    pdf.set_font("Arial", '', 10)
    for u in users:
        pdf.cell(30, 10, str(u[0]), 1)
        pdf.cell(70, 10, str(u[1])[:30], 1)
        pdf.cell(40, 10, str(u[2]), 1)
        pdf.cell(30, 10, str(u[3]), 1, ln=True)
        
    os.makedirs("temp", exist_ok=True)
    pdf_path = os.path.join("temp", "Cinema_Users.pdf")
    pdf.output(pdf_path)
    return pdf_path

def generate_manifest_pdf(show_id, show_title, show_date):
    query = '''SELECT b.booking_ref, b.seat_num, r.name, b.user_id
               FROM booked_seats b JOIN registered_ids r ON b.user_id = r.user_id
               WHERE b.show_id = %s ORDER BY b.booking_ref, b.seat_num'''
    bookings = run_query(query, (show_id,), fetch="all")
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="CINEMA DOOR VERIFICATION MANIFEST", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(200, 10, txt=f"Show: {show_title} ({show_date})", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 10, "Ref Code", 1)
    pdf.cell(20, 10, "Seat", 1)
    pdf.cell(80, 10, "Customer Name", 1)
    pdf.cell(30, 10, "User ID", 1, ln=True)
    
    pdf.set_font("Arial", '', 10)
    for b in bookings:
        pdf.cell(30, 10, str(b[0]), 1)
        pdf.cell(20, 10, str(b[1]), 1)
        pdf.cell(80, 10, str(b[2])[:30], 1)
        pdf.cell(30, 10, str(b[3]), 1, ln=True)
        
    os.makedirs("temp", exist_ok=True)
    pdf_path = os.path.join("temp", f"Manifest_Show_{show_id}.pdf")
    pdf.output(pdf_path)
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
        real_pwd = run_query("SELECT value FROM admin_settings WHERE key='password'", fetch="one")[0]
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
   # Tab 1: Manage Shows
    with tab1:
        st.subheader("Current Shows")
        shows = run_query("SELECT * FROM shows ORDER BY id", fetch="all")
        
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
                
                run_query("INSERT INTO shows (title, show_date, show_time, description, image_path) VALUES (%s, %s, %s, %s, %s)",
                          (new_title, new_date, new_time, new_desc, img_name))
                st.success("Show added successfully!")
                st.rerun()

       # Look for this loop in Tab 1 and replace it:
        for s in shows:
            col_img, col_info, col_act = st.columns([1, 2, 3])
            
            with col_img:
                if s[5] and os.path.exists(os.path.join("static", "uploads", s[5])):
                    st.image(os.path.join("static", "uploads", s[5]), width=100)
                else:
                    st.write("No Poster")
                    
            with col_info:
                st.markdown(f"**{s[1]}** — {s[2]} at {s[3]}")
                st.caption(s[4])
                
                # Show Current Status Badge
                if s[6]: # s[6] is the new is_active column
                    st.success("🟢 Bookings Open")
                else:
                    st.error("🔴 Bookings Closed")
                
            with col_act:
                # --- NEW TOGGLE BUTTON ---
                btn_label = "Disable Bookings" if s[6] else "Enable Bookings"
                if st.button(btn_label, key=f"tog_{s[0]}"):
                    new_status = not s[6]
                    run_query("UPDATE shows SET is_active=%s WHERE id=%s", (new_status, s[0]))
                    st.toast(f"Status for '{s[1]}' updated!")
                    st.rerun()

                with st.expander(f"✏️ Edit Show Details"):
                    edit_desc = st.text_area("Update Description", value=s[4], key=f"edit_desc_{s[0]}")
                    edit_poster = st.file_uploader("Update Poster", type=["png", "jpg", "jpeg"], key=f"edit_poster_{s[0]}")
                    
                    if st.button("💾 Save Changes", key=f"save_edit_{s[0]}", type="primary"):
                        if edit_poster:
                            os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
                            new_img_name = f"updated_{s[0]}_{edit_poster.name}"
                            with open(os.path.join("static", "uploads", new_img_name), "wb") as f:
                                f.write(edit_poster.getbuffer())
                            run_query("UPDATE shows SET description=%s, image_path=%s WHERE id=%s", (edit_desc, new_img_name, s[0]))
                        else:
                            run_query("UPDATE shows SET description=%s WHERE id=%s", (edit_desc, s[0]))
                        st.toast("Updated!")
                        st.rerun()

                if st.button(f"🗑️ Delete Show", key=f"del_show_{s[0]}"):
                    run_query("DELETE FROM shows WHERE id=%s", (s[0],))
                    run_query("DELETE FROM booked_seats WHERE show_id=%s", (s[0],))
                    st.rerun()
            st.markdown("---")
    # Tab 2: Manage Users
    with tab2:
        st.subheader("Registered Users")
        
        col_btn1, col_btn2 = st.columns([1, 3])
        with col_btn1:
            users_pdf_path = generate_users_pdf()
            with open(users_pdf_path, "rb") as f:
                st.download_button("📥 Export Users PDF", f, file_name="Cinema_Users.pdf", mime="application/pdf")
                
        with st.expander("+ Generate New User"):
            u_name = st.text_input("Full Name")
            u_cat = st.selectbox("Access Tier", ["Standard", "Silver", "Gold"])
            u_lim = st.number_input("Max Booking Limit", min_value=1, value=4)
            if st.button("Generate User ID"):
                new_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                run_query("INSERT INTO registered_ids (user_id, name, category, password, max_limit) VALUES (%s, %s, %s, %s, %s)",
                          (new_id, u_name, u_cat, "1234", u_lim))
                st.success(f"Generated User ID: {new_id} | Temp Pass: 1234")
                st.rerun()
                
        st.markdown("---")
        search_query = st.text_input("🔍 Search User by Name or ID", "")
        
        if search_query:
            query = "SELECT user_id, name, category, max_limit FROM registered_ids WHERE name ILIKE %s OR user_id ILIKE %s"
            search_param = f"%{search_query}%"
            users = run_query(query, (search_param, search_param), fetch="all")
        else:
            users = run_query("SELECT user_id, name, category, max_limit FROM registered_ids", fetch="all")
            
        for u in users:
            col_u1, col_u2, col_u3, col_u4 = st.columns([2, 1, 2, 1])
            with col_u1:
                st.write(f"ID: **{u[0]}** | Name: {u[1]}")
                st.write(f"Tier: {u[2]} | Current Limit: {u[3]}")
            with col_u2:
                new_limit = st.number_input("New Limit", min_value=1, value=u[3], key=f"lim_in_{u[0]}")
            with col_u3:
                if st.button("Update Limit", key=f"upd_lim_{u[0]}"):
                    run_query("UPDATE registered_ids SET max_limit=%s WHERE user_id=%s", (new_limit, u[0]))
                    st.toast(f"Limit for {u[0]} updated to {new_limit}!")
                    st.rerun()
            with col_u4:
                if st.button("Delete User", key=f"del_usr_{u[0]}", type="primary"):
                    run_query("DELETE FROM registered_ids WHERE user_id=%s", (u[0],))
                    st.rerun()

   
   # Tab 3: Door Manifest & Bookings
    with tab3:
        st.subheader("Door Verification Manifest")
        
        # 1. Added show_time (s[3]) to the database query
        shows_list = run_query("SELECT id, title, show_date, show_time FROM shows ORDER BY show_date, show_time", fetch="all")
        
        # 2. Formatted the dropdown options to show "Title (YYYY-MM-DD @ HH:MM)"
        show_options = {f"{s[1]} ({s[2]} @ {s[3]})": s[0] for s in shows_list}
        
        selected_show_name = st.selectbox("Filter by Show", ["-- All Shows --"] + list(show_options.keys()))
        
        if selected_show_name != "-- All Shows --":
            show_id = show_options[selected_show_name]
            # Find the specific show info based on the selected ID
            show_info = [s for s in shows_list if s[0] == show_id][0]
            
            # 3. Combine date and time for the PDF Header
            date_time_str = f"{show_info[2]} at {show_info[3]}"
            manifest_pdf_path = generate_manifest_pdf(show_id, show_info[1], date_time_str)
            
            with open(manifest_pdf_path, "rb") as f:
                st.download_button("📥 Download Door Manifest (PDF)", f, file_name=f"Manifest_Show_{show_id}.pdf", mime="application/pdf")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        query = '''SELECT b.booking_ref, s.title, b.seat_num, b.user_id, r.name, b.show_id
                   FROM booked_seats b 
                   JOIN shows s ON b.show_id = s.id 
                   JOIN registered_ids r ON b.user_id = r.user_id'''
        
        params = None
        if selected_show_name != "-- All Shows --":
            query += " WHERE b.show_id = %s"
            params = (show_options[selected_show_name],)
            
        bookings = run_query(query, params, fetch="all")
        
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
                        run_query("UPDATE booked_seats SET seat_num=%s WHERE booking_ref=%s AND seat_num=%s", (new_seat, b[0], b[2]))
                        st.rerun()
                if st.button("Cancel Seat", key=f"can_btn_{b[0]}_{b[2]}"):
                    run_query("DELETE FROM booked_seats WHERE booking_ref=%s AND seat_num=%s", (b[0], b[2]))
                    st.rerun()

    # Tab 4: Settings
    with tab4:
        st.subheader("Change Admin Password")
        new_admin_p = st.text_input("New Admin Password", type="password")
        if st.button("Update Password"):
            if new_admin_p:
                run_query("UPDATE admin_settings SET value=%s WHERE key='password'", (new_admin_p,))
                st.success("Admin password successfully updated.")

# USER LOGIN
elif st.session_state.role == "user_login":
    st.subheader("👤 User Portal Login")
    u_id = st.text_input("Booking ID (6 characters)").strip().upper()
    u_pass = st.text_input("Password", type="password")
    
    if st.button("Login", type="primary"):
        user = run_query("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=%s AND password=%s", 
                         (u_id, u_pass), fetch="one")
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
    user = run_query("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=%s", 
                     (st.session_state.user_data[0],), fetch="one")
    
    st.title(f"Welcome, {user[1]}!")
    st.markdown(f"Access Tier: **{user[2]}** | Account ID: `{user[0]}`")
    
    if st.button("Logout"):
        logout()
        
    utab1, utab2, utab3 = st.tabs(["Now Showing", "My Tickets & Receipts", "Account Settings"])
    
    # Tab 1: Now Showing / Seat Booking
    with utab1:
        if st.session_state.current_page is None:
            shows = run_query("SELECT * FROM shows ORDER BY id", fetch="all")
            
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
                        
                        # --- NEW: Check if bookings are active ---
                        if s[6]: # If is_active is True
                            if st.button(f"Book Seats for {s[1]}", key=f"book_page_{s[0]}", type="primary"):
                                st.session_state.current_page = ("book", s[0], s[1])
                                st.rerun()
                        else:
                            st.error("🚫 Bookings are currently closed for this show.")
    # Tab 2: Tickets Management
    with utab2:
        st.subheader("My Past Bookings")
        query = '''SELECT b.booking_ref, s.title, s.show_date, s.show_time, STRING_AGG(b.seat_num, ', ')
                   FROM booked_seats b JOIN shows s ON b.show_id = s.id
                   WHERE b.user_id = %s GROUP BY b.booking_ref, s.title, s.show_date, s.show_time'''
        my_books = run_query(query, (user[0],), fetch="all")
        
        if not my_books:
            st.write("No bookings found.")
            
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
                run_query("UPDATE registered_ids SET password=%s WHERE user_id=%s", (new_p, user[0]))
                st.success("Password changed successfully!")
