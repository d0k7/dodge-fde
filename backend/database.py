"""
Database utilities and ingestion pipeline for the SAP O2C dataset.
"""
import sqlite3, json, logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH  = Path(__file__).parent / "data" / "dodge.db"
DATA_DIR = Path(__file__).parent / "data" / "sap-o2c-data"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def get_schema_description() -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    parts = []
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [row[1] for row in cur.fetchall()]
        parts.append(f"  {t}({', '.join(cols)})")
    conn.close()
    return "DATABASE SCHEMA (SQLite, camelCase SAP columns):\n" + "\n".join(parts)

def _flatten(obj: dict, prefix: str = "") -> dict:
    result = {}
    for k, v in obj.items():
        key = f"{prefix}_{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        elif isinstance(v, list):
            result[key] = json.dumps(v)
        else:
            result[key] = v
    return result

def _read_jsonl_folder(folder_path: Path) -> list[dict]:
    records = []
    if not folder_path.exists():
        logger.warning(f"Folder not found: {folder_path}")
        return records
    for fpath in sorted(folder_path.iterdir()):
        if fpath.suffix.lower() not in (".jsonl", ".json"):
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(_flatten(json.loads(line)))
                    except json.JSONDecodeError as e:
                        logger.warning(f"{fpath.name}:{line_no} JSON error: {e}")
        except OSError as e:
            logger.error(f"Cannot read {fpath}: {e}")
    return records

def _insert_records(conn: sqlite3.Connection, table: str, records: list[dict]):
    if not records:
        return
    all_cols: list[str] = []
    seen: set[str] = set()
    for rec in records:
        for col in rec.keys():
            if col not in seen:
                all_cols.append(col)
                seen.add(col)
    safe = [f'"{c}"' for c in all_cols]
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in safe)})")
    placeholders = ", ".join("?" for _ in all_cols)
    sql = f"INSERT INTO {table} ({', '.join(safe)}) VALUES ({placeholders})"
    rows = [tuple("" if rec.get(c) is None else str(rec.get(c)) for c in all_cols) for rec in records]
    conn.executemany(sql, rows)
    logger.info(f"  {table}: {len(rows)} rows")

FOLDER_TABLE_MAP = {
    "billing_document_cancellations":          "billing_document_cancellations",
    "billing_document_headers":                "billing_document_headers",
    "billing_document_items":                  "billing_document_items",
    "business_partner_addresses":              "business_partner_addresses",
    "business_partners":                       "business_partners",
    "customer_company_assignments":            "customer_company_assignments",
    "customer_sales_area_assignments":         "customer_sales_area_assignments",
    "journal_entry_items_accounts_receivable": "journal_entry_items_ar",
    "outbound_delivery_headers":               "outbound_delivery_headers",
    "outbound_delivery_items":                 "outbound_delivery_items",
    "payments_accounts_receivable":            "payments_ar",
    "plants":                                  "plants",
    "product_descriptions":                    "product_descriptions",
    "product_plants":                          "product_plants",
    "product_storage_locations":               "product_storage_locations",
    "products":                                "products",
    "sales_order_headers":                     "sales_order_headers",
    "sales_order_items":                       "sales_order_items",
    "sales_order_schedule_lines":              "sales_order_schedule_lines",
}

def ingest_dataset():
    if not DATA_DIR.exists():
        logger.error(f"Dataset not found at: {DATA_DIR}")
        return []
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    ingested = []
    logger.info(f"Ingesting from: {DATA_DIR}")
    for folder_name, table_name in FOLDER_TABLE_MAP.items():
        records = _read_jsonl_folder(DATA_DIR / folder_name)
        if records:
            _insert_records(conn, table_name, records)
            ingested.append((table_name, len(records)))
    _create_indexes(conn)
    conn.commit()
    conn.close()
    logger.info(f"Done. {len(ingested)} tables loaded.")
    return ingested

def _create_indexes(conn: sqlite3.Connection):
    indexes = [
        ("sales_order_headers",    "salesOrder"),
        ("sales_order_headers",    "soldToParty"),
        ("sales_order_items",      "salesOrder"),
        ("sales_order_items",      "material"),
        ("outbound_delivery_headers", "deliveryDocument"),
        ("outbound_delivery_items",   "deliveryDocument"),
        ("outbound_delivery_items",   "referenceSdDocument"),
        ("billing_document_headers",  "billingDocument"),
        ("billing_document_headers",  "soldToParty"),
        ("billing_document_items",    "billingDocument"),
        ("billing_document_items",    "referenceSdDocument"),
        ("billing_document_cancellations", "billingDocument"),
        ("journal_entry_items_ar",    "referenceDocument"),
        ("journal_entry_items_ar",    "accountingDocument"),
        ("payments_ar",               "accountingDocument"),
        ("payments_ar",               "salesDocument"),
        ("business_partners",         "customer"),
        ("products",                  "product"),
        ("product_descriptions",      "product"),
        ("plants",                    "plant"),
    ]
    for table, col in indexes:
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}("{col}")')
        except Exception:
            pass
