"""
Deterministic analytics for the SAP O2C dataset.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

from database import get_connection

logger = logging.getLogger(__name__)


def _safe_fetch(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        logger.warning(f"Analytics query failed: {e}")
        return []


def _count(conn: sqlite3.Connection, table: str) -> int:
    rows = _safe_fetch(conn, f'SELECT COUNT(*) AS c FROM {table}')
    return int(rows[0][0]) if rows else 0


def get_top_products(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            bdi."material" AS material,
            pd."productDescription" AS description,
            COUNT(DISTINCT bdi."billingDocument") AS billing_docs
        FROM billing_document_items bdi
        LEFT JOIN product_descriptions pd
          ON pd."product" = bdi."material" AND pd."language" = 'EN'
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdi."billingDocument"
        WHERE bc."billingDocument" IS NULL
        GROUP BY bdi."material", pd."productDescription"
        ORDER BY billing_docs DESC
        LIMIT ?
        """,
        (limit,),
    )
    total_items = _count(conn, "billing_document_items")
    distinct_products = _safe_fetch(
        conn,
        'SELECT COUNT(DISTINCT "material") FROM billing_document_items',
    )
    distinct_products = int(distinct_products[0][0]) if distinct_products else 0
    return {
        "rows": [
            {
                "material": r["material"],
                "description": r["description"],
                "billing_docs": int(r["billing_docs"]),
            }
            for r in rows
        ],
        "total_items": total_items,
        "distinct_products": distinct_products,
    }


def get_top_products_by_revenue(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            bdi."material" AS material,
            pd."productDescription" AS description,
            SUM(CAST(bdi."netAmount" AS REAL)) AS revenue,
            COUNT(DISTINCT bdi."billingDocument") AS billing_docs
        FROM billing_document_items bdi
        LEFT JOIN product_descriptions pd
          ON pd."product" = bdi."material" AND pd."language" = 'EN'
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdi."billingDocument"
        WHERE bc."billingDocument" IS NULL
        GROUP BY bdi."material", pd."productDescription"
        ORDER BY revenue DESC
        LIMIT ?
        """,
        (limit,),
    )
    total_items = _count(conn, "billing_document_items")
    return {
        "rows": [
            {
                "material": r["material"],
                "description": r["description"],
                "revenue": float(r["revenue"]) if r["revenue"] is not None else 0.0,
                "billing_docs": int(r["billing_docs"]),
            }
            for r in rows
        ],
        "total_items": total_items,
    }


def get_top_customers(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            bdh."soldToParty" AS customer,
            bp."businessPartnerFullName" AS name,
            SUM(CAST(bdh."totalNetAmount" AS REAL)) AS total_billed,
            COUNT(DISTINCT bdh."billingDocument") AS billing_docs
        FROM billing_document_headers bdh
        LEFT JOIN business_partners bp
          ON bp."businessPartner" = bdh."soldToParty"
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdh."billingDocument"
        WHERE bc."billingDocument" IS NULL
        GROUP BY bdh."soldToParty", bp."businessPartnerFullName"
        ORDER BY total_billed DESC
        LIMIT ?
        """,
        (limit,),
    )
    total_headers = _count(conn, "billing_document_headers")
    distinct_customers = _safe_fetch(
        conn,
        'SELECT COUNT(DISTINCT "soldToParty") FROM billing_document_headers',
    )
    distinct_customers = int(distinct_customers[0][0]) if distinct_customers else 0
    return {
        "rows": [
            {
                "customer": r["customer"],
                "name": r["name"],
                "total_billed": float(r["total_billed"]) if r["total_billed"] is not None else 0.0,
                "billing_docs": int(r["billing_docs"]),
            }
            for r in rows
        ],
        "total_headers": total_headers,
        "distinct_customers": distinct_customers,
    }


