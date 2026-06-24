import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import re
import random
from datetime import datetime
import pytz
from export_log import show_export_tab

# --- WEB APP SETTINGS ---
st.set_page_config(page_title="Carla's Workout", page_icon="💪")
st.title("🏋️ Carla's Daily Workout Tracker")

# --- TIMEZONE FIX ---
eastern = pytz.timezone("America/New_York")
today = datetime.now(eastern).strftime("%A")

# --- GOOGLE SHEETS CONNECTION ---
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scopes
)
client = gspread.authorize(creds)

SHEET_URL = "https://docs.google.com/spreadsheets/d/1QrVZ4eg2b2KLXDGgLzoU8useR__9kFYiZgR-A6lBotY"
sheet = client.open_by_url(SHEET_URL)


def convert_drive_link(url):
    """Convert any Google Drive share link to a working thumbnail URL."""
    try:
        url = url.strip()
        file_id = None

        if "drive.google.com/file/d/" in url:
            file_id = url.split("/file/d/")[1].split("/")[0]
        elif "uc?id=" in url:
            file_id = url.split("uc?id=")[1].split("&")[0]
        elif "uc?export=view&id=" in url:
            file_id = url.split("id=")[1].split("&")[0]

        if file_id:
            return f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"

        return url
    except Exception:
        return url


def display_photos(photo_cell_value, width=250):
    """Display one or more photos from a comma-separated cell value."""
    if not photo_cell_value or str(photo_cell_value).strip().lower() in ["none", "", "n/a"]:
        return

    urls = [u.strip() for u in str(photo_cell_value).split(",") if u.strip()]
    valid_urls = [u for u in urls if u.lower() not in ["none", "", "n/a"]]

    if not valid_urls:
        return

    if len(valid_urls) == 1:
        st.image(convert_drive_link(valid_urls[0]), width=width)
    else:
        cols = st.columns(len(valid_urls))
        for i, url in enumerate(valid_urls):
            with cols[i]:
                st.image(convert_drive_link(url), width=width)


@st.cache_resource
def get_or_create_log_sheet():
    """Get the workout log tab, or create it if it doesn't exist. Cached for the session."""
    try:
        return sheet.worksheet("Workout Log")
    except Exception:
        ws = sheet.add_worksheet(title="Workout Log", rows="1000", cols="10")
        ws.append_row(["Date", "Day", "Exercise", "Sets", "Reps Done", "Weight (lbs)", "Notes"])
        return ws


def display_exercise_block(row, name_col, sets_col, reps_col, notes_col,
                            photo_col, superset_col, superset_id_col,
                            superset_photo_col, df, ex_id="", is_superset_secondary=False):
    """Display a single exercise block with name, targets, notes and photos."""

    ex_name     = str(row[name_col]).strip() if name_col else "Unknown Exercise"
    target_sets = str(row[sets_col]).strip() if sets_col else "3"
    target_reps = str(row[reps_col]).strip() if reps_col else "10"
    notes       = str(row[notes_col]).strip() if notes_col else ""
    photo_val   = str(row[photo_col]).strip() if photo_col else ""
    row_superset_default = str(row[superset_col]).strip().lower() == "yes" if superset_col else False
    ss_ex_id    = str(row[superset_id_col]).strip() if superset_id_col else ""
    ss_photo    = str(row[superset_photo_col]).strip() if superset_photo_col else ""

    st.markdown(f"**{ex_name}** — 🎯 {target_sets} sets × {target_reps} reps")
    if notes and notes.lower() not in ["none", ""]:
        st.info(f"📝 {notes}")
    display_photos(photo_val)

    return ex_name, target_sets, target_reps, row_superset_default, ss_ex_id, ss_photo


def get_last_session(log_ws, exercise_name):
    try:
        records = log_ws.get_all_records()
    except Exception:
        return None

    if not records:
        return None

    exercise_key = str(exercise_name).strip().lower()
    history = [r for r in records if str(r.get("Exercise", "")).strip().lower() == exercise_key]
    if not history:
        return None

    def parse_float(value):
        try:
            return float(str(value).strip())
        except Exception:
            return None

    pr_weight = None
    for record in history:
        weight = parse_float(record.get("Weight (lbs)", ""))
        if weight is not None:
            if pr_weight is None or weight > pr_weight:
                pr_weight = weight

    def parse_date(value):
        try:
            return datetime.fromisoformat(str(value).strip())
        except Exception:
            return None

    latest = None
    latest_date = None
    for record in history:
        record_date = parse_date(record.get("Date", ""))
        if record_date is not None and (latest_date is None or record_date > latest_date):
            latest = record
            latest_date = record_date

    if latest is None:
        latest = history[-1]

    return {
        "date": str(latest.get("Date", "")).strip(),
        "sets": str(latest.get("Sets", "")).strip(),
        "reps": str(latest.get("Reps Done", "")).strip(),
        "weight": str(latest.get("Weight (lbs)", "")).strip(),
        "pr_weight": pr_weight,
    }


