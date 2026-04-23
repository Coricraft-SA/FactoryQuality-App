import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURATION & DIRECTORIES ---
for folder in ["pass_photo", "defect_photo"]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# --- DATABASE HELPERS ---
def get_db_connection():
    conn = sqlite3.connect('factory_quality.db')
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def log_action(action, module, details=""):
    try:
        conn = get_db_connection()
        user_id = st.session_state['user_perms'].get('id')
        user_name = st.session_state['user_perms'].get('fld_userName', 'Unknown')
        
        conn.execute('''
            INSERT INTO tblAuditLog (fld_userId, fld_userName, fld_action, fld_module, fld_details)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, user_name, action, module, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit Log Error: {e}")

def check_login(clock_no, password):
    conn = get_db_connection()
    query = "SELECT * FROM tbluserData WHERE fld_userClockNumber = ? AND fld_userPassword = ?"
    df = pd.read_sql_query(query, conn, params=(clock_no, password))
    conn.close()
    return df

def finalize_audit(temp_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_id = st.session_state['user_perms']['id']
        current_station = st.session_state.get('active_station', 'Unknown')
        
        pass_photo_path = None
        if temp_data['result'] == "Pass":
            pass_photo_path = f"pass_photo/JOB_{temp_data['job_num']}_{timestamp}.png"
            with open(pass_photo_path, "wb") as f:
                f.write(temp_data['photo'].getbuffer())

        cursor.execute('''
            INSERT INTO tblQCdata (
                fld_jobNumber, fld_prodLine, fld_active,
                fld_dateCreated, fld_dateModified, fld_result,
                fld_passPhoto, fld_user, fld_station
            ) VALUES (?, ?, 'Y', ?, ?, ?, ?, ?, ?)
        ''', (
            temp_data['job_num'], temp_data['line_id'], datetime.now(),
            datetime.now(), temp_data['result'], pass_photo_path, user_id, current_station
        ))
        
        new_qc_id = cursor.lastrowid

        if temp_data['result'] == "Fail":
            for i, d in enumerate(temp_data['defects']):
                def_path = f"defect_photo/JOB_{temp_data['job_num']}_DEF_{i}_{timestamp}.png"
                with open(def_path, "wb") as f:
                    f.write(d['photo'].getbuffer())
                
                cursor.execute('''
                    INSERT INTO tblDefectLogs (
                        fld_qcDataId, fld_defectId, fld_active,
                        fld_dateCreated, fld_dateModified
                    ) VALUES (?, ?, 'Y', ?, ?)
                ''', (new_qc_id, d['def_id'], datetime.now(), datetime.now()))

        conn.commit()
        log_action("Finalized Submission", current_station, f"Job: {temp_data['job_num']} | Result: {temp_data['result']}")
        return True
    except Exception as e:
        st.error(f"Database Error: {e}")
        return False
    finally:
        conn.close()

# --- INITIALIZE SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'main_portal'
if 'review_mode' not in st.session_state:
    st.session_state['review_mode'] = False
if 'active_station' not in st.session_state:
    st.session_state['active_station'] = 'EOL'
if 'admin_sub_page' not in st.session_state:
    st.session_state['admin_sub_page'] = None
if 'bible_target' not in st.session_state:
    st.session_state['bible_target'] = None
if 'fs_target' not in st.session_state:
    st.session_state['fs_target'] = None

# --- UI LOGIC ---
if not st.session_state['logged_in']:
    st.title("🪑 Coricraft Quality Portal")
    with st.form("login"):
        c = st.text_input("Clock Number")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            user_df = check_login(c, p)
            if not user_df.empty:
                st.session_state['logged_in'] = True
                st.session_state['user_perms'] = user_df.iloc[0].to_dict()
                log_action("Login", "Auth")
                st.rerun()
            else:
                st.error("Access Denied")

else:
    perms = st.session_state['user_perms']
    user_name = perms.get('fld_userName', 'User')

    st.sidebar.write(f"👤 **{user_name}**")
    st.sidebar.info(f"📍 Station: **{st.session_state['active_station']}**")
    if st.sidebar.button("Logout"):
        log_action("Logout", "Auth")
        st.session_state.clear()
        st.rerun()

    # --- SCREEN: ADMIN PORTAL ---
    if st.session_state['current_page'] == 'admin_portal':
        st.title("⚙️ Administrative Panel")
        if st.button("⬅️ Back to Main Portal"):
            st.session_state['current_page'] = 'main_portal'
            st.session_state['admin_sub_page'] = None
            st.rerun()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👤 User Management", use_container_width=True):
                st.session_state['admin_sub_page'] = 'user_mgmt'; st.rerun()
            if st.button("🏗️ Factory Setup", use_container_width=True):
                st.session_state['admin_sub_page'] = 'factory_setup'; st.rerun()
        with col2:
            if st.button("📖 Quality Bible", use_container_width=True):
                st.session_state['admin_sub_page'] = 'quality_bible'; st.rerun()
            st.button("📉 Audit Logs", use_container_width=True)

        st.divider()

        # SUB-PAGE: USER MANAGEMENT
        if st.session_state['admin_sub_page'] == 'user_mgmt':
            st.subheader("User Management")
            conn = get_db_connection()
            user_list = pd.read_sql("SELECT id, fld_userName, fld_userClockNumber FROM tbluserData", conn)
            u_options = {f"{r['fld_userName']} ({r['fld_userClockNumber']})": r['id'] for _, r in user_list.iterrows()}
            selected_u = st.selectbox("Select User to Edit", options=["-- Select --"] + list(u_options.keys()))
            if selected_u != "-- Select --":
                u_id = u_options[selected_u]
                u_data = pd.read_sql("SELECT * FROM tbluserData WHERE id = ?", conn, params=(u_id,)).iloc[0]
                with st.form("edit_user"):
                    e_name = st.text_input("Name", value=u_data['fld_userName'])
                    e_pass = st.text_input("Password", value=u_data['fld_userPassword'])
                    st.write("**Permissions**")
                    c1, c2, c3 = st.columns(3)
                    p_admin = c1.checkbox("Admin", value=u_data['fld_admin'] == 'Y')
                    p_mgmt = c1.checkbox("Management", value=u_data['fld_management'] == 'Y')
                    p_eol = c2.checkbox("EOL QC", value=u_data['fld_eolQC'] == 'Y')
                    p_sew = c2.checkbox("Sewing QC", value=u_data['fld_sewingQC'] == 'Y')
                    p_frm = c3.checkbox("Frame QC", value=u_data['fld_frameQC'] == 'Y')
                    p_wh = c3.checkbox("Warehouse", value=u_data['fld_warehouse'] == 'Y')
                    if st.form_submit_button("Save Changes"):
                        def yn(b): return 'Y' if b else 'N'
                        conn.execute('''UPDATE tbluserData SET fld_userName=?, fld_userPassword=?,
                                        fld_admin=?, fld_management=?, fld_eolQC=?, fld_sewingQC=?,
                                        fld_frameQC=?, fld_warehouse=?, fld_dateModified=? WHERE id=?''',
                                     (e_name, e_pass, yn(p_admin), yn(p_mgmt), yn(p_eol), yn(p_sew),
                                      yn(p_frm), yn(p_wh), datetime.now(), u_id))
                        conn.commit(); st.success("User Updated"); st.rerun()
            conn.close()

        # SUB-PAGE: QUALITY BIBLE
        elif st.session_state['admin_sub_page'] == 'quality_bible':
            st.subheader("📖 Quality Bible Editor")
            b1, b2, b3, b4, b5 = st.columns(5)
            if b1.button("Cost Centre", use_container_width=True): st.session_state['bible_target'] = 'tblcostcentres'
            if b2.button("Work Centre", use_container_width=True): st.session_state['bible_target'] = 'tblworkcentres'
            if b3.button("Operation", use_container_width=True): st.session_state['bible_target'] = 'tbloperation'
            if b4.button("Main Op", use_container_width=True): st.session_state['bible_target'] = 'tblmainOp'
            if b5.button("Prod Line", use_container_width=True): st.session_state['bible_target'] = 'tblprodLine'

            if st.session_state['bible_target']:
                target = st.session_state['bible_target']
                st.divider()
                conn = get_db_connection()
                config = {
                    'tblcostcentres': {'col': 'fld_costCentre', 'abb': 'fld_costAbb', 'cat': None, 'label': 'Cost Centre'},
                    'tblworkcentres': {'col': 'fld_workCentre', 'abb': 'fld_workAbb', 'cat': None, 'label': 'Work Centre'},
                    'tbloperation': {'col': 'fld_operation', 'abb': None, 'cat': None, 'label': 'Operation'},
                    'tblmainOp': {'col': 'fld_mainOp', 'abb': 'fld_mainOpAbb', 'cat': None, 'label': 'Main Operation'},
                    'tblprodLine': {'col': 'fld_prodLine', 'abb': 'fld_lineAbb', 'cat': 'fld_category', 'label': 'Production Line'}
                }
                cfg = config[target]
                
                with st.expander(f"➕ Add New {cfg['label']}"):
                    with st.form(f"add_{target}"):
                        new_val = st.text_input(f"{cfg['label']} Name")
                        new_abb = ""
                        new_cat = ""
                        if cfg['abb']: new_abb = st.text_input(f"{cfg['label']} Abbreviation")
                        if cfg['cat']: new_cat = st.text_input(f"{cfg['label']} Category (e.g., FRAM, SEW)")
                        
                        if st.form_submit_button("Save"):
                            if target == 'tblprodLine':
                                conn.execute(f"INSERT INTO {target} ({cfg['col']}, {cfg['abb']}, {cfg['cat']}) VALUES (?,?,?)", 
                                             (new_val, new_abb.upper(), new_cat.upper()))
                            elif cfg['abb']:
                                conn.execute(f"INSERT INTO {target} ({cfg['col']}, {cfg['abb']}) VALUES (?,?)", 
                                             (new_val, new_abb.upper()))
                            else:
                                conn.execute(f"INSERT INTO {target} ({cfg['col']}) VALUES (?)", (new_val,))
                            conn.commit(); st.success(f"{cfg['label']} Added"); st.rerun()

                df_existing = pd.read_sql(f"SELECT * FROM {target}", conn)
                for _, row in df_existing.iterrows():
                    cols = st.columns([3, 1, 1])
                    display_text = str(row[cfg['col']])
                    if cfg['abb'] and row[cfg['abb']]: display_text = f"{row[cfg['col']]} ({row[cfg['abb']]})"
                    if cfg['cat'] and row[cfg['cat']]: display_text += f" [{row[cfg['cat']]}]"
                    cols[0].write(display_text)
                    if cols[1].button("🗑️", key=f"del_{target}_{row['id']}"):
                        conn.execute(f"DELETE FROM {target} WHERE id = ?", (row['id'],)); conn.commit(); st.rerun()
                    if cols[2].button("✏️", key=f"edit_{target}_{row['id']}"):
                        st.session_state[f"edit_id_{target}"] = row['id']
                
                if f"edit_id_{target}" in st.session_state:
                    edit_id = st.session_state[f"edit_id_{target}"]
                    current_row = df_existing[df_existing['id'] == edit_id].iloc[0]
                    with st.form("edit_val_form"):
                        up_name = st.text_input("New Name", value=current_row[cfg['col']])
                        up_abb = st.text_input("New Abbreviation", value=current_row[cfg['abb']] if cfg['abb'] and current_row[cfg['abb']] else "") if cfg['abb'] else ""
                        up_cat = st.text_input("New Category", value=current_row[cfg['cat']] if cfg['cat'] and current_row[cfg['cat']] else "") if cfg['cat'] else ""
                        if st.form_submit_button("Update"):
                            if target == 'tblprodLine':
                                conn.execute(f"UPDATE {target} SET {cfg['col']} = ?, {cfg['abb']} = ?, {cfg['cat']} = ? WHERE id = ?", (up_name, up_abb.upper(), up_cat.upper(), edit_id))
                            elif cfg['abb']:
                                conn.execute(f"UPDATE {target} SET {cfg['col']} = ?, {cfg['abb']} = ? WHERE id = ?", (up_name, up_abb.upper(), edit_id))
                            else:
                                conn.execute(f"UPDATE {target} SET {cfg['col']} = ? WHERE id = ?", (up_name, edit_id))
                            conn.commit(); del st.session_state[f"edit_id_{target}"]; st.rerun()
                conn.close()

        # SUB-PAGE: FACTORY SETUP
        # SUB-PAGE: FACTORY SETUP
        elif st.session_state['admin_sub_page'] == 'factory_setup':
            st.subheader("🏗️ Factory Setup & Relations")
            fs1, fs2, fs3, fs4 = st.columns(4)
            if fs1.button("CC-WC-OP Relation", use_container_width=True): st.session_state['fs_target'] = 'cc_wc_op'
            if fs2.button("Defects Relation", use_container_width=True): st.session_state['fs_target'] = 'defect_rel'
            if fs3.button("Main Op-Op Relation", use_container_width=True): st.session_state['fs_target'] = 'main_op_rel'
            if fs4.button("Reason Codes", use_container_width=True): st.session_state['fs_target'] = 'reason_codes'

            if st.session_state['fs_target']:
                target = st.session_state['fs_target']
                st.divider()
                conn = get_db_connection()

                # --- 1. CC-WC-OP RELATION ---
                if target == 'cc_wc_op':
                    st.write("### Manage CC -> WC -> Operation")
                    with st.expander("➕ Add New Mapping"):
                        with st.form("add_ccwcop"):
                            df_cc = pd.read_sql("SELECT id, fld_costCentre FROM tblcostcentres", conn)
                            df_wc = pd.read_sql("SELECT id, fld_workCentre FROM tblworkcentres", conn)
                            df_op = pd.read_sql("SELECT id, fld_operation FROM tbloperation", conn)
                            s_cc = st.selectbox("Cost Centre", options=df_cc['fld_costCentre'].tolist())
                            s_wc = st.selectbox("Work Centre", options=df_wc['fld_workCentre'].tolist())
                            s_op = st.selectbox("Operation", options=df_op['fld_operation'].tolist())
                            if st.form_submit_button("Save Relation"):
                                cc_id = df_cc[df_cc['fld_costCentre'] == s_cc]['id'].values[0]
                                wc_id = df_wc[df_wc['fld_workCentre'] == s_wc]['id'].values[0]
                                op_id = df_op[df_op['fld_operation'] == s_op]['id'].values[0]
                                conn.execute("INSERT INTO tblCCWCOP (fld_costCentreId, fld_workCentreId, fld_operationId) VALUES (?,?,?)", (int(cc_id), int(wc_id), int(op_id)))
                                conn.commit(); st.rerun()

                    query_view = """SELECT rel.id, cc.fld_costCentre AS [Cost Centre], wc.fld_workCentre AS [Work Centre], op.fld_operation AS [Operation]
                                    FROM tblCCWCOP rel JOIN tblcostcentres cc ON rel.fld_costCentreId = cc.id
                                    JOIN tblworkcentres wc ON rel.fld_workCentreId = wc.id JOIN tbloperation op ON rel.fld_operationId = op.id"""
                    df_display = pd.read_sql(query_view, conn)
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

                    sel_id = st.selectbox("Select ID to Edit/Delete", options=[None] + df_display['id'].tolist())
                    if sel_id:
                        row = df_display[df_display['id'] == sel_id].iloc[0]
                        c1, c2, c3 = st.columns(3)
                        df_cc = pd.read_sql("SELECT id, fld_costCentre FROM tblcostcentres", conn)
                        df_wc = pd.read_sql("SELECT id, fld_workCentre FROM tblworkcentres", conn)
                        df_op = pd.read_sql("SELECT id, fld_operation FROM tbloperation", conn)
                        u_cc = c1.selectbox("New CC", options=df_cc['fld_costCentre'].tolist(), index=df_cc['fld_costCentre'].tolist().index(row['Cost Centre']))
                        u_wc = c2.selectbox("New WC", options=df_wc['fld_workCentre'].tolist(), index=df_wc['fld_workCentre'].tolist().index(row['Work Centre']))
                        u_op = c3.selectbox("New Op", options=df_op['fld_operation'].tolist(), index=df_op['fld_operation'].tolist().index(row['Operation']))
                        b1, b2 = st.columns(2)
                        if b1.button("Update Relation"):
                            cc_id = df_cc[df_cc['fld_costCentre'] == u_cc]['id'].values[0]
                            wc_id = df_wc[df_wc['fld_workCentre'] == u_wc]['id'].values[0]
                            op_id = df_op[df_op['fld_operation'] == u_op]['id'].values[0]
                            conn.execute("UPDATE tblCCWCOP SET fld_costCentreId=?, fld_workCentreId=?, fld_operationId=? WHERE id=?", (int(cc_id), int(wc_id), int(op_id), sel_id))
                            conn.commit(); st.rerun()
                        if b2.button("Delete Record", type="primary"):
                            conn.execute("DELETE FROM tblCCWCOP WHERE id=?", (sel_id,)); conn.commit(); st.rerun()

                # --- 2. DEFECTS RELATION ---
                elif target == 'defect_rel':
                    st.write("### Manage Defects")
                    with st.expander("➕ Add New Defect"):
                        with st.form("add_def"):
                            df_mo = pd.read_sql("SELECT id, fld_mainOp FROM tblmainOp", conn)
                            s_mo = st.selectbox("Main Operation", options=df_mo['fld_mainOp'].tolist())
                            noun = st.text_input("Defect Noun (e.g., STAIN)")
                            if st.form_submit_button("Save Defect"):
                                mo_id = df_mo[df_mo['fld_mainOp'] == s_mo]['id'].values[0]
                                full = f"{s_mo} {noun}".strip()
                                conn.execute("INSERT INTO tblDefect (fld_mainOp, fld_defectNoun, fld_defect) VALUES (?,?,?)", (int(mo_id), noun, full))
                                conn.commit(); st.rerun()

                    query_def = "SELECT d.id, m.fld_mainOp AS [Main Op], d.fld_defectNoun AS [Noun], d.fld_defect AS [Full Defect] FROM tblDefect d JOIN tblmainOp m ON d.fld_mainOp = m.id"
                    df_display = pd.read_sql(query_def, conn)
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    
                    sel_id = st.selectbox("Select Defect ID to Edit/Delete", options=[None] + df_display['id'].tolist())
                    if sel_id:
                        row = df_display[df_display['id'] == sel_id].iloc[0]
                        df_mo = pd.read_sql("SELECT id, fld_mainOp FROM tblmainOp", conn)
                        u_mo = st.selectbox("New Main Op", options=df_mo['fld_mainOp'].tolist(), index=df_mo['fld_mainOp'].tolist().index(row['Main Op']))
                        u_noun = st.text_input("New Noun", value=row['Noun'])
                        if st.button("Update Defect"):
                            mo_id = df_mo[df_mo['fld_mainOp'] == u_mo]['id'].values[0]
                            full = f"{u_mo} {u_noun}".strip().upper()
                            conn.execute("UPDATE tblDefect SET fld_mainOp=?, fld_defectNoun=?, fld_defect=? WHERE id=?", (int(mo_id), u_noun.upper(), full, sel_id))
                            conn.commit(); st.rerun()
                        if st.button("Delete Defect", type="primary"):
                            conn.execute("DELETE FROM tblDefect WHERE id=?", (sel_id,)); conn.commit(); st.rerun()

                # --- 3. MAIN OP-OP RELATION ---
                elif target == 'main_op_rel':
                    st.write("### Manage Main Operation to Operation Mapping")
                    
                    # --- ADD NEW (The missing piece) ---
                    with st.expander("➕ Add New Mapping"):
                        with st.form("add_mo_rel"):
                            df_mo_list = pd.read_sql("SELECT id, fld_mainOp FROM tblmainOp", conn)
                            df_op_list = pd.read_sql("SELECT id, fld_operation FROM tbloperation", conn)
                            
                            s_mo = st.selectbox("Main Operation", options=df_mo_list['fld_mainOp'].tolist())
                            s_op = st.selectbox("Sub-Operation", options=df_op_list['fld_operation'].tolist())
                            
                            if st.form_submit_button("Save Relation"):
                                m_id = int(df_mo_list[df_mo_list['fld_mainOp'] == s_mo]['id'].values[0])
                                o_id = int(df_op_list[df_op_list['fld_operation'] == s_op]['id'].values[0])
                                
                                # 1. Check if this combination already exists in the table
                                check_query = """
                                    SELECT COUNT(*) FROM tblmainOpToOpRelation 
                                    WHERE fld_mainOpId = ? AND fld_operationId = ?
                                """
                                exists = conn.execute(check_query, (m_id, o_id)).fetchone()[0]
                                
                                if exists > 0:
                                    # 2. Block the insert and warn the user
                                    st.warning(f"⚠️ This mapping already exists. No duplicate added.")
                                else:
                                    # 3. Proceed with the Insert if it's unique
                                    conn.execute(
                                        "INSERT INTO tblmainOpToOpRelation (fld_mainOpId, fld_operationId) VALUES (?,?)", 
                                        (m_id, o_id)
                                    )
                                    conn.commit()
                                    st.success("New relation saved!")
                                    st.rerun()

                    # --- VIEW ---
                    query_mo = """
                        SELECT rel.id, m.fld_mainOp AS [Main Op], o.fld_operation AS [Operation] 
                        FROM tblmainOpToOpRelation rel 
                        JOIN tblmainOp m ON rel.fld_mainOpId = m.id 
                        JOIN tbloperation o ON rel.fld_operationId = o.id
                    """
                    df_display = pd.read_sql(query_mo, conn)
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

                    # --- UPDATE / DELETE ---
                    st.write("#### Edit or Delete Selection")
                    sel_id = st.selectbox("Select Relation ID", options=[None] + df_display['id'].tolist())
                    
                    if sel_id:
                        row = df_display[df_display['id'] == sel_id].iloc[0]
                        df_mo = pd.read_sql("SELECT id, fld_mainOp FROM tblmainOp", conn)
                        df_op = pd.read_sql("SELECT id, fld_operation FROM tbloperation", conn)
                        
                        col_u1, col_u2 = st.columns(2)
                        u_mo = col_u1.selectbox("Main Op", options=df_mo['fld_mainOp'].tolist(), 
                                                index=df_mo['fld_mainOp'].tolist().index(row['Main Op']))
                        u_op = col_u2.selectbox("Operation", options=df_op['fld_operation'].tolist(), 
                                                index=df_op['fld_operation'].tolist().index(row['Operation']))
                        
                        b1, b2 = st.columns(2)
                        if b1.button("💾 Update Relation", use_container_width=True):
                            m_id = int(df_mo[df_mo['fld_mainOp'] == u_mo]['id'].values[0])
                            o_id = int(df_op[df_op['fld_operation'] == u_op]['id'].values[0])
                            
                            # 1. Check if this combination already exists (excluding the current record)
                            check_query = """
                                SELECT COUNT(*) FROM tblmainOpToOpRelation 
                                WHERE fld_mainOpId = ? AND fld_operationId = ? AND id != ?
                            """
                            exists = conn.execute(check_query, (m_id, o_id, sel_id)).fetchone()[0]
                            
                            if exists > 0:
                                st.error(f"⚠️ This relation already exists! Cannot create a duplicate.")
                            else:
                                # 2. Proceed with Update if no duplicate found
                                conn.execute("""
                                    UPDATE tblmainOpToOpRelation 
                                    SET fld_mainOpId=?, fld_operationId=? 
                                    WHERE id=?
                                """, (m_id, o_id, sel_id))
                                conn.commit()
                                st.success("Relation updated successfully!")
                                st.rerun()
                            
                        if b2.button("🗑️ Delete Relation", use_container_width=True, type="secondary"):
                            conn.execute("DELETE FROM tblmainOpToOpRelation WHERE id=?", (sel_id,))
                            conn.commit(); st.rerun()

                # --- 4. REASON CODES ---
                elif target == 'reason_codes':
                    st.write("### Manage Reason Codes")
                    
                    # --- ADD NEW ---
                    with st.expander("➕ Add New Reason Code"):
                        with st.form("add_reason"):
                            df_cc_list = pd.read_sql("SELECT id, fld_costCentre FROM tblcostcentres", conn)
                            df_def_list = pd.read_sql("SELECT id, fld_defect FROM tblDefect", conn)
                            
                            s_cc_name = st.selectbox("Cost Centre", options=df_cc_list['fld_costCentre'].tolist())
                            s_def_name = st.selectbox("Defect", options=df_def_list['fld_defect'].tolist())
                            
                            if st.form_submit_button("Save Reason Code"):
                                # Fetch the IDs to store in the table
                                cc_id = df_cc_list[df_cc_list['fld_costCentre'] == s_cc_name]['id'].values[0]
                                def_id = df_def_list[df_def_list['fld_defect'] == s_def_name]['id'].values[0]
                                
                                # Generate the standardized Reason Code string
                                full_code = f"{s_cc_name}-{s_def_name}".strip().upper()
                                
                                conn.execute("""
                                    INSERT INTO tblreasonCode (fld_costCentre, fld_defect, fld_reasonCode) 
                                    VALUES (?,?,?)""", (int(cc_id), int(def_id), full_code))
                                conn.commit(); st.rerun()

                    # --- VIEW (JOINing to get Names instead of IDs) ---
                    query_rc = """
                        SELECT 
                            rc.id, 
                            cc.fld_costCentre AS [CC Name], 
                            d.fld_defect AS [Defect Name], 
                            rc.fld_reasonCode AS [Reason Code]
                        FROM tblreasonCode rc
                        JOIN tblcostcentres cc ON rc.fld_costCentreId = cc.id
                        JOIN tblDefect d ON rc.fld_defectId = d.id
                    """
                    df_display = pd.read_sql(query_rc, conn)
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

                    # --- UPDATE / DELETE ---
                    st.write("#### Edit or Delete Existing Reason Code")
                    sel_id = st.selectbox("Select ID to Modify", options=[None] + df_display['id'].tolist())
                    
                    if sel_id:
                        row = df_display[df_display['id'] == sel_id].iloc[0]
                        df_cc = pd.read_sql("SELECT id, fld_costCentre FROM tblcostcentres", conn)
                        df_def = pd.read_sql("SELECT id, fld_defect FROM tblDefect", conn)
                        
                        cc_names = df_cc['fld_costCentre'].tolist()
                        def_names = df_def['fld_defect'].tolist()

                        col_u1, col_u2 = st.columns(2)
                        
                        # Now row['CC Name'] matches a value in cc_names perfectly
                        u_cc_name = col_u1.selectbox("New CC", options=cc_names, 
                                                    index=cc_names.index(row['CC Name']))
                        u_def_name = col_u2.selectbox("New Defect", options=def_names, 
                                                     index=def_names.index(row['Defect Name']))
                        
                        b1, b2 = st.columns(2)
                        if b1.button("💾 Update Reason Code", use_container_width=True):
                            new_cc_id = df_cc[df_cc['fld_costCentre'] == u_cc_name]['id'].values[0]
                            new_def_id = df_def[df_def['fld_defect'] == u_def_name]['id'].values[0]
                            new_full = f"{u_cc_name}-{u_def_name}".strip().upper()
                            
                            conn.execute("""
                                UPDATE tblreasonCode 
                                SET fld_costCentre=?, fld_defect=?, fld_reasonCode=? 
                                WHERE id=?""", (int(new_cc_id), int(new_def_id), new_full, int(sel_id)))
                            conn.commit(); st.success("Updated!"); st.rerun()
                            
                        if b2.button("🗑️ Delete Reason Code", use_container_width=True, type="secondary"):
                            conn.execute("DELETE FROM tblreasonCode WHERE id=?", (int(sel_id),))
                            conn.commit(); st.rerun()
                
                conn.close()

    # --- SHARED SCREEN: QC FORM ---
    elif st.session_state['current_page'] == 'qc_form':
        current_st = st.session_state['active_station']
        if not st.session_state['review_mode']:
            st.title(f"🛠️ {current_st} Quality Form")
            if st.button("⬅️ Back"):
                st.session_state['current_page'] = 'data_capture_portal'
                st.rerun()

            txtJobNum = st.text_input("Enter Job Number", key="txtJobNum")
            conn = get_db_connection()
            
            if current_st == "Sewing QC":
                df_sew_cc = pd.read_sql("SELECT id FROM tblcostcentres WHERE fld_costCentre = 'SEWING'", conn)
                sew_cc_id = int(df_sew_cc.iloc[0]['id']) if not df_sew_cc.empty else 0
                query_sew_wc = "SELECT DISTINCT w.id, w.fld_workCentre FROM tblworkcentres w JOIN tblCCWCOP c ON w.id = c.fld_workCentreId WHERE c.fld_costCentreId = ?"
                df_sew_wc = pd.read_sql(query_sew_wc, conn, params=(sew_cc_id,))
                ddWC = st.selectbox("Work Centre", options=df_sew_wc['fld_workCentre'].tolist(), key="ddWC")
                line_id = None
                line_display_name = ddWC
            else:
                line_disabled = current_st in ["WH", "RMA Repair"]
                if line_disabled:
                    ddProdLine = st.selectbox("Production Line", options=["N/A"], disabled=True, key="ddProdLine")
                    line_id = None
                    line_display_name = "N/A"
                else:
                    query_lines = "SELECT id, fld_prodLine FROM tblprodLine"
                    if current_st == "Frame": query_lines += " WHERE fld_category = 'FRAM'"
                    df_lines = pd.read_sql(query_lines, conn)
                    ddProdLine = st.selectbox("Production Line", options=df_lines['fld_prodLine'].tolist(), key="ddProdLine")
                    line_id = int(df_lines[df_lines['fld_prodLine'] == ddProdLine]['id'].values[0]) if not df_lines.empty else None
                    line_display_name = ddProdLine

            ddPass = st.selectbox("Result", options=["Pass", "Fail"], key="ddPass")

            if ddPass == "Pass":
                captured_photo = st.camera_input("Capture Pass Photo")
                if st.button("Submit Audit"):
                    if txtJobNum and captured_photo:
                        st.session_state['temp_audit'] = {
                            'job_num': txtJobNum, 'line_id': line_id, 'line_name': line_display_name,
                            'result': "Pass", 'photo': captured_photo, 'defects': []
                        }
                        st.session_state['review_mode'] = True
                        st.rerun()
            else:
                ddDefectNum = st.selectbox("Number of Defects", options=[1, 2, 3, 4, 5], key="ddDefectNum")
                defects_to_log = []
                for i in range(ddDefectNum):
                    st.divider()
                    st.write(f"**Defect {i+1} Details**")
                    if current_st == "Sewing QC":
                        sel_cc = "SEWING"; sel_wc = ddWC
                        df_force_wc = pd.read_sql("SELECT id FROM tblworkcentres WHERE fld_workCentre = ?", conn, params=(sel_wc,))
                        wc_id = int(df_force_wc.iloc[0]['id']) if not df_force_wc.empty else 0
                    else:
                        query_cc = "SELECT id, fld_costCentre FROM tblcostcentres"
                        if current_st == "Frame": query_cc += " WHERE fld_costCentre IN ('FRAME', 'MACHINE SHOP')"
                        df_cc = pd.read_sql(query_cc, conn)
                        sel_cc = st.selectbox(f"Cost Centre {i+1}", options=df_cc['fld_costCentre'].tolist(), key=f"cc_{i}")
                        cc_id = int(df_cc[df_cc['fld_costCentre'] == sel_cc]['id'].values[0])
                        query_wc = "SELECT DISTINCT w.id, w.fld_workCentre FROM tblworkcentres w JOIN tblCCWCOP c ON w.id = c.fld_workCentreId WHERE c.fld_costCentreId = ?"
                        df_wc = pd.read_sql(query_wc, conn, params=(cc_id,))
                        wc_options = df_wc['fld_workCentre'].tolist() if not df_wc.empty else ["No WC Found"]
                        sel_wc = st.selectbox(f"Work Centre {i+1}", options=wc_options, key=f"wc_{i}")
                        wc_id = int(df_wc[df_wc['fld_workCentre'] == sel_wc]['id'].values[0]) if not df_wc.empty and sel_wc != "No WC Found" else 0

                    query_op = "SELECT DISTINCT o.id, o.fld_operation FROM tbloperation o JOIN tblCCWCOP c ON o.id = c.fld_operationId WHERE c.fld_workCentreId = ?"
                    df_op = pd.read_sql(query_op, conn, params=(wc_id,))
                    op_options = df_op['fld_operation'].tolist() if not df_op.empty else ["No Op Found"]
                    sel_op = st.selectbox(f"Operation {i+1}", options=op_options, key=f"op_{i}")
                    op_id = int(df_op[df_op['fld_operation'] == sel_op]['id'].values[0]) if not df_op.empty and sel_op != "No Op Found" else 0
                    
                    df_def = pd.read_sql("SELECT d.id,d.fld_defect FROM tblDefect d JOIN tblmainOpToOpRelation mop ON d.fld_mainOp=mop.fld_mainOpId WHERE fld_operationId = ?", conn, params=(op_id,))
                    def_options = df_def['fld_defect'].tolist() if not df_def.empty else ["No Defect Found"]
                    sel_def = st.selectbox(f"Defect {i+1}", options=def_options, key=f"def_{i}")
                    def_photo = st.camera_input(f"Capture Defect {i+1} Photo", key=f"cam_{i}")
                    if not df_def.empty and sel_def != "No Defect Found":
                        defects_to_log.append({'def_id': int(df_def[df_def['fld_defect'] == sel_def]['id'].values[0]), 'def_name': sel_def, 'photo': def_photo})

                if st.button("Submit Fail Audit"):
                    if txtJobNum and all(d['photo'] is not None for d in defects_to_log):
                        st.session_state['temp_audit'] = {'job_num': txtJobNum, 'line_id': line_id, 'line_name': line_display_name, 'result': "Fail", 'defects': defects_to_log}
                        st.session_state['review_mode'] = True; st.rerun()
            conn.close()
        else:
            st.title("📋 Confirm Data Correctness")
            temp = st.session_state['temp_audit']
            col1, col2, col3 = st.columns(3)
            col1.metric("Station", st.session_state['active_station'])
            col2.metric("Job Number", temp['job_num'])
            label = "Work Centre" if st.session_state['active_station'] == "Sewing QC" else "Line"
            col3.metric(label, temp['line_name'])
            if temp['result'] == "Pass": st.image(temp['photo'], caption="Final Pass Photo", width=400)
            else:
                for i, d in enumerate(temp['defects']):
                    with st.expander(f"Defect {i+1}: {d['def_name']}", expanded=True): st.image(d['photo'], width=300)
            c1, c2 = st.columns(2)
            if c1.button("⬅️ Back / Edit"): st.session_state['review_mode'] = False; st.rerun()
            if c2.button("✅ Confirm & Save"):
                if finalize_audit(temp): st.success(f"Audit saved!"); st.session_state['review_mode'] = False; st.session_state['current_page'] = 'data_capture_portal'; st.rerun()

    # --- SCREEN: DATA CAPTURE PORTAL ---
    elif st.session_state['current_page'] == 'data_capture_portal':
        if st.button("⬅️ Back to Main Portal"): st.session_state['current_page'] = 'main_portal'; st.rerun()
        st.title("📝 Data Capture Portal")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏭 EOL QC", use_container_width=True, disabled=perms.get('fld_eolQC') != "Y"):
                st.session_state['active_station'] = "EOL"; st.session_state['current_page'] = 'qc_form'; st.rerun()
            if st.button("🔍 QC 2", use_container_width=True, disabled=perms.get('fld_QC2') != "Y"):
                st.session_state['active_station'] = "QC 2"; st.session_state['current_page'] = 'qc_form'; st.rerun()
            if st.button("📏 Frame QC", use_container_width=True, disabled=perms.get('fld_frameQC') != "Y"):
                st.session_state['active_station'] = "Frame"; st.session_state['current_page'] = 'qc_form'; st.rerun()
            if st.button("🧵 Sewing QC", use_container_width=True, disabled=perms.get('fld_sewingQC') != "Y"):
                st.session_state['active_station'] = "Sewing QC"; st.session_state['current_page'] = 'qc_form'; st.rerun()
        with col2:
            if st.button("📦 Warehouse QC", use_container_width=True, disabled=perms.get('fld_warehouse') != "Y"):
                st.session_state['active_station'] = "WH"; st.session_state['current_page'] = 'qc_form'; st.rerun()
            if st.button("🏥 Hospital Bay", use_container_width=True, disabled=perms.get('fld_uphRepair') != "Y"):
                st.session_state['active_station'] = "Hospital Bay"; st.session_state['current_page'] = 'qc_form'; st.rerun()
            if st.button("🔧 RMA Repair", use_container_width=True, disabled=perms.get('fld_rmaRepair') != "Y"):
                st.session_state['active_station'] = "RMA Repair"; st.session_state['current_page'] = 'qc_form'; st.rerun()

    # --- SCREEN: MAIN PORTAL ---
    else:
        st.title(f"Welcome, {user_name}")
        qc_fields = ['fld_eolQC', 'fld_frameQC', 'fld_sewingQC', 'fld_uphRepair', 'fld_rmaRepair', 'fld_QC2', 'fld_warehouse']
        can_capture = any(perms.get(f) == "Y" for f in qc_fields)
        col1, col2, col3 = st.columns(3)
        if col1.button("📝 Data Capture", use_container_width=True, disabled=not can_capture):
            log_action("Entered Portal", "Data Capture"); st.session_state['current_page'] = 'data_capture_portal'; st.rerun()
        col2.button("📊 Reports", use_container_width=True, disabled=perms.get('fld_management') != "Y")
        if col3.button("⚙️ Admin Panel", use_container_width=True, disabled=perms.get('fld_admin') != "Y"):
            st.session_state['current_page'] = 'admin_portal'; st.rerun()