def get_top_plants(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            odi."plant" AS plant,
            p."plantName" AS name,
            COUNT(DISTINCT odi."deliveryDocument") AS deliveries
        FROM outbound_delivery_items odi
        LEFT JOIN plants p
          ON p."plant" = odi."plant"
        GROUP BY odi."plant", p."plantName"
        ORDER BY deliveries DESC
        LIMIT ?
        """,
        (limit,),
    )
    total_deliveries = _safe_fetch(
        conn,
        'SELECT COUNT(DISTINCT "deliveryDocument") FROM outbound_delivery_items',
    )
    total_deliveries = int(total_deliveries[0][0]) if total_deliveries else 0
    return {
        "rows": [
            {
                "plant": r["plant"],
                "name": r["name"],
                "deliveries": int(r["deliveries"]),
            }
            for r in rows
        ],
        "total_deliveries": total_deliveries,
    }


def get_top_regions(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            COALESCE(bpa."region", 'Unknown') AS region,
            COALESCE(bpa."country", 'Unknown') AS country,
            SUM(CAST(bdh."totalNetAmount" AS REAL)) AS total_billed,
            COUNT(DISTINCT bdh."billingDocument") AS billing_docs
        FROM billing_document_headers bdh
        LEFT JOIN business_partner_addresses bpa
          ON bpa."businessPartner" = bdh."soldToParty"
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdh."billingDocument"
        WHERE bc."billingDocument" IS NULL
        GROUP BY region, country
        ORDER BY total_billed DESC
        LIMIT ?
        """,
        (limit,),
    )
    return {
        "rows": [
            {
                "region": r["region"],
                "country": r["country"],
                "total_billed": float(r["total_billed"]) if r["total_billed"] is not None else 0.0,
                "billing_docs": int(r["billing_docs"]),
            }
            for r in rows
        ],
    }


def get_top_countries(conn: sqlite3.Connection, limit: int = 5) -> dict[str, Any]:
    rows = _safe_fetch(
        conn,
        """
        SELECT
            COALESCE(bpa."country", 'Unknown') AS country,
            SUM(CAST(bdh."totalNetAmount" AS REAL)) AS total_billed,
            COUNT(DISTINCT bdh."billingDocument") AS billing_docs
        FROM billing_document_headers bdh
        LEFT JOIN business_partner_addresses bpa
          ON bpa."businessPartner" = bdh."soldToParty"
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdh."billingDocument"
        WHERE bc."billingDocument" IS NULL
        GROUP BY country
        ORDER BY total_billed DESC
        LIMIT ?
        """,
        (limit,),
    )
    return {
        "rows": [
            {
                "country": r["country"],
                "total_billed": float(r["total_billed"]) if r["total_billed"] is not None else 0.0,
                "billing_docs": int(r["billing_docs"]),
            }
            for r in rows
        ],
    }