@st.cache_data(ttl=60)
def load_workout_data():
    """Read the workout sheet data once per minute instead of on every interaction."""
    for ws in sheet.worksheets():
        if ws.title == "Workout Log":
            continue
        data = ws.get_all_values()
        for idx, row in enumerate(data[:10]):
            row_cleaned = [
                str(cell).lower().replace("_", "").replace(" ", "").strip()
                for cell in row
            ]
            if 'dayofweek' in row_cleaned or 'exerciseid' in row_cleaned:
                return data, idx
    return None, None


def run_tracker():
    try:
        # --- SCAN FOR WORKOUT DATA TAB (CACHED) ---
        raw_values, header_idx = load_workout_data()

        if header_idx is None or not raw_values:
            st.error("❌ Could not find workout data in any tab.")
            return

        # --- BUILD DATAFRAME ---
        headers   = [str(h).strip() for h in raw_values[header_idx]]
        data_rows = raw_values[header_idx + 1:]

        df = pd.DataFrame(data_rows)
        df.columns = headers[:len(df.columns)]
        df = df.loc[:, (df.columns != "") & (df.columns.notna())]

        st.success("✅ Connected to Google Sheet!")

        # --- CREATE TABS ---
        tab1, tab2 = st.tabs(["Workout Tracker", "Export Log"])

        with tab1:
            # --- IDENTIFY COLUMNS ---
            def normalize_col(col_name):
                return re.sub(r"[^a-z0-9]", "", str(col_name).lower())

            def find_col(df, *keywords):
                normalized_columns = {normalize_col(c): c for c in df.columns}
                for kw in keywords:
                    kw_norm = normalize_col(kw)
                    if kw_norm in normalized_columns:
                        return normalized_columns[kw_norm]

                for kw in keywords:
                    kw_norm = normalize_col(kw)
                    for norm_name, original_name in normalized_columns.items():
                        if kw_norm in norm_name or norm_name in kw_norm:
                            return original_name
                return None

            day_col          = find_col(df, "dayofweek")
            id_col           = find_col(df, "exerciseid")
            name_col         = find_col(df, "exercisename")
            sets_col         = find_col(df, "targetsets")
            reps_col         = find_col(df, "targetreps")
            notes_col        = find_col(df, "instructions/notes", "instructionsnotes", "notes")
            photo_col        = find_col(df, "photoreference", "photo", "imageurl", "image")
            superset_col     = find_col(df, "superset")
            superset_id_col  = find_col(df, "supersetexerciseid", "supersetid")
            superset_photo_col = find_col(df, "supersetphoto", "supersetpicture")

            if not day_col:
                st.error("❌ Could not find 'Day_of_Week' column.")
                return

            # --- COLLAPSIBLE SUMMARY ---
            with st.expander("📋 Workout Database Summary"):
                day_counts = df[day_col].str.strip().value_counts()
                for day, count in day_counts.items():
                    if day.strip():
                        st.write(f"• **{day}**: {count} exercise(s)")

            # --- DAY SELECTOR ---
            mix_days = ["Day-3", "Day-4"]  # virtual days, not actual rows in the sheet

            sheet_days = sorted(
                df[day_col].dropna().astype(str).str.strip().unique(),
                key=lambda d: d.lower()
            )
            available_days = sheet_days + [d for d in mix_days if d not in sheet_days]
            selected_day = st.selectbox("📅 Select Day", available_days, index=0)

            st.subheader(f"💪 {selected_day}'s Workout")

            def get_primary_pool(day_label):
                """Return rows for a given day, excluding superset partner rows."""
                pool = df[df[day_col].str.strip().str.lower() == day_label].copy()
                if superset_id_col and id_col:
                    partner_ids = set()
                    for _, row in pool.iterrows():
                        pid = str(row[superset_id_col]).strip()
                        uses_flag = superset_col and str(row[superset_col]).strip().lower() == "yes"
                        if pid and (uses_flag or not superset_col):
                            partner_ids.add(pid)
                    pool = pool[~pool[id_col].astype(str).str.strip().isin(partner_ids)]
                return pool

            if selected_day.strip() in mix_days:
                day1_pool = get_primary_pool("day-1")
                day2_pool = get_primary_pool("day-2")

                pick_count_1 = min(5, len(day1_pool))
                pick_count_2 = min(5, len(day2_pool))

                picked_1 = day1_pool.loc[random.sample(list(day1_pool.index), pick_count_1)] if pick_count_1 > 0 else day1_pool
                picked_2 = day2_pool.loc[random.sample(list(day2_pool.index), pick_count_2)] if pick_count_2 > 0 else day2_pool

                days_workout = pd.concat([picked_1, picked_2])
                st.info(f"🎲 Mixed session: {pick_count_1} from Day-1 + {pick_count_2} from Day-2 (randomized)")
            else:
                days_workout = df[df[day_col].str.strip().str.lower() == selected_day.strip().lower()].copy()

            if days_workout.empty:
                st.info("🎉 Rest day! Recovery is part of the program.")
                return

            # --- LOG SHEET ---
            log_ws = get_or_create_log_sheet()

            # --- TRACK WHICH EXERCISE IDS ARE SUPERSET PARTNERS (skip as standalone) ---
            superset_partner_ids = set()
            if superset_id_col and id_col:
                for _, row in days_workout.iterrows():
                    partner_id = str(row[superset_id_col]).strip()
                    uses_superset_flag = superset_col and str(row[superset_col]).strip().lower() == "yes"
                    if partner_id and (uses_superset_flag or not superset_col):
                        superset_partner_ids.add(partner_id)

            # --- WORKOUT FORM ---
            st.markdown("### Log Your Session")
            log_date = datetime.now(eastern).strftime("%Y-%m-%d")

            for idx, (_, row) in enumerate(days_workout.iterrows()):
                ex_id = str(row[id_col]).strip() if id_col else ""

                if ex_id in superset_partner_ids:
                    continue

                st.markdown("---")

                ex_name, target_sets, target_reps, row_superset_default, ss_ex_id, ss_photo = display_exercise_block(
                    row, name_col, sets_col, reps_col, notes_col,
                    photo_col, superset_col, superset_id_col,
                    superset_photo_col, df, ex_id=ex_id
                )

                if not ex_name:
                    continue

                form_key = f"workout_form_{ex_id or re.sub(r'[^a-z0-9]', '_', ex_name.lower())}"
                radio_key = f"superset_{ex_id}"
                sup_choice = "No"
                if row_superset_default and ss_ex_id:
                    st.radio("Superset?", ["No", "Yes"], index=0, key=radio_key)
                    sup_choice = st.session_state.get(radio_key, "No")

                if sup_choice == "Yes" and row_superset_default and ss_ex_id:
                    st.markdown(f"""
                    <div style='background-color:#1e3a5f;padding:10px;border-radius:8px;margin-bottom:4px'>
                        <span style='color:#f0a500;font-weight:bold;font-size:13px'>🔁 SUPERSET</span>
                    </div>
                    """, unsafe_allow_html=True)

                    # Look up partner data only — nothing is displayed here.
                    # It now renders inside the form, directly above its own
                    # fields, so each exercise's photo sits next to its inputs.
                    id_col_lookup = next((c for c in df.columns if str(c).lower().replace("_"," ").replace(" ","") == "exerciseid"), None)
                    partner_name = ss_ex_id
                    p_sets = "3"
                    p_reps = "10"
                    p_notes = ""
                    partner_rows = pd.DataFrame()

                    if id_col_lookup and ss_ex_id:
                        partner_rows = df[df[id_col_lookup].str.strip() == ss_ex_id]
                        if not partner_rows.empty:
                            partner = partner_rows.iloc[0]
                            partner_name = str(partner[name_col]).strip() if name_col else ss_ex_id
                            p_sets = str(partner[sets_col]).strip() if sets_col else "3"
                            p_reps = str(partner[reps_col]).strip() if reps_col else "10"
                            p_notes = str(partner[notes_col]).strip() if notes_col else ""

                    partner_photo = ""
                    if not partner_rows.empty and photo_col:
                        partner_photo = str(partner[photo_col]).strip()

                    chosen_photo = partner_photo if partner_photo and partner_photo.lower() not in ["none", ""] else ss_photo

                last = get_last_session(log_ws, ex_name)
                if last:
                    is_pr = False
                    try:
                        last_weight = float(last["weight"])
                        is_pr = last["pr_weight"] is not None and last_weight == last["pr_weight"]
                    except Exception:
                        is_pr = False
                    pr_badge = " ⭐ PR" if is_pr else ""
                    st.caption(f"📊 Last session ({last['date']}): {last['sets']} sets × {last['reps']} reps @ {last['weight']} lbs{pr_badge}")

                with st.form(form_key):
                    col1, col2, col3, col4 = st.columns(4)
                    try:
                        default_sets = int(float(target_sets))
                    except Exception:
                        default_sets = 3
                    sets_index = min(max(default_sets - 1, 0), 3)
                    with col1:
                        sets_selected = st.selectbox("Sets", [1, 2, 3, 4], index=sets_index, key=f"sets_{ex_id}")
                    with col2:
                        reps_done = st.text_input("Reps done", key=f"reps_{ex_id}", placeholder=target_reps)
                    with col3:
                        weight = st.text_input("Weight (lbs)", key=f"weight_{ex_id}", placeholder="0")
                    with col4:
                        log_note = st.text_input("Notes", key=f"notes_{ex_id}", placeholder="optional")

                    if st.session_state.get(radio_key, "No") == "Yes" and row_superset_default and ss_ex_id:
                        st.markdown("---")
                        st.markdown(f"**{partner_name}** — 🎯 {p_sets} sets × {p_reps} reps")
                        if p_notes and p_notes.lower() not in ["none", ""]:
                            st.info(f"📝 {p_notes}")
                        display_photos(chosen_photo)

                        try:
                            p_default_sets = int(float(p_sets))
                        except Exception:
                            p_default_sets = 3
                        p_sets_index = min(max(p_default_sets - 1, 0), 3)
                        p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                        with p_col1:
                            p_sets_selected = st.selectbox("Sets", [1, 2, 3, 4], index=p_sets_index, key=f"partner_sets_{ss_ex_id}_{idx}")
                        with p_col2:
                            p_reps_done = st.text_input("Reps done", key=f"partner_reps_{ss_ex_id}_{idx}", placeholder=p_reps)
                        with p_col3:
                            p_weight = st.text_input("Weight (lbs)", key=f"partner_weight_{ss_ex_id}_{idx}", placeholder="0")
                        with p_col4:
                            p_note = st.text_input("Notes", key=f"partner_notes_{ss_ex_id}_{idx}", placeholder="optional")

                    submitted = st.form_submit_button(f"💾 Save {ex_name}")

                    if submitted:
                        log_ws.append_row([
                            log_date,
                            selected_day,
                            ex_name,
                            sets_selected,
                            reps_done,
                            weight,
                            log_note
                        ])

                        if sup_choice == "Yes" and row_superset_default and ss_ex_id:
                            id_col_lookup = next((c for c in df.columns if str(c).lower().replace("_"," ").replace(" ","") == "exerciseid"), None)
                            partner_name = ss_ex_id
                            if id_col_lookup and ss_ex_id:
                                partner_rows = df[df[id_col_lookup].str.strip() == ss_ex_id]
                                if not partner_rows.empty:
                                    partner = partner_rows.iloc[0]
                                    partner_name = str(partner[name_col]).strip() if name_col else ss_ex_id

                            p_sets_key = f"partner_sets_{ss_ex_id}_{idx}"
                            p_reps_key = f"partner_reps_{ss_ex_id}_{idx}"
                            p_weight_key = f"partner_weight_{ss_ex_id}_{idx}"
                            p_note_key = f"partner_notes_{ss_ex_id}_{idx}"
                            p_sets_val = st.session_state.get(p_sets_key, None)
                            p_reps_val = st.session_state.get(p_reps_key, "")
                            p_weight_val = st.session_state.get(p_weight_key, "")
                            p_note_val = st.session_state.get(p_note_key, "")

                            if partner_name:
                                log_ws.append_row([
                                    log_date,
                                    selected_day,
                                    partner_name,
                                    p_sets_val if p_sets_val is not None else "",
                                    p_reps_val,
                                    p_weight_val,
                                    p_note_val
                                ])
                        st.success(f"✅ Logged {ex_name} to Workout Log")

        with tab2:
            workout_log_ws = get_or_create_log_sheet()
            show_export_tab(workout_log_ws)
    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.exception(e)


# Run the app
run_tracker()
