import os

class Config:
    SECRET_KEY = os.urandom(24)
    PERMANENT_SESSION_LIFETIME = 1800 
    
    NUM_FAMILIAS = 5
    COSTO_KWH_DEFECTO = 0.6018
    COSTO_M3_DEFECTO = 1.86
    IGV_PORCENTAJE = 0.18
    
    LOGIN_USER = "admin"
    LOGIN_PASS = "123"
    
    FAMILIAS_COLLECTION = "familias"
    CONSUMOS_COLLECTION = "consumos"
    CONFIG_DOC = "config"
    LOGIN_DOC = "login"