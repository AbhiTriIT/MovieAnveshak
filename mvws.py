import os
import psycopg2
import random
import string
import datetime
import streamlit as st
from fpdf import FPDF
import qrcode
from PIL import Image

# --- Page Setup & CSS Injection ---
st.set_page_config(page_title="Cinemagic Booking Portal", page_icon="🍿", layout="wide")

def load_custom_css():
    st.markdown("""
    <style>
        /* Modern Button Styling */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease-in-out;
            border: none;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(255, 75, 75, 0.3);
            border-color: #ff4b4b;
        }
        
        /* Movie Card Styling */
        .movie-card {
            background-color: rgba(255, 255, 255, 0.05);
            border-left: 5px solid #ff4b4b;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        
        /* Screen Indicator styling */
        .cinema-screen {
            background: linear-gradient(90deg, #1f1c2c 0%, #928dab 100%);
            color: white;
            text-align: center;
            padding: 15px;
            border-radius: 10px;
            font-weight: bold;
            letter-spacing: 5px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            margin-bottom: 30px;
        }
        
        /* Tab Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            border-radius: 5px 5px 0 0;
        }
    </style>
    """, unsafe_allow_html=True)

load_custom_css()

PRICES = {"Gold": 20.0, "Silver": 15.0, "Standard": 10.0}
ROWS = "ABCDEFGHIJ"