def get_broken_flows(conn: sqlite3.Connection) -> dict[str, Any]:
    delivered_not_billed = _safe_fetch(
        conn,
        """
        SELECT COUNT(DISTINCT odh."deliveryDocument") AS c
        FROM outbound_delivery_headers odh
        LEFT JOIN billing_document_items bdi
          ON bdi."referenceSdDocument" = odh."deliveryDocument"
        WHERE bdi."billingDocument" IS NULL
        """,
    )
    delivered_not_billed_count = int(delivered_not_billed[0][0]) if delivered_not_billed else 0
    delivered_not_billed_sample = [
        r[0] for r in _safe_fetch(
            conn,
            """
            SELECT DISTINCT odh."deliveryDocument"
            FROM outbound_delivery_headers odh
            LEFT JOIN billing_document_items bdi
              ON bdi."referenceSdDocument" = odh."deliveryDocument"
            WHERE bdi."billingDocument" IS NULL
            LIMIT 5
            """,
        )
    ]

    billed_no_delivery = _safe_fetch(
        conn,
        """
        SELECT COUNT(DISTINCT bdi."billingDocument") AS c
        FROM billing_document_items bdi
        LEFT JOIN outbound_delivery_headers odh
          ON bdi."referenceSdDocument" = odh."deliveryDocument"
        WHERE odh."deliveryDocument" IS NULL
        """,
    )
    billed_no_delivery_count = int(billed_no_delivery[0][0]) if billed_no_delivery else 0
    billed_no_delivery_sample = [
        r[0] for r in _safe_fetch(
            conn,
            """
            SELECT DISTINCT bdi."billingDocument"
            FROM billing_document_items bdi
            LEFT JOIN outbound_delivery_headers odh
              ON bdi."referenceSdDocument" = odh."deliveryDocument"
            WHERE odh."deliveryDocument" IS NULL
            LIMIT 5
            """,
        )
    ]

    billed_no_journal = _safe_fetch(
        conn,
        """
        SELECT COUNT(DISTINCT bdh."billingDocument") AS c
        FROM billing_document_headers bdh
        LEFT JOIN journal_entry_items_ar je
          ON je."referenceDocument" = bdh."billingDocument"
        LEFT JOIN billing_document_cancellations bc
          ON bc."billingDocument" = bdh."billingDocument"
        WHERE je."referenceDocument" IS NULL AND bc."billingDocument" IS NULL
        """,
    )
    billed_no_journal_count = int(billed_no_journal[0][0]) if billed_no_journal else 0
    billed_no_journal_sample = [
        r[0] for r in _safe_fetch(
            conn,
            """
            SELECT DISTINCT bdh."billingDocument"
            FROM billing_document_headers bdh
            LEFT JOIN journal_entry_items_ar je
              ON je."referenceDocument" = bdh."billingDocument"
            LEFT JOIN billing_document_cancellations bc
              ON bc."billingDocument" = bdh."billingDocument"
            WHERE je."referenceDocument" IS NULL AND bc."billingDocument" IS NULL
            LIMIT 5
            """,
        )
    ]

    unpaid = _safe_fetch(
        conn,
        """
        SELECT COUNT(DISTINCT je."accountingDocument") AS c
        FROM journal_entry_items_ar je
        LEFT JOIN payments_ar p
          ON p."accountingDocument" = je."accountingDocument"
        WHERE p."accountingDocument" IS NULL
        """,
    )
    unpaid_count = int(unpaid[0][0]) if unpaid else 0
    unpaid_sample = [
        r[0] for r in _safe_fetch(
            conn,
            """
            SELECT DISTINCT je."accountingDocument"
            FROM journal_entry_items_ar je
            LEFT JOIN payments_ar p
              ON p."accountingDocument" = je."accountingDocument"
            WHERE p."accountingDocument" IS NULL
            LIMIT 5
            """,
        )
    ]

    return {
        "delivered_not_billed": {"count": delivered_not_billed_count, "sample": delivered_not_billed_sample},
        "billed_no_delivery": {"count": billed_no_delivery_count, "sample": billed_no_delivery_sample},
        "billed_no_journal": {"count": billed_no_journal_count, "sample": billed_no_journal_sample},
        "unpaid": {"count": unpaid_count, "sample": unpaid_sample},
    }


def get_summary() -> dict[str, Any]:
    conn = get_connection()
    try:
        totals = {
            "customers": _count(conn, "business_partners"),
            "products": _count(conn, "products"),
            "sales_orders": _count(conn, "sales_order_headers"),
            "deliveries": _count(conn, "outbound_delivery_headers"),
            "billing_documents": _count(conn, "billing_document_headers"),
            "journal_entries": _count(conn, "journal_entry_items_ar"),
            "payments": _count(conn, "payments_ar"),
        }
        return {
            "totals": totals,
            "top_products": get_top_products(conn, 5)["rows"],
            "top_products_revenue": get_top_products_by_revenue(conn, 5)["rows"],
            "top_customers": get_top_customers(conn, 5)["rows"],
            "top_plants": get_top_plants(conn, 5)["rows"],
            "top_regions": get_top_regions(conn, 5)["rows"],
            "top_countries": get_top_countries(conn, 5)["rows"],
            "broken_flows": get_broken_flows(conn),
        }
    finally:
        conn.close()
