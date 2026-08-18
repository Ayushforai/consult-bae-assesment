import os
import re
import pandas as pd
import numpy as np
from datetime import datetime
from rapidfuzz import fuzz
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_PATH = "sqlite:///consultbae.db"
engine = create_engine(DB_PATH, echo=False)
Base = declarative_base()

# --- SCHEMA DEFINITION ---

class SourceRecord(Base):
    __tablename__ = 'source_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(String, nullable=False)
    raw_name = Column(String)
    raw_email = Column(String)
    raw_phone = Column(String)
    raw_city = Column(String)
    raw_payload = Column(Text)
    canonical_person_id = Column(Integer, ForeignKey('people.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

class Person(Base):
    __tablename__ = 'people'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String, nullable=False)
    email = Column(String, index=True)
    phone = Column(String, index=True)
    city = Column(String)
    experience_years = Column(Float)
    current_ctc = Column(Float)
    hourly_rate = Column(Float)
    monthly_rate = Column(Float)
    status = Column(String)
    verified = Column(Boolean)
    projects_completed = Column(Integer)
    skills = Column(Text)
    data_sources = Column(String) # e.g. "source1,source3"
    match_confidence = Column(String) # e.g. "EXACT_EMAIL", "EXACT_PHONE", "FUZZY_NAME_CITY"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    raw_records = relationship("SourceRecord", backref="person")

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# --- NORMALIZERS ---

def normalize_phone(val):
    if pd.isna(val): return None
    digits = re.sub(r'\D', '', str(val))
    if len(digits) >= 10:
        return digits[-10:] # Extract standard 10-digit mobile number
    return None

def normalize_email(val):
    if pd.isna(val): return None
    s = str(val).strip().lower()
    return s if '@' in s else None

def normalize_city(val):
    if pd.isna(val): return None
    s = str(val).strip().lower()
    mapping = {
        'gurgaon': 'Gurugram',
        'gurugram': 'Gurugram',
        'bengaluru': 'Bengaluru',
        'bangalore': 'Bengaluru',
        'noida': 'Noida',
        'delhi': 'New Delhi',
        'new delhi': 'New Delhi',
        'delhi ncr': 'New Delhi',
        'pune': 'Pune'
    }
    return mapping.get(s, s.title())

def parse_rate(rate_str):
    if pd.isna(rate_str): return None, None
    s = str(rate_str).strip().lower()
    hourly, monthly = None, None
    if '/hr' in s:
        val = re.sub(r'[^\d.]', '', s.split('/hr')[0])
        hourly = float(val) if val else None
    elif 'k/month' in s:
        val = re.sub(r'[^\d.]', '', s.split('k/month')[0])
        monthly = float(val) * 1000 if val else None
    return hourly, monthly

def parse_skills(skills_val):
    if pd.isna(skills_val): return []
    items = str(skills_val).split(',')
    return [i.strip().lower() for i in items if i.strip()]

# --- ENTITY RESOLUTION & PIPELINE EXECUTION ---

def run_merge_pipeline():
    session = Session()
    print("🚀 Running Ingestion and Entity Resolution Pipeline...")

    # Load Raw Datasets
    df1 = pd.read_csv('data/source1_naukri_applicants.csv')
    df2 = pd.read_csv('data/source2_gig_workers.csv')
    df3 = pd.read_csv('data/source3_cbnexus_contacts.csv')

    # 1. Process Source 1 (Naukri)
    for _, row in df1.iterrows():
        raw_rec = SourceRecord(
            source_file="source1_naukri_applicants.csv",
            raw_name=row.get('Full Name'),
            raw_email=row.get('Email'),
            raw_phone=str(row.get('Phone')),
            raw_city=row.get('City'),
            raw_payload=str(row.to_dict())
        )
        session.add(raw_rec)
        
        email = normalize_email(row.get('Email'))
        phone = normalize_phone(row.get('Phone'))
        name = str(row['Full Name']).strip().title()
        city = normalize_city(row.get('City'))
        
        person = Person(
            full_name=name,
            email=email,
            phone=phone,
            city=city,
            experience_years=float(row['Experience (Years)']) if pd.notna(row.get('Experience (Years)')) else None,
            current_ctc=float(row['Current CTC']) if pd.notna(row.get('Current CTC')) else None,
            skills=", ".join(parse_skills(row.get('Skills'))),
            data_sources="source1",
            match_confidence="PRIMARY_INSERT"
        )
        session.add(person)
        session.flush()
        raw_rec.canonical_person_id = person.id

    # 2. Process Source 2 (Gig Workers)
    df2 = df2.dropna(how='all') # Clean completely blank rows
    for _, row in df2.iterrows():
        raw_rec = SourceRecord(
            source_file="source2_gig_workers.csv",
            raw_name=row.get('worker_name'),
            raw_email=row.get('email_id'),
            raw_city=row.get('location'),
            raw_payload=str(row.to_dict())
        )
        session.add(raw_rec)
        
        email = normalize_email(row.get('email_id'))
        name = str(row.get('worker_name', '')).strip().title()
        city = normalize_city(row.get('location'))
        hourly, monthly = parse_rate(row.get('rate'))
        
        if not name or name.lower() == 'nan':
            continue

        person = None
        match_type = None

        # Tier 1 Match: Email
        if email:
            person = session.query(Person).filter_by(email=email).first()
            if person: match_type = "EXACT_EMAIL"

        # Tier 2 Match: Fuzzy Name + City Fallback
        if not person:
            candidates = session.query(Person).all()
            for cand in candidates:
                name_score = fuzz.ratio(name.lower(), cand.full_name.lower())
                if name_score >= 88 and (city and cand.city and city == cand.city):
                    person = cand
                    match_type = f"FUZZY_NAME_CITY ({name_score}%)"
                    break

        if person:
            sources = set((person.data_sources or "").split(","))
            sources.add("source2")
            person.data_sources = ",".join(filter(None, sources))
            if hourly: person.hourly_rate = hourly
            if monthly: person.monthly_rate = monthly
            
            # Merge Skills
            existing_skills = set(parse_skills(person.skills))
            new_skills = set(parse_skills(row.get('skill_tags')))
            person.skills = ", ".join(existing_skills.union(new_skills))
            
            status_val = str(row.get('status', '')).strip().lower()
            if status_val not in ['pune', 'noida', 'gurgaon']:
                person.status = status_val
        else:
            person = Person(
                full_name=name,
                email=email,
                city=city,
                hourly_rate=hourly,
                monthly_rate=monthly,
                status=str(row.get('status')).strip().lower(),
                skills=", ".join(parse_skills(row.get('skill_tags'))),
                data_sources="source2",
                match_confidence="NEW_ENTRY"
            )
            session.add(person)
        
        session.flush()
        raw_rec.canonical_person_id = person.id

    # 3. Process Source 3 (CBNexus Contacts - No Email)
    df3 = df3[df3['Name'] != 'Name'] # Filter header rows inserted in data
    for _, row in df3.iterrows():
        raw_rec = SourceRecord(
            source_file="source3_cbnexus_contacts.csv",
            raw_name=row.get('Name'),
            raw_phone=str(row.get('Phone Number')),
            raw_city=row.get('City'),
            raw_payload=str(row.to_dict())
        )
        session.add(raw_rec)
        
        phone = normalize_phone(row.get('Phone Number'))
        name = str(row.get('Name', '')).strip().title()
        city = normalize_city(row.get('City'))
        ver_raw = str(row.get('Verified', '')).strip().lower()
        verified_bool = True if ver_raw in ['y', 'yes', 'true', '1'] else False
        
        try:
            projects = int(row.get('Projects Completed', 0))
        except ValueError:
            projects = 0

        person = None
        # Tier 1 Match: 10-Digit Phone
        if phone:
            person = session.query(Person).filter_by(phone=phone).first()
            if person: match_type = "EXACT_PHONE"

        # Tier 2 Match: Fuzzy Name + City Fallback
        if not person:
            candidates = session.query(Person).all()
            for cand in candidates:
                name_score = fuzz.ratio(name.lower(), cand.full_name.lower())
                if name_score >= 88 and (city and cand.city and city == cand.city):
                    person = cand
                    match_type = f"FUZZY_NAME_CITY ({name_score}%)"
                    break

        if person:
            sources = set((person.data_sources or "").split(","))
            sources.add("source3")
            person.data_sources = ",".join(filter(None, sources))
            person.verified = verified_bool
            person.projects_completed = projects
            if not person.phone and phone:
                person.phone = phone
        else:
            person = Person(
                full_name=name,
                phone=phone,
                city=city,
                verified=verified_bool,
                projects_completed=projects,
                data_sources="source3",
                match_confidence="NEW_ENTRY"
            )
            session.add(person)
            
        session.flush()
        raw_rec.canonical_person_id = person.id

    session.commit()
    print("✅ Merge Pipeline Completed! Database populated at `consultbae.db`.")

if __name__ == '__main__':
    run_merge_pipeline()