# ==========================================
# 1. DATABASE UTILITIES
# ==========================================
def run_query(query, params=None, fetch=None, execute_many=False):
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
    if run_query("SELECT COUNT(*) FROM admin_settings WHERE key='password'", fetch="one")[0] == 0:
        run_query("INSERT INTO admin_settings (key, value) VALUES ('password', 'admin123')")

    run_query('''CREATE TABLE IF NOT EXISTS shows 
                 (id SERIAL PRIMARY KEY, title TEXT, show_date TEXT, 
                  show_time TEXT, description TEXT, image_path TEXT)''')
    run_query("ALTER TABLE shows ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    
    run_query('''CREATE TABLE IF NOT EXISTS registered_ids 
                 (user_id TEXT PRIMARY KEY, name TEXT, category TEXT, password TEXT, max_limit INTEGER)''')
                      
    run_query('''CREATE TABLE IF NOT EXISTS booked_seats 
                 (id SERIAL PRIMARY KEY, show_id INTEGER, seat_num TEXT, user_id TEXT, booking_ref TEXT)''')

init_db()

# ==========================================
# 2. PDF UTILITIES
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
    pdf.cell(200, 10, txt="CINEMAGIC - OFFICIAL TICKET", ln=True, align='C')
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
# 3. SESSION MANAGEMENT
# ==========================================
if "role" not in st.session_state: st.session_state.role = "landing"
if "user_data" not in st.session_state: st.session_state.user_data = None
if "current_page" not in st.session_state: st.session_state.current_page = None

def logout():
    for key in ["role", "user_data", "current_page"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# ==========================================
# 4. PORTALS
# ==========================================

# --- LANDING PAGE ---
if st.session_state.role == "landing":
    st.markdown("<h1 style='text-align: center; color: #ff4b4b;'>🍿 Cinemagic Booking Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.2rem;'>Welcome! Please select your destination.</p><br>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
    with col2:
        if st.button("👤 Enter User Portal", use_container_width=True, type="primary"):
            st.session_state.role = "user_login"
            st.rerun()
    with col3:
        if st.button("⚙️ Enter Admin Portal", use_container_width=True):
            st.session_state.role = "admin_login"
            st.rerun()

# --- ADMIN LOGIN ---
elif st.session_state.role == "admin_login":
    st.markdown("<h2>⚙️ Admin Control Panel</h2>", unsafe_allow_html=True)
    with st.container():
        password = st.text_input("Enter Master Password", type="password")
        if st.button("Authenticate", type="primary"):
            real_pwd = run_query("SELECT value FROM admin_settings WHERE key='password'", fetch="one")[0]
            if password == real_pwd:
                st.session_state.role = "admin_dashboard"
                st.toast("✅ Access Granted!")
                st.rerun()
            else:
                st.error("❌ Incorrect Credentials.")
        if st.button("← Return to Home"):
            st.session_state.role = "landing"
            st.rerun()

# --- ADMIN DASHBOARD ---
elif st.session_state.role == "admin_dashboard":
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("Admin Dashboard 📊")
    with col2:
        st.write("") # Spacing
        if st.button("🚪 Secure Logout"): logout()
    
    # KPI Metrics Header
    tot_shows = run_query("SELECT COUNT(*) FROM shows", fetch="one")[0]
    tot_users = run_query("SELECT COUNT(*) FROM registered_ids", fetch="one")[0]
    tot_books = run_query("SELECT COUNT(*) FROM booked_seats", fetch="one")[0]
    
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Active Shows", f"{tot_shows} 🎬")
    m2.metric("Registered Patrons", f"{tot_users} 👥")
    m3.metric("Total Seats Sold", f"{tot_books} 🎟️")
    st.markdown("---")
        
    tab1, tab2, tab3, tab4 = st.tabs(["🎬 Show Manager", "👥 Patron Database", "🎫 Door Manifests", "⚙️ Security"])
    
    with tab1:
        shows = run_query("SELECT * FROM shows ORDER BY id", fetch="all")
        with st.expander("➕ Deploy New Show to Cinema"):
            new_title = st.text_input("Movie Title")
            new_date = st.text_input("Date (YYYY-MM-DD)", value=datetime.date.today().strftime("%Y-%m-%d"))
            new_time = st.text_input("Time (HH:MM)", value="18:00")
            new_desc = st.text_area("Synopsis/Description")
            new_poster = st.file_uploader("Upload Poster Artwork", type=["png", "jpg", "jpeg"])
            
            if st.button("Save & Publish Show"):
                img_name = ""
                if new_poster:
                    os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
                    img_name = new_poster.name
                    with open(os.path.join("static", "uploads", img_name), "wb") as f:
                        f.write(new_poster.getbuffer())
                run_query("INSERT INTO shows (title, show_date, show_time, description, image_path) VALUES (%s, %s, %s, %s, %s)",
                          (new_title, new_date, new_time, new_desc, img_name))
                st.success("✨ Show added successfully!")
                st.rerun()

        st.subheader("Currently Scheduled")
        for s in shows:
            st.markdown(f"<div class='movie-card'>", unsafe_allow_html=True)
            col_img, col_info, col_act = st.columns([1, 2, 2])
            with col_img:
                if s[5] and os.path.exists(os.path.join("static", "uploads", s[5])):
                    st.image(os.path.join("static", "uploads", s[5]), width=120)
                else:
                    st.info("No Poster")
            with col_info:
                st.markdown(f"### {s[1]}")
                st.write(f"📅 {s[2]} &nbsp;|&nbsp; ⏰ {s[3]}")
                if s[6]:
                    st.success("🟢 Sales Open")
                else:
                    st.error("🔴 Sales Suspended")
            with col_act:
                btn_label = "⏸️ Suspend Sales" if s[6] else "▶️ Resume Sales"
                if st.button(btn_label, key=f"tog_{s[0]}"):
                    run_query("UPDATE shows SET is_active=%s WHERE id=%s", (not s[6], s[0]))
                    st.rerun()
                
                with st.expander("✏️ Edit Details"):
                    edit_desc = st.text_area("Update Description", value=s[4], key=f"ed_{s[0]}")
                    edit_poster = st.file_uploader("Update Poster", type=["png", "jpg", "jpeg"], key=f"up_{s[0]}")
                    if st.button("💾 Save Changes", key=f"sv_{s[0]}", type="primary"):
                        if edit_poster:
                            new_img = f"upd_{s[0]}_{edit_poster.name}"
                            with open(os.path.join("static", "uploads", new_img), "wb") as f: f.write(edit_poster.getbuffer())
                            run_query("UPDATE shows SET description=%s, image_path=%s WHERE id=%s", (edit_desc, new_img, s[0]))
                        else:
                            run_query("UPDATE shows SET description=%s WHERE id=%s", (edit_desc, s[0]))
                        st.toast("✅ Updated!")
                        st.rerun()
                        
                if st.button(f"🗑️ Delete Show", key=f"del_{s[0]}"):
                    run_query("DELETE FROM shows WHERE id=%s", (s[0],))
                    run_query("DELETE FROM booked_seats WHERE show_id=%s", (s[0],))
                    st.toast("🗑️ Deleted!")
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        col_btn1, col_btn2 = st.columns([1, 3])
        with col_btn1:
            users_pdf_path = generate_users_pdf()
            with open(users_pdf_path, "rb") as f:
                st.download_button("📥 Export Database PDF", f, file_name="Patrons.pdf", mime="application/pdf")
                
        with st.expander("➕ Generate New Patron ID"):
            u_name = st.text_input("Full Name")
            u_cat = st.selectbox("Tier", ["Standard", "Silver", "Gold"])
            u_lim = st.number_input("Booking Limit", min_value=1, value=4)
            if st.button("Issue ID Card", type="primary"):
                new_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                run_query("INSERT INTO registered_ids (user_id, name, category, password, max_limit) VALUES (%s, %s, %s, %s, %s)",
                          (new_id, u_name, u_cat, "1234", u_lim))
                st.success(f"🎉 Issued! ID: {new_id} | Pass: 1234")
                st.rerun()
                
        search_query = st.text_input("🔍 Search Patron by Name or ID", "")
        if search_query:
            srch = f"%{search_query}%"
            users = run_query("SELECT user_id, name, category, max_limit FROM registered_ids WHERE name ILIKE %s OR user_id ILIKE %s", (srch, srch), fetch="all")
        else:
            users = run_query("SELECT user_id, name, category, max_limit FROM registered_ids", fetch="all")
            
        for u in users:
            col_u1, col_u2, col_u3, col_u4 = st.columns([3, 1, 1, 1])
            with col_u1:
                st.markdown(f"**{u[1]}** (ID: `{u[0]}`)")
                st.caption(f"Tier: {u[2]} | Limit: {u[3]}")
            with col_u2:
                new_limit = st.number_input("Limit", min_value=1, value=u[3], key=f"l_{u[0]}", label_visibility="collapsed")
            with col_u3:
                if st.button("Save", key=f"s_{u[0]}"):
                    run_query("UPDATE registered_ids SET max_limit=%s WHERE user_id=%s", (new_limit, u[0]))
                    st.toast("✅ Updated")
                    st.rerun()
            with col_u4:
                if st.button("Revoke", key=f"d_{u[0]}"):
                    run_query("DELETE FROM registered_ids WHERE user_id=%s", (u[0],))
                    st.rerun()

    with tab3:
        shows_list = run_query("SELECT id, title, show_date, show_time FROM shows ORDER BY show_date, show_time", fetch="all")
        show_options = {f"{s[1]} ({s[2]} @ {s[3]})": s[0] for s in shows_list}
        selected_show_name = st.selectbox("Select Show to Audit", ["-- Entire Database --"] + list(show_options.keys()))
        
        if selected_show_name != "-- Entire Database --":
            show_id = show_options[selected_show_name]
            show_info = [s for s in shows_list if s[0] == show_id][0]
            manifest_pdf_path = generate_manifest_pdf(show_id, show_info[1], f"{show_info[2]} at {show_info[3]}")
            with open(manifest_pdf_path, "rb") as f:
                st.download_button("📥 Print Manifest", f, file_name=f"Manifest_{show_id}.pdf", mime="application/pdf", type="primary")
        
        query = '''SELECT b.booking_ref, s.title, b.seat_num, b.user_id, r.name, b.show_id
                   FROM booked_seats b JOIN shows s ON b.show_id = s.id JOIN registered_ids r ON b.user_id = r.user_id'''
        params = None
        if selected_show_name != "-- Entire Database --":
            query += " WHERE b.show_id = %s"
            params = (show_options[selected_show_name],)
            
        bookings = run_query(query, params, fetch="all")
        for b in bookings:
            col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
            with col_b1:
                st.markdown(f"**Seat {b[2]}** | Ref: `{b[0]}`")
                st.caption(b[1])
            with col_b2:
                st.markdown(f"👤 {b[4]} (`{b[3]}`)")
            with col_b3:
                col_i, col_btn, col_del = st.columns([2, 1, 1])
                new_seat = col_i.text_input("New", key=f"m_{b[0]}_{b[2]}", max_chars=4, label_visibility="collapsed").upper()
                if col_btn.button("Move", key=f"mv_{b[0]}_{b[2]}"):
                    if new_seat:
                        run_query("UPDATE booked_seats SET seat_num=%s WHERE booking_ref=%s AND seat_num=%s", (new_seat, b[0], b[2]))
                        st.rerun()
                if col_del.button("❌", key=f"c_{b[0]}_{b[2]}"):
                    run_query("DELETE FROM booked_seats WHERE booking_ref=%s AND seat_num=%s", (b[0], b[2]))
                    st.rerun()

    with tab4:
        st.info("Update system root password below.")
        new_admin_p = st.text_input("New Secure Password", type="password")
        if st.button("Apply Security Patch", type="primary"):
            if new_admin_p:
                run_query("UPDATE admin_settings SET value=%s WHERE key='password'", (new_admin_p,))
                st.success("🔒 System secured with new credentials.")

# --- USER LOGIN ---
elif st.session_state.role == "user_login":
    st.markdown("<h2 style='text-align:center;'>🎟️ Box Office Login</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        u_id = st.text_input("Patron ID").strip().upper()
        u_pass = st.text_input("PIN / Password", type="password")
        if st.button("Access Box Office", type="primary", use_container_width=True):
            user = run_query("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=%s AND password=%s", (u_id, u_pass), fetch="one")
            if user:
                st.session_state.user_data = user
                st.session_state.role = "user_dashboard"
                st.toast(f"Welcome back, {user[1]}! 🍿")
                st.rerun()
            else:
                st.error("🚫 Identification failed. Check ID/PIN.")
        if st.button("← Back", use_container_width=True):
            st.session_state.role = "landing"
            st.rerun()

# --- USER DASHBOARD ---
elif st.session_state.role == "user_dashboard":
    user = run_query("SELECT user_id, name, category, password, max_limit FROM registered_ids WHERE user_id=%s", (st.session_state.user_data[0],), fetch="one")
    
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"Hello, {user[1].split()[0]}! 👋")
        st.caption(f"💎 Tier: **{user[2]}** | ID: `{user[0]}` | Max Allowance: {user[4]} seats")
    with col2:
        st.write("")
        if st.button("🚪 Leave"): logout()
        
    utab1, utab2, utab3 = st.tabs(["🍿 Now Showing", "🎫 My Wallet", "⚙️ Preferences"])
    
    with utab1:
        if st.session_state.current_page is None:
            shows = run_query("SELECT * FROM shows ORDER BY id", fetch="all")
            for s in shows:
                st.markdown("<div class='movie-card'>", unsafe_allow_html=True)
                col1, col2 = st.columns([1, 4])
                with col1:
                    if s[5] and os.path.exists(os.path.join("static", "uploads", s[5])):
                        st.image(os.path.join("static", "uploads", s[5]), use_container_width=True)
                    else:
                        st.info("Image Pending")
                with col2:
                    st.subheader(s[1])
                    st.markdown(f"**{datetime.datetime.strptime(s[2], '%Y-%m-%d').strftime('%B %d, %Y')}** at **{s[3]}**")
                    st.write(s[4])
                    if s[6]:
                        if st.button(f"🎟️ Buy Tickets", key=f"bk_{s[0]}", type="primary"):
                            st.session_state.current_page = ("book", s[0], s[1])
                            st.rerun()
                    else:
                        st.error("🚫 SOLD OUT / CLOSED")
                st.markdown("</div>", unsafe_allow_html=True)
                
        else:
            page_type, show_id, show_title = st.session_state.current_page
            st.button("← Back to Movies", on_click=lambda: st.session_state.update(current_page=None))
            
            st.markdown(f"<h2>Booking: <span style='color:#ff4b4b;'>{show_title}</span></h2>", unsafe_allow_html=True)
            
            booked = [r[0] for r in run_query("SELECT seat_num FROM booked_seats WHERE show_id=%s", (show_id,), fetch="all")]
            u_booked_count = len(run_query("SELECT b.seat_num FROM booked_seats b JOIN shows s ON b.show_id = s.id WHERE s.title = %s AND b.user_id = %s", (show_title, user[0]), fetch="all"))
            rem_quota = user[4] - u_booked_count
            
            st.info(f"💡 You have **{rem_quota}** tickets remaining for '{show_title}' across all showtimes.")
            
            with st.form(key=f"seat_form_{show_id}"):
                st.markdown("<div class='cinema-screen'>CINEMA SCREEN</div>", unsafe_allow_html=True)
                
                selected_seats = []
                for row in ROWS:
                    cat = 'Gold' if row == 'J' else ('Silver' if row in ['G','H','I'] else 'Standard')
                    is_disabled = (cat != user[2])
                    
                    cols = st.columns(30)
                    cols[0].markdown(f"**{row}**")
                    for c in range(1, 29):
                        seat_id = f"{row}{c}"
                        col_idx = c if c <= 14 else c + 1  
                        with cols[col_idx]:
                            if seat_id in booked: st.markdown("🔴") 
                            elif is_disabled: st.markdown("🔒") 
                            else:
                                if st.checkbox(f"{c}", key=f"c_{seat_id}", label_visibility="collapsed"):
                                    selected_seats.append(seat_id)
                    cols[29].markdown(f"**{row}**")
                    
                st.write("")
                if st.form_submit_button("💳 Confirm Secure Checkout", type="primary"):
                    if not selected_seats:
                        st.warning("Please select at least one seat.")
                    elif len(selected_seats) > rem_quota:
                        st.error(f"Quota exceeded! You are trying to book {len(selected_seats)}, but only have {rem_quota} left.")
                    else:
                        ref = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                        ins = [(show_id, s, user[0], ref) for s in selected_seats]
                        run_query("INSERT INTO booked_seats (show_id, seat_num, user_id, booking_ref) VALUES (%s, %s, %s, %s)", ins, execute_many=True)
                        st.balloons()
                        st.success("🎉 Success! Tickets sent to your wallet.")
                        st.session_state.current_page = None

    with utab2:
        my_books = run_query("SELECT b.booking_ref, s.title, s.show_date, s.show_time, STRING_AGG(b.seat_num, ', ') FROM booked_seats b JOIN shows s ON b.show_id = s.id WHERE b.user_id = %s GROUP BY b.booking_ref, s.title, s.show_date, s.show_time", (user[0],), fetch="all")
        if not my_books:
            st.info("Your wallet is empty. Go book a movie!")
        for mb in my_books:
            st.markdown("<div class='movie-card'>", unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### 🎬 {mb[1]}")
                st.write(f"**When:** {mb[2]} @ {mb[3]}")
                st.write(f"**Seats:** {mb[4]} | **Ref:** `{mb[0]}`")
            with col2:
                seats_arr = mb[4].split(", ")
                cost = len(seats_arr) * PRICES.get(user[2], 10)
                pdf_out = generate_receipt_pdf(mb[0], user[1], user[0], user[2], f"{mb[1]} ({mb[2]} {mb[3]})", seats_arr, cost)
                with open(pdf_out, "rb") as pdf_file:
                    st.download_button(label="📥 Download Pass", data=pdf_file, file_name=f"Ticket_{mb[0]}.pdf", mime="application/pdf", key=f"dl_{mb[0]}", type="primary")
            st.markdown("</div>", unsafe_allow_html=True)

    with utab3:
        st.markdown("### 🔐 Security Details")
        old_p = st.text_input("Current PIN", type="password")
        new_p = st.text_input("New PIN", type="password")
        if st.button("Update PIN", type="primary"):
            if old_p != user[3]: st.error("Incorrect current PIN.")
            elif new_p:
                run_query("UPDATE registered_ids SET password=%s WHERE user_id=%s", (new_p, user[0]))
                st.toast("✅ PIN Updated!")
