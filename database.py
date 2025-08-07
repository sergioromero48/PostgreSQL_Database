"""
Central place for all DB helpers.
- load_config(): read database.ini
- get_conn():   return a connection (context-manager friendly)
"""
from configparser import ConfigParser
import os
import psycopg2

INI_PATH   = os.getenv("DB_INI", "database.ini")
INI_SECT   = os.getenv("DB_SECTION", "postgresql")

def load_config(filename: str = INI_PATH,
                section: str = INI_SECT) -> dict:
    """Read key-value pairs from database.ini → dict, with env var overrides"""
    # Try to read from file first
    config = {}
    try:
        parser = ConfigParser()
        parser.read(filename)
        if parser.has_section(section):
            config = dict(parser.items(section))
    except Exception as e:
        print(f"Warning: Could not read {filename}: {e}")
    
    # Override with environment variables if present
    env_overrides = {
        'host': os.getenv('DB_HOST'),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'port': os.getenv('DB_PORT')
    }
    
    for key, value in env_overrides.items():
        if value is not None:
            config[key] = value
    
    # Default fallbacks
    if not config:
        config = {
            'host': 'localhost',
            'database': 'energyharvestingweatherdata',
            'user': 'postgres',
            'password': 'password',
            'port': '5432'
        }
    
    return config

def get_conn():
    """Context-manager wrapper around psycopg2.connect"""
    cfg = load_config()
    return psycopg2.connect(**cfg)
