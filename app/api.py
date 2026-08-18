# app/api.py
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, request, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from merge import Person, normalize_phone, normalize_email

app = Flask(__name__)
engine = create_engine(f"sqlite:///{ROOT_DIR / 'consultbae.db'}")
Session = sessionmaker(bind=engine)

@app.route('/check-duplicate', methods=['POST'])
def check_duplicate():
    data = request.json or {}
    email = normalize_email(data.get('email'))
    phone = normalize_phone(data.get('phone'))
    
    session = Session()
    existing = None
    if email:
        existing = session.query(Person).filter_by(email=email).first()
    if not existing and phone:
        existing = session.query(Person).filter_by(phone=phone).first()
        
    if existing:
        return jsonify({
            "is_duplicate": True,
            "canonical_id": existing.id,
            "full_name": existing.full_name,
            "data_sources": existing.data_sources
        }), 200
    return jsonify({"is_duplicate": False}), 200

if __name__ == '__main__':
    app.run(port=5002, debug=True)
