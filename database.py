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
    """Read key-value pairs from database.ini → dict"""
    parser = ConfigParser()
    parser.read(filename)
    if not parser.has_section(section):
        raise RuntimeError(
            f"Section [{section}] missing in {filename}"
        )
    return dict(parser.items(section))

def get_conn():
    """Context-manager wrapper around psycopg2.connect"""
    cfg = load_config()
    return psycopg2.connect(**cfg)
