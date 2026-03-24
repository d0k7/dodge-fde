"""
Builds the in-memory NetworkX graph for the SAP O2C dataset.
"""
import networkx as nx
import sqlite3
import logging
from database import get_connection

logger = logging.getLogger(__name__)

_GRAPH: nx.DiGraph | None = None

NODE_COLORS = {
    "SalesOrder":    "#4A9EFF",
    "Delivery":      "#34D399",
    "Invoice":       "#F59E0B",
    "JournalEntry":  "#A78BFA",
    "Customer":      "#F87171",
    "Product":       "#60A5FA",
    "Plant":         "#6EE7B7",
    "Payment":       "#FB923C",
}

def build_graph() -> nx.DiGraph:
    """
    Build the O2C graph from SQLite.

    NODE TYPES + IDs:
      Customer     → CUST_{businessPartner}
      Product      → PROD_{product}
      Plant        → PLANT_{plant}
      SalesOrder   → SO_{salesOrder}
      Delivery     → DEL_{deliveryDocument}
      Invoice      → INV_{billingDocument}
      JournalEntry → JE_{accountingDocument}
      Payment      → PAY_{accountingDocument}_{accountingDocumentItem}

    EDGES:
      Customer   -[PLACED]---------> SalesOrder
      SalesOrder -[INCLUDES]-------> Product
      SalesOrder -[HAS_DELIVERY]---> Delivery
      Delivery   -[HAS_INVOICE]----> Invoice
      Invoice    -[HAS_JOURNAL]----> JournalEntry
      JournalEntry-[CLEARED_BY]----> Payment
    """
    global _GRAPH
    G = nx.DiGraph()
    conn = get_connection()

    _add_customers(G, conn)
    _add_products(G, conn)
    _add_plants(G, conn)
    _add_sales_orders(G, conn)
    _add_deliveries(G, conn)
    _add_invoices(G, conn)
    _add_journal_entries(G, conn)
    _add_payments(G, conn)

    conn.close()
    _GRAPH = G
    logger.info(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def get_graph() -> nx.DiGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def graph_to_json(G: nx.DiGraph | None = None) -> dict:
    if G is None:
        G = get_graph()
    nodes = []
    for node_id, attrs in G.nodes(data=True):
        nodes.append({
            "id": node_id,
            "label": attrs.get("label", node_id),
            "type": attrs.get("type", "Unknown"),
            "color": NODE_COLORS.get(attrs.get("type", ""), "#94A3B8"),
            "metadata": {k: v for k, v in attrs.items() if k not in ("type", "label")},
        })
    links = []
    for src, tgt, attrs in G.edges(data=True):
        links.append({"source": src, "target": tgt, "label": attrs.get("label", "")})
    return {"nodes": nodes, "links": links}


def get_neighbors(node_id: str, depth: int = 1) -> dict:
    G = get_graph()
    if node_id not in G:
        return {"nodes": [], "links": []}
    visited = {node_id}
    frontier = {node_id}
    for _ in range(depth):
        nxt = set()
        for n in frontier:
            nxt.update(G.predecessors(n))
            nxt.update(G.successors(n))
        nxt -= visited
        visited.update(nxt)
        frontier = nxt
    return graph_to_json(G.subgraph(visited))


# ── Private builders ──────────────────────────────────────────────────────────

def _q(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    try:
        return conn.execute(sql).fetchall()
    except Exception as e:
        logger.warning(f"Query skipped ({e}): {sql[:80]}")
        return []


def _add_customers(G, conn):
    for row in _q(conn, "SELECT * FROM business_partners"):
        r = dict(row)
        # businessPartner is the node ID; customer is the SAP customer number
        bp = r.get("businessPartner", "")
        if not bp:
            continue
        nid = f"CUST_{bp}"
        name = (r.get("businessPartnerFullName") or
                r.get("businessPartnerName") or
                r.get("organizationBpName1") or bp)
        G.add_node(nid, type="Customer", label=name[:40], **{k: v for k, v in r.items() if v})


def _add_products(G, conn):
    # Join products with product_descriptions (language EN preferred)
    rows = _q(conn, """
        SELECT p.product, p.productType, p.productGroup, p.baseUnit,
               COALESCE(pd.productDescription, p.product) AS description
        FROM products p
        LEFT JOIN product_descriptions pd
          ON pd.product = p.product AND pd.language = 'EN'
    """)
    for row in rows:
        r = dict(row)
        prod = r.get("product", "")
        if not prod:
            continue
        G.add_node(f"PROD_{prod}", type="Product",
                   label=r.get("description", prod)[:40],
                   product=prod, productType=r.get("productType", ""),
                   productGroup=r.get("productGroup", ""))


def _add_plants(G, conn):
    for row in _q(conn, "SELECT plant, plantName FROM plants"):
        r = dict(row)
        plant = r.get("plant", "")
        if not plant:
            continue
        G.add_node(f"PLANT_{plant}", type="Plant",
                   label=r.get("plantName", plant)[:40], plant=plant)


def _add_sales_orders(G, conn):
    for row in _q(conn, "SELECT * FROM sales_order_headers"):
        r = dict(row)
        so = r.get("salesOrder", "")
        if not so:
            continue
        nid = f"SO_{so}"
        G.add_node(nid, type="SalesOrder",
                   label=f"SO {so}",
                   **{k: v for k, v in r.items() if v and k != "salesOrder"})

        # Customer → SalesOrder
        sold_to = r.get("soldToParty", "")
        if sold_to:
            # soldToParty in sales_order_headers = businessPartner
            cnode = f"CUST_{sold_to}"
            if G.has_node(cnode):
                G.add_edge(cnode, nid, label="PLACED")

    # SalesOrder → Product (from items)
    for row in _q(conn, "SELECT DISTINCT salesOrder, material FROM sales_order_items WHERE material != ''"):
        r = dict(row)
        so_node = f"SO_{r['salesOrder']}"
        prod_node = f"PROD_{r['material']}"
        if G.has_node(so_node) and G.has_node(prod_node):
            G.add_edge(so_node, prod_node, label="INCLUDES")


def _add_deliveries(G, conn):
    for row in _q(conn, "SELECT * FROM outbound_delivery_headers"):
        r = dict(row)
        doc = r.get("deliveryDocument", "")
        if not doc:
            continue
        G.add_node(f"DEL_{doc}", type="Delivery",
                   label=f"Delivery {doc}",
                   **{k: v for k, v in r.items() if v and k != "deliveryDocument"})

    # SalesOrder → Delivery (via outbound_delivery_items.referenceSdDocument)
    for row in _q(conn, """
        SELECT DISTINCT referenceSdDocument, deliveryDocument
        FROM outbound_delivery_items
        WHERE referenceSdDocument != '' AND deliveryDocument != ''
    """):
        r = dict(row)
        so_node  = f"SO_{r['referenceSdDocument']}"
        del_node = f"DEL_{r['deliveryDocument']}"
        if G.has_node(so_node) and G.has_node(del_node):
            if not G.has_edge(so_node, del_node):
                G.add_edge(so_node, del_node, label="HAS_DELIVERY")


def _add_invoices(G, conn):
    # Only non-cancelled billing documents
    cancelled = {
        row[0] for row in _q(conn,
            "SELECT billingDocument FROM billing_document_cancellations"
        )
    }
    for row in _q(conn, "SELECT * FROM billing_document_headers"):
        r = dict(row)
        doc = r.get("billingDocument", "")
        if not doc or doc in cancelled:
            continue
        G.add_node(f"INV_{doc}", type="Invoice",
                   label=f"Invoice {doc}",
                   **{k: v for k, v in r.items() if v and k != "billingDocument"})

    # Delivery → Invoice (billing_document_items.referenceSdDocument = deliveryDocument)
    for row in _q(conn, """
        SELECT DISTINCT billingDocument, referenceSdDocument
        FROM billing_document_items
        WHERE billingDocument != '' AND referenceSdDocument != ''
    """):
        r = dict(row)
        inv_node = f"INV_{r['billingDocument']}"
        del_node = f"DEL_{r['referenceSdDocument']}"
        if G.has_node(inv_node) and G.has_node(del_node):
            if not G.has_edge(del_node, inv_node):
                G.add_edge(del_node, inv_node, label="HAS_INVOICE")


def _add_journal_entries(G, conn):
    seen: set[str] = set()
    for row in _q(conn, "SELECT * FROM journal_entry_items_ar"):
        r = dict(row)
        acc_doc = r.get("accountingDocument", "")
        if not acc_doc:
            continue
        nid = f"JE_{acc_doc}"
        if nid not in seen:
            G.add_node(nid, type="JournalEntry",
                       label=f"Journal {acc_doc}",
                       **{k: v for k, v in r.items() if v and k != "accountingDocument"})
            seen.add(nid)

        # Invoice → JournalEntry (referenceDocument = billingDocument)
        ref = r.get("referenceDocument", "")
        if ref:
            inv_node = f"INV_{ref}"
            if G.has_node(inv_node) and not G.has_edge(inv_node, nid):
                G.add_edge(inv_node, nid, label="HAS_JOURNAL")


def _add_payments(G, conn):
    seen: set[str] = set()
    for row in _q(conn, "SELECT * FROM payments_ar"):
        r = dict(row)
        acc_doc  = r.get("accountingDocument", "")
        acc_item = r.get("accountingDocumentItem", "")
        if not acc_doc:
            continue
        nid = f"PAY_{acc_doc}_{acc_item}"
        if nid not in seen:
            G.add_node(nid, type="Payment",
                       label=f"Payment {acc_doc}",
                       **{k: v for k, v in r.items() if v})
            seen.add(nid)

        # JournalEntry → Payment (accountingDocument match)
        je_node = f"JE_{acc_doc}"
        if G.has_node(je_node) and not G.has_edge(je_node, nid):
            G.add_edge(je_node, nid, label="CLEARED_BY")
