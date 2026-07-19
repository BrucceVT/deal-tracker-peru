"""
Almacenamiento en SQLite.
Guarda cada producto visto, su historial de precios y qué alertas
ya se enviaron (para no spamear la misma oferta cada 45s).
"""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "deals.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT,
                image_url TEXT,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                original_price REAL,
                in_stock INTEGER DEFAULT 1,
                ts REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS alerts_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price_at_alert REAL NOT NULL,
                score REAL NOT NULL,
                ts REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL UNIQUE,
                subscription_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_product
                ON price_history(product_id);
            """
        )


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_or_create_product(store, url, title, category, image_url):
    """Upsert de la fila de products (sin tocar price_history). Devuelve product_id.

    Separado de record_price_point a propósito: el deal_engine necesita leer el
    historial de precios ANTES de que el precio actual se inserte en él, si no,
    la señal "precio más bajo histórico" nunca puede activarse (el precio actual
    ya estaría incluido en su propia comparación).
    """
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM products WHERE url = ?", (url,)).fetchone()
        if row is None:
            cur = conn.execute(
                """INSERT INTO products (store, url, title, category, image_url, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (store, url, title, category, image_url, now, now),
            )
            return cur.lastrowid
        else:
            product_id = row["id"]
            conn.execute(
                "UPDATE products SET title = ?, image_url = ?, last_seen = ? WHERE id = ?",
                (title, image_url, now, product_id),
            )
            return product_id


def record_price_point(product_id, price, original_price, in_stock=True):
    """Agrega un punto de historial de precio. Llamar DESPUÉS de evaluar el deal
    con get_price_history, para que la evaluación no vea su propio precio actual."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO price_history (product_id, price, original_price, in_stock, ts)
               VALUES (?, ?, ?, ?, ?)""",
            (product_id, price, original_price, int(in_stock), time.time()),
        )


def get_price_history(product_id, limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT price, ts FROM price_history WHERE product_id = ? ORDER BY ts DESC LIMIT ?",
            (product_id, limit),
        ).fetchall()
        return [(r["price"], r["ts"]) for r in rows]


def was_alert_sent_recently(product_id, price, window_seconds=6 * 3600):
    """Evita re-notificar el mismo producto al mismo precio cada 45s.

    Compara con tolerancia (no ==) porque price_at_alert viene de un scrape
    y puede diferir en centavos por redondeos entre lecturas del mismo precio.
    """
    cutoff = time.time() - window_seconds
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id FROM alerts_sent
               WHERE product_id = ? AND ABS(price_at_alert - ?) < 0.01 AND ts >= ?
               LIMIT 1""",
            (product_id, price, cutoff),
        ).fetchone()
        return row is not None


def record_alert(product_id, price, score):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts_sent (product_id, price_at_alert, score, ts) VALUES (?, ?, ?, ?)",
            (product_id, price, score, time.time()),
        )


def recent_deals(limit=50):
    """Últimas ofertas detectadas, para el dashboard."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id, p.store, p.url, p.title, p.category, p.image_url,
                   a.price_at_alert, a.score, a.ts
            FROM alerts_sent a
            JOIN products p ON p.id = a.product_id
            ORDER BY a.ts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_push_subscription(endpoint, subscription_json):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO push_subscriptions (endpoint, subscription_json, created_at)
               VALUES (?, ?, ?)""",
            (endpoint, subscription_json, time.time()),
        )


def all_push_subscriptions():
    with get_conn() as conn:
        rows = conn.execute("SELECT subscription_json FROM push_subscriptions").fetchall()
        return [r["subscription_json"] for r in rows]
