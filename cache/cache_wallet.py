import json
import sqlite3
import time
from typing import Optional, Dict, Any
from pathlib import Path

class CacheWallet:
    """Sistema de cache para persistir análisis de wallets y acelerar la demo."""
    
    def __init__(self, db_path: str = "cache/wallet_cache.db"):
        self.db_path = db_path
        self._init_db()
        self.ttl = 86400  # 24 horas

    def _init_db(self):
        """Inicializa la base de datos SQLite para el cache."""
        Path("cache").mkdir(exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wallet_analysis (
                address TEXT PRIMARY KEY,
                data TEXT,
                timestamp INTEGER
            )
        ''')
        conn.commit()
        conn.close()

    def obtener(self, address: str) -> Optional[Dict[str, Any]]:
        """Recupera un análisis del cache si no ha expirado."""
        address = address.lower()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT data, timestamp FROM wallet_analysis WHERE address = ?', (address,))
        row = cursor.fetchone()
        conn.close()

        if row:
            data_str, timestamp = row
            if time.time() - timestamp < self.ttl:
                return json.loads(data_str)
        return None

    def guardar(self, address: str, data: Dict[str, Any]):
        """Guarda un nuevo análisis en el cache."""
        address = address.lower()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO wallet_analysis (address, data, timestamp)
            VALUES (?, ?, ?)
        ''', (address, json.dumps(data), int(time.time())))
        conn.commit()
        conn.close()

wallet_cache = CacheWallet()
