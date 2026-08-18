# app/audio_app.py
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(APP_DIR))

import streamlit as st
import pandas as pd
from datetime import datetime

from merge import Person, normalize_phone
from audio_utils import extract_audio_metrics
from models import AudioSubmission, Session

UPLOAD_DIR = ROOT_DIR / "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

st.set_page_config(page_title="ConsultBae Audio Portal", layout="wide")
st.title("🎙️ ConsultBae Gig Worker Audio Portal")

tab1, tab2 = st.tabs(["📤 Record & Submit", "📊 Submissions Dashboard"])

with tab1:
    st.subheader("Submit Audio Response")
    name = st.text_input("Full Name")
    phone = st.text_input("10-Digit Phone Number")
    audio_file = st.file_uploader("Upload Audio File", type=["wav", "mp3", "m4a", "ogg"])
    audio_recorded = st.audio_input("Or Record Audio Directly")

    if st.button("Submit Audio", type="primary"):
        target_audio = audio_recorded or audio_file
        if not name or not phone:
            st.error("Please fill in Name and Phone Number.")
        elif not target_audio:
            st.error("Please record or upload an audio file.")
        else:
            clean_p = normalize_phone(phone)
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_p}.wav"
            save_path = os.path.join(str(UPLOAD_DIR), filename)

            with open(save_path, "wb") as f:
                f.write(target_audio.read())

            metrics = extract_audio_metrics(save_path)

            session = Session()
            person = session.query(Person).filter_by(phone=clean_p).first()

            sub = AudioSubmission(
                person_id=person.id if person else None,
                applicant_name=name.strip(),
                phone=clean_p or phone,
                file_path=save_path,
                duration_seconds=metrics["duration_seconds"],
                sample_rate_hz=metrics["sample_rate_hz"],
                bitrate_kbps=metrics["bitrate_kbps"],
                loudness_db=metrics["loudness_db"],
                snr_db=metrics["snr_db"],
                quality_label=metrics["quality_label"]
            )
            session.add(sub)
            session.commit()

            st.success("✅ Audio processed and linked to canonical person database!")
            st.json(metrics)

with tab2:
    st.subheader("All Audio Submissions & Audio Metrics")
    session = Session()
    records = session.query(AudioSubmission).all()
    
    if not records:
        st.info("No audio recordings submitted yet.")
    else:
        df_display = pd.DataFrame([{
            "ID": r.id,
            "Person ID": r.person_id or "Unlinked",
            "Name": r.applicant_name,
            "Phone": r.phone,
            "Duration (s)": r.duration_seconds,
            "Sample Rate (Hz)": r.sample_rate_hz,
            "Bitrate (kbps)": r.bitrate_kbps,
            "Loudness (dB)": r.loudness_db,
            "SNR Quality": f"{r.snr_db} dB ({r.quality_label})"
        } for r in records])
        
        st.dataframe(df_display, use_container_width=True)
        
        st.markdown("### 🎧 Play Audio Recordings")
        for r in records:
            col1, col2 = st.columns([1, 3])
            with col1:
                st.write(f"**{r.applicant_name}** ({r.phone})")
                st.caption(f"Status: {r.quality_label}")
            with col2:
                if os.path.exists(r.file_path):
                    st.audio(r.file_path)

if __name__ == '__main__':
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx() is None:
        from streamlit.web import cli as stcli

        sys.argv = ["streamlit", "run", str(Path(__file__).resolve()), *sys.argv[1:]]
        sys.exit(stcli.main())
