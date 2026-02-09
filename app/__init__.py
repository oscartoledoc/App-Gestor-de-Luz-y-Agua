from flask import Flask
from datetime import timedelta
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from .config import Config

db = None

def init_firebase():
    global db
    try:
        if os.environ.get('FIREBASE_CREDENTIALS'):
            cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
            cred = credentials.Certificate(cred_json)
        else:
            cred = credentials.Certificate("firebase-service-account.json")
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("Conexión a Firebase exitosa.")
    except Exception as e:
        print(f"Error al inicializar Firebase: {e}")
        db = None

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(seconds=Config.PERMANENT_SESSION_LIFETIME)
    
    init_firebase()
    
    from .routes import main_bp
    app.register_blueprint(main_bp)
    
    return app