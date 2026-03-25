"""
NL to SQL to Answer pipeline using Groq with guardrails.
"""
import os, re, json, sqlite3, logging
from groq import Groq
from database import get_connection, get_schema_description
from analytics import (
    get_top_products,
    get_top_products_by_revenue,
    get_top_customers,
    get_broken_flows,
    get_top_plants,
    get_top_regions,
    get_top_countries,
)

logger = logging.getLogger(__name__)

# ── Guardrail: fast blocklist ──────────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    "order", "delivery", "invoice", "billing", "payment", "journal", "entry",
    "customer", "material", "product", "plant", "sales", "shipment", "dispatch",
    "quantity", "amount", "currency", "date", "flow", "process", "account",
    "document", "vendor", "purchase", "goods", "receipt", "item", "line",
    "revenue", "cost", "profit", "center", "fiscal", "year", "gl", "ledger",
    "o2c", "p2p", "procure", "cash", "receivable", "payable", "balance",
    "supply", "chain", "erp", "sap", "transaction", "posting", "company", "code",
    "trace", "track", "identify", "which", "how many", "total", "list", "find",
    "show", "what", "when", "who", "status", "broken", "incomplete",
    "complete", "missing", "without", "highest", "lowest", "most", "least",
    "average", "sum", "count", "filter", "between", "before", "after",
    "cancelled", "blocked", "partner", "address", "region", "country",
    "schedule", "line", "confirmed", "delivery date", "sold to", "billing doc",
}

BLOCKED_TOPICS = [
    "recipe", "weather", "sport", "movie", "music", "song", "poem", "joke",
    "write a story", "essay", "capital of", "president of", "who invented",
    "meaning of life", "philosophy", "python tutorial", "javascript tutorial",
    "html tutorial", "hello world", "translate this", "summarize this article",
    "what is your name", "are you an ai", "tell me about yourself",
]

def is_likely_off_topic(query: str) -> bool:
    q = query.lower()
    for topic in BLOCKED_TOPICS:
        if topic in q:
            return True
    words = set(re.findall(r"\b\w+\b", q))
    if words & DOMAIN_KEYWORDS:
        return False
    if len(words) <= 4:
        return False
    return True


# ── System prompt ──────────────────────────────────────────────────────────────

RELATIONSHIP_GUIDE = """
KEY JOINS (use these for every multi-table query):
  sales_order_headers.salesOrder = sales_order_items.salesOrder
  sales_order_headers.soldToParty = business_partners.businessPartner
  outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
  outbound_delivery_items.deliveryDocument = outbound_delivery_headers.deliveryDocument
  billing_document_items.referenceSdDocument = outbound_delivery_headers.deliveryDocument
  billing_document_items.billingDocument = billing_document_headers.billingDocument
  billing_document_headers.soldToParty = business_partners.businessPartner
  journal_entry_items_ar.referenceDocument = billing_document_headers.billingDocument
  payments_ar.accountingDocument = journal_entry_items_ar.accountingDocument
  sales_order_items.material = products.product
  product_descriptions.product = products.product AND product_descriptions.language = 'EN'
  outbound_delivery_items.plant = plants.plant
  billing_document_cancellations.billingDocument = cancelled billing documents (exclude these)

BROKEN FLOW DETECTION:
  - Delivered but not billed: SO in outbound_delivery_headers but NOT in billing_document_items
  - Billed but no delivery:   SO in billing_document_items but NOT in outbound_delivery_headers  
  - Billed but no journal:    billingDocument NOT in journal_entry_items_ar.referenceDocument
  - Unpaid:                   accountingDocument NOT in payments_ar.accountingDocument
"""

def _system_prompt(schema: str) -> str:
    return f"""You are a data analyst for an SAP Order-to-Cash (O2C) system.
You ONLY answer questions about the provided SAP dataset. Reject all off-topic requests.

{schema}

{RELATIONSHIP_GUIDE}

TASK: Given the user's question, output ONLY a JSON object (no markdown, no explanation outside JSON):

If question is about the dataset:
{{"is_relevant": true, "sql": "SELECT ...", "explanation": "..."}}

If question is NOT about the dataset:
{{"is_relevant": false, "sql": null, "explanation": "This system only answers questions about the Order-to-Cash dataset."}}

SQL RULES:
- SELECT only (never INSERT, UPDATE, DELETE, DROP, ALTER)
- Column names are camelCase exactly as in the schema
- Quote column names with double quotes when they might conflict with SQL keywords
- Use LIMIT 50 unless user asks for specific count
- Exclude cancelled billing docs when billing documents are involved by using:
  "billingDocument" NOT IN (SELECT "billingDocument" FROM billing_document_cancellations)
- For product names always JOIN product_descriptions pd ON pd.product = x.material AND pd.language = 'EN'
- Use COALESCE for nullable fields
- Add meaningful ORDER BY
"""


def _answer_prompt(query: str, sql: str, results: list[dict]) -> str:
    count = len(results)
    preview = json.dumps(results[:15], default=str)
    return f"""User asked: "{query}"

SQL executed:
{sql}

Result: {count} row(s). First 15:
{preview}

Write a clear, specific answer in simple language:
- Use short sentences
- Explain like the reader is new to the topic
- Include actual values, counts, names from the data
- If 0 results: say no records were found for that request
- If many results: summarize key findings
- Under 150 words
- Do NOT mention SQL or technical details
- Do NOT invent information not in the results
- Do NOT speculate about cancellation or existence unless it is present in results

Format exactly 4 lines, no bullets:
Answer: <one sentence>
Evidence: <counts and 1-3 concrete values>
Insight: <what this means in plain language>
Coverage: <say "Based on N rows" or "No rows found">
"""


# ── Main chat function ─────────────────────────────────────────────────────────

OFF_TOPIC_REPLY = (
    "This system is designed to answer questions about the "
    "Order-to-Cash dataset only. Please ask about sales orders, "
    "deliveries, billing documents, journal entries, customers, "
    "or products."
)

def _is_transform_prompt(query: str) -> bool:
    q = query.strip().lower()
    return q.startswith("explain this in very simple words") or q.startswith("give me 3 key takeaways")


def _parse_structured_text(text: str) -> dict | None:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    data: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^(Answer|Evidence|Insight|Coverage):\s*(.*)$", line)
        if not m:
            continue
        data[m.group(1).lower()] = m.group(2).strip()
    if len(data) >= 2:
        return data
    return None


def _extract_last_structured(history: list[dict] | None) -> dict | None:
    if not history:
        return None
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        parsed = _parse_structured_text(str(msg.get("content", "")))
        if parsed:
            return parsed
    return None


def _build_simple_from_structured(structured: dict) -> str:
    answer = structured.get("answer", "Here is a simple summary.")
    evidence = structured.get("evidence", "No evidence available.")
    insight = structured.get("insight", "This explains the main result.")
    coverage = structured.get("coverage", "Coverage not available.")
    return _build_structured(answer, evidence, insight, coverage)


def _build_takeaways_from_structured(structured: dict) -> str:
    answer = structured.get("answer", "")
    evidence = structured.get("evidence", "")
    insight = structured.get("insight", "")
    coverage = structured.get("coverage", "")
    takeaways = [t for t in [answer, evidence, insight] if t]
    while len(takeaways) < 3:
        if coverage:
            takeaways.append(coverage)
        else:
            takeaways.append("No additional details available.")
    takeaways_text = f"1) {takeaways[0]} 2) {takeaways[1]} 3) {takeaways[2]}"
    coverage_lower = coverage.lower()
    evidence_lower = evidence.lower()
    if "no rows" in coverage_lower or "0 rows" in coverage_lower or "no records" in evidence_lower:
        risk = "No data was found, so the conclusion may be incomplete or the ID could be wrong."
    else:
        risk = "This is based only on the current dataset, so missing records could change the conclusion."
    return _build_structured(
        f"Takeaways: {takeaways_text}",
        f"Risk: {risk}",
        "These summarize the result in simple words.",
        coverage or "Coverage not available.",
    )


def chat(user_query: str, conversation_history: list[dict] | None = None) -> dict:
    if _is_transform_prompt(user_query):
        structured = _extract_last_structured(conversation_history)
        if not structured:
            return {
                "answer": _build_structured(
                    "Please ask a data question first.",
                    "No prior result was found to summarize.",
                    "Ask any Order-to-Cash question, then use Explain simply or Key takeaways.",
                    "No rows found.",
                ),
                "sql": None,
                "results": [],
                "is_relevant": True,
                "error": None,
            }
        if user_query.strip().lower().startswith("explain this in very simple words"):
            answer = _build_simple_from_structured(structured)
        else:
            answer = _build_takeaways_from_structured(structured)
        return {"answer": answer, "sql": None, "results": [], "is_relevant": True, "error": None}

    if is_likely_off_topic(user_query):
        return {"answer": OFF_TOPIC_REPLY, "sql": None, "results": [],
                "is_relevant": False, "error": None}

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"answer": "Set GROQ_API_KEY in backend/.env to enable chat.",
                "sql": None, "results": [], "is_relevant": True,
                "error": "Missing GROQ_API_KEY"}

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    schema = get_schema_description()

    # Deterministic trace flow for known entities
    if _is_trace_request(user_query):
        billing_doc = _extract_billing_document_id(user_query)
        if billing_doc:
            conn = get_connection()
            trace = _trace_billing_flow(conn, billing_doc)
            conn.close()
            return trace

    # Deterministic analytics queries
    if _is_top_products_revenue_query(user_query):
        conn = get_connection()
        data = get_top_products_by_revenue(conn, 5)
        conn.close()
        return _build_top_products_revenue_answer(data)

    if _is_top_products_query(user_query):
        conn = get_connection()
        data = get_top_products(conn, 5)
        conn.close()
        return _build_top_products_answer(data)

    if _is_top_customers_query(user_query):
        conn = get_connection()
        data = get_top_customers(conn, 5)
        conn.close()
        return _build_top_customers_answer(data)

    if _is_top_plants_query(user_query):
        conn = get_connection()
        data = get_top_plants(conn, 5)
        conn.close()
        return _build_top_plants_answer(data)

    if _is_top_countries_query(user_query):
        conn = get_connection()
        data = get_top_countries(conn, 5)
        conn.close()
        return _build_top_countries_answer(data)

    if _is_top_regions_query(user_query):
        conn = get_connection()
        data = get_top_regions(conn, 5)
        conn.close()
        return _build_top_regions_answer(data)

    if _is_broken_flow_query(user_query):
        conn = get_connection()
        data = get_broken_flows(conn)
        conn.close()
        return _build_broken_flows_answer(data)
        sales_order_id = _extract_sales_order_id(user_query)
        if sales_order_id:
            conn = get_connection()
            trace = _trace_sales_order_flow(conn, sales_order_id)
            conn.close()
            return trace
        delivery_id = _extract_delivery_id(user_query)
        if delivery_id:
            conn = get_connection()
            trace = _trace_delivery_flow(conn, delivery_id)
            conn.close()
            return trace

    if _is_product_billing_docs_query(user_query):
        product_id = _extract_product_id(user_query)
        if product_id:
            conn = get_connection()
            result = _get_billing_documents_for_product(conn, product_id)
            conn.close()
            return result

    # Step 1: generate SQL
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt(schema)},
                {"role": "user",   "content": user_query},
            ],
            temperature=0.05,
            max_tokens=600,
        )
        raw = _extract_llm_content(resp, "SQL generation")
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {"answer": f"LLM error: {e}", "sql": None, "results": [],
                "is_relevant": True, "error": str(e)}

    parsed = _parse_llm_json(raw)
    if not parsed.get("is_relevant", True):
        return {"answer": OFF_TOPIC_REPLY, "sql": None, "results": [],
                "is_relevant": False, "error": None}

    sql = parsed.get("sql")
    if not sql or not sql.strip().upper().startswith("SELECT"):
        return {"answer": parsed.get("explanation", "Could not generate a query. Try rephrasing."),
                "sql": None, "results": [], "is_relevant": True, "error": None}

    # Step 2: execute SQL
    conn = None
    try:
        conn = get_connection()
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"SQL error: {e}\n{sql}")
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        return _retry(client, model, schema, user_query, sql, str(e))

    # Step 2b: deterministic check for billing document existence or cancellation
    if not rows:
        billing_doc = _extract_billing_document_id(user_query)
        if billing_doc:
            status = _check_billing_document_status(conn, billing_doc)
            conn.close()
            if status == "cancelled":
                return {
                    "answer": _build_structured(
                        f"Billing document {billing_doc} is cancelled.",
                        "It appears in the cancellations table with a cancelled flag.",
                        "Cancelled documents do not have a complete flow to trace.",
                        "No rows found.",
                    ),
                    "sql": sql,
                    "results": rows,
                    "is_relevant": True,
                    "error": None,
                }
            if status == "exists":
                return {
                    "answer": _build_structured(
                        f"Billing document {billing_doc} exists, but no linked flow records were found.",
                        "A header or item record exists for this billing document.",
                        "This suggests downstream links are missing or not in the dataset.",
                        "No rows found.",
                    ),
                    "sql": sql,
                    "results": rows,
                    "is_relevant": True,
                    "error": None,
                }
            if status == "missing":
                return {
                    "answer": _build_structured(
                        f"No records found for billing document {billing_doc}.",
                        "No matching header or item records exist.",
                        "The document may be outside the loaded data or typed incorrectly.",
                        "No rows found.",
                    ),
                    "sql": sql,
                    "results": rows,
                    "is_relevant": True,
                    "error": None,
                }
        conn.close()
    else:
        conn.close()

    # Step 3: synthesise answer
    try:
        ans_resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content":
                    "You are a concise data analyst. Answer strictly from the provided results."},
                {"role": "user",   "content": _answer_prompt(user_query, sql, rows)},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        answer = _extract_llm_content(ans_resp, "Answer synthesis")
    except Exception:
        answer = _fallback_answer(rows)

    answer = _ensure_structured_answer(answer, rows)
    return {"answer": answer, "sql": sql, "results": rows,
            "is_relevant": True, "error": None}


def _parse_llm_json(raw: str) -> dict:
    clean = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", clean, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {"is_relevant": True, "sql": None, "explanation": raw}


def _extract_llm_content(resp, label: str) -> str:
    """
    Defensive content extraction for LLM responses.
    Avoids Optional content issues and produces a clear error if empty.
    """
    try:
        content = resp.choices[0].message.content
    except Exception as e:
        raise ValueError(f"{label} response missing content: {e}") from e
    if content is None or not str(content).strip():
        raise ValueError(f"{label} response was empty.")
    return str(content).strip()


def _retry(client, model: str, schema: str, query: str, bad_sql: str, error: str) -> dict:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt(schema)},
                {"role": "user", "content":
                    f"Previous SQL failed with: {error}\nBad SQL: {bad_sql}\n"
                    f"Fix it for: {query}\nReturn only JSON."},
            ],
            temperature=0.05, max_tokens=600,
        )
        parsed = _parse_llm_json(resp.choices[0].message.content)
        new_sql = parsed.get("sql", "")
        if new_sql and new_sql.strip().upper().startswith("SELECT"):
            conn = get_connection()
            cur = conn.execute(new_sql)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            conn.close()
            return {"answer": _fallback_answer(rows), "sql": new_sql,
                    "results": rows, "is_relevant": True, "error": None}
    except Exception:
        pass
    return {"answer": "Could not execute that query. Please try rephrasing.",
            "sql": bad_sql, "results": [], "is_relevant": True, "error": error}


def _is_trace_request(query: str) -> bool:
    q = query.lower()
    return any(p in q for p in ["trace", "full flow", "end to end", "flow of"])


def _is_top_products_query(query: str) -> bool:
    q = query.lower()
    return (
        any(k in q for k in ["product", "material"])
        and any(k in q for k in ["billing", "invoice"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_top_products_revenue_query(query: str) -> bool:
    q = query.lower()
    return (
        any(k in q for k in ["product", "material"])
        and any(k in q for k in ["revenue", "value", "amount", "net"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_top_customers_query(query: str) -> bool:
    q = query.lower()
    return (
        "customer" in q
        and any(k in q for k in ["billed", "billing", "invoice", "revenue", "amount"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_top_plants_query(query: str) -> bool:
    q = query.lower()
    return (
        "plant" in q
        and any(k in q for k in ["delivery", "deliveries", "shipped"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_top_regions_query(query: str) -> bool:
    q = query.lower()
    return (
        any(k in q for k in ["region", "location"])
        and any(k in q for k in ["billed", "billing", "invoice", "amount", "value"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_top_countries_query(query: str) -> bool:
    q = query.lower()
    return (
        "country" in q
        and any(k in q for k in ["billed", "billing", "invoice", "amount", "value"])
        and any(k in q for k in ["most", "highest", "top", "largest", "max"])
    )


def _is_broken_flow_query(query: str) -> bool:
    q = query.lower()
    return any(k in q for k in [
        "broken",
        "incomplete",
        "missing",
        "delivered but not billed",
        "billed but no delivery",
        "billed without delivery",
        "unpaid",
    ])


def _is_product_billing_docs_query(query: str) -> bool:
    q = query.lower()
    return (
        any(k in q for k in ["billing document", "billing documents", "billing docs", "invoice", "invoices"])
        and any(k in q for k in ["product", "material"])
    )


def _safe_float(val) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


def _get_billing_documents_for_product(conn: sqlite3.Connection, product_id: str, limit: int = 50) -> dict:
    rows = conn.execute(
        'SELECT bdi."billingDocument", bdi."billingDocumentItem", bdi."material", '
        'bdi."billingQuantity", bdi."billingQuantityUnit", bdi."netAmount", bdi."transactionCurrency", '
        'bdi."referenceSdDocument", bdi."referenceSdDocumentItem", '
        'bdh."billingDocumentType", bdh."creationDate", bdh."totalNetAmount", '
        'pd."productDescription" '
        'FROM billing_document_items bdi '
        'LEFT JOIN billing_document_headers bdh ON bdh."billingDocument" = bdi."billingDocument" '
        'LEFT JOIN product_descriptions pd ON pd."product" = bdi."material" AND pd."language" = "EN" '
        'WHERE bdi."material" = ? '
        'AND bdi."billingDocument" NOT IN (SELECT "billingDocument" FROM billing_document_cancellations) '
        'ORDER BY bdh."creationDate" DESC, bdi."billingDocument" DESC '
        f'LIMIT {int(limit)}',
        (product_id,),
    ).fetchall()

    cols = [
        "billingDocument", "billingDocumentItem", "material", "billingQuantity", "billingQuantityUnit",
        "netAmount", "transactionCurrency", "referenceSdDocument", "referenceSdDocumentItem",
        "billingDocumentType", "creationDate", "totalNetAmount", "productDescription",
    ]
    result_rows = [dict(zip(cols, r)) for r in rows]

    if not result_rows:
        return {
            "answer": _build_structured(
                f"No billing documents were found for product {product_id}.",
                "0 rows returned.",
                "This product does not appear in billing document items in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    doc_ids = [r["billingDocument"] for r in result_rows if r.get("billingDocument")]
    distinct_docs = list(dict.fromkeys(doc_ids))
    net_vals = [_safe_float(r.get("netAmount")) for r in result_rows]
    net_vals = [v for v in net_vals if v is not None]
    total_net = sum(net_vals) if net_vals else None
    samples = ", ".join(distinct_docs[:3]) if distinct_docs else "N/A"

    evidence = f"{len(distinct_docs)} billing documents across {len(result_rows)} items. Sample docs: {samples}."
    if total_net is not None:
        evidence = evidence + f" Total net amount across items: {total_net:.2f}."

    return {
        "answer": _build_structured(
            f"We found billing documents for product {product_id}.",
            evidence,
            "This shows the product is billed in multiple documents in the O2C flow.",
            f"Based on {len(result_rows)} billing item rows.",
        ),
        "sql": None,
        "results": result_rows,
        "is_relevant": True,
        "error": None,
    }


def _build_top_products_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No products with billing documents were found.",
                "0 rows returned.",
                "There are no billing document items in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top products by number of billing documents are " + ", ".join(
        [f"{r['material']}" for r in top]
    ) + "."
    evidence = "; ".join(
        [f"{r['material']} has {r['billing_docs']} billing documents" for r in top]
    ) + "."
    insight = "These products appear most often in billing documents, indicating higher sales activity."
    coverage = f"Based on {data.get('total_items', 0)} billing items across {data.get('distinct_products', 0)} products."

    results = [{"material": r["material"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}


def _build_top_products_revenue_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No products with billed revenue were found.",
                "0 rows returned.",
                "There are no billing document items in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top products by billed revenue are " + ", ".join([r["material"] for r in top]) + "."
    evidence = "; ".join(
        [f"{r['material']} billed {round(r['revenue'], 2)}" for r in top]
    ) + "."
    insight = "These products contribute the most billed value in the dataset."
    coverage = f"Based on {data.get('total_items', 0)} billing items."

    results = [{"material": r["material"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}

def _build_top_customers_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No customers with billed amounts were found.",
                "0 rows returned.",
                "There are no billing document headers in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top customers by billed amount are " + ", ".join(
        [f"{r['customer']}" for r in top]
    ) + "."
    evidence = "; ".join(
        [f"{r['customer']} billed {round(r['total_billed'], 2)}" for r in top]
    ) + "."
    insight = "These customers generate the highest billed value in the dataset."
    coverage = f"Based on {data.get('total_headers', 0)} billing headers across {data.get('distinct_customers', 0)} customers."

    results = [{"customer": r["customer"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}


def _build_top_plants_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No plants with deliveries were found.",
                "0 rows returned.",
                "There are no delivery items in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top plants by deliveries are " + ", ".join([r["plant"] for r in top]) + "."
    evidence = "; ".join(
        [f"{r['plant']} has {r['deliveries']} deliveries" for r in top]
    ) + "."
    insight = "These plants handle the highest delivery volume in the dataset."
    coverage = f"Based on {data.get('total_deliveries', 0)} total deliveries."

    results = [{"plant": r["plant"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}


def _build_top_regions_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No regions with billed amounts were found.",
                "0 rows returned.",
                "There are no billing document headers in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top regions by billed value are " + ", ".join(
        [f"{r['region']} ({r['country']})" for r in top]
    ) + "."
    evidence = "; ".join(
        [f"{r['region']} billed {round(r['total_billed'], 2)}" for r in top]
    ) + "."
    insight = "These regions generate the highest billed value in the dataset."
    coverage = "Based on billing headers joined with customer address regions."

    results = [{"region": r["region"], "country": r["country"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}


def _build_top_countries_answer(data: dict) -> dict:
    rows = data.get("rows", [])
    if not rows:
        return {
            "answer": _build_structured(
                "No countries with billed value were found.",
                "0 rows returned.",
                "There are no billing document headers in this dataset.",
                "No rows found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    top = rows[:3]
    answer = "Top countries by billed value are " + ", ".join([r["country"] for r in top]) + "."
    evidence = "; ".join(
        [f"{r['country']} billed {round(r['total_billed'], 2)}" for r in top]
    ) + "."
    insight = "These countries generate the highest billed value in the dataset."
    coverage = "Based on billing headers joined with customer address countries."

    results = [{"country": r["country"]} for r in rows]
    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}

def _build_broken_flows_answer(data: dict) -> dict:
    dnb = data.get("delivered_not_billed", {})
    bnd = data.get("billed_no_delivery", {})
    bnj = data.get("billed_no_journal", {})
    unpaid = data.get("unpaid", {})

    answer = (
        f"Broken flow checks found {dnb.get('count', 0)} delivered but not billed, "
        f"{bnd.get('count', 0)} billed without delivery, "
        f"{bnj.get('count', 0)} billed without journal, "
        f"{unpaid.get('count', 0)} unpaid."
    )
    evidence = (
        f"Samples: deliveries {', '.join(dnb.get('sample', [])[:3]) or 'none'}; "
        f"billing docs {', '.join(bnd.get('sample', [])[:3]) or 'none'}; "
        f"no-journal bills {', '.join(bnj.get('sample', [])[:3]) or 'none'}; "
        f"unpaid journals {', '.join(unpaid.get('sample', [])[:3]) or 'none'}."
    )
    insight = "These gaps show where the O2C process stops before full completion."
    coverage = "Based on delivery, billing, journal, and payment tables."

    results = []
    for d in dnb.get("sample", []):
        results.append({"delivery_document": d})
    for b in bnd.get("sample", []):
        results.append({"billing_document": b})
    for b in bnj.get("sample", []):
        results.append({"billing_document": b})
    for j in unpaid.get("sample", []):
        results.append({"accounting_document": j})

    return {"answer": _build_structured(answer, evidence, insight, coverage),
            "sql": None, "results": results, "is_relevant": True, "error": None}


def _trace_billing_flow(conn: sqlite3.Connection, billing_doc: str) -> dict:
    # Check cancellation
    cancelled = False
    try:
        row = conn.execute(
            'SELECT "billingDocumentIsCancelled" FROM billing_document_cancellations WHERE "billingDocument" = ? LIMIT 1',
            (billing_doc,),
        ).fetchone()
        if row is not None:
            val = str(row[0]).lower()
            cancelled = val in {"1", "true", "t", "yes", "y"}
    except Exception:
        pass

    header = conn.execute(
        'SELECT "billingDocument","billingDocumentDate","billingDocumentType","totalNetAmount","transactionCurrency","companyCode","fiscalYear","accountingDocument","soldToParty" '
        'FROM billing_document_headers WHERE "billingDocument" = ? LIMIT 1',
        (billing_doc,),
    ).fetchone()

    items = conn.execute(
        'SELECT "billingDocumentItem","material","billingQuantity","netAmount","transactionCurrency","referenceSdDocument","referenceSdDocumentItem" '
        'FROM billing_document_items WHERE "billingDocument" = ?',
        (billing_doc,),
    ).fetchall()

    materials = conn.execute(
        'SELECT DISTINCT bdi."material", pd."productDescription" '
        'FROM billing_document_items bdi '
        'LEFT JOIN product_descriptions pd ON pd."product" = bdi."material" AND pd."language" = "EN" '
        'WHERE bdi."billingDocument" = ?',
        (billing_doc,),
    ).fetchall()

    deliveries = conn.execute(
        'SELECT DISTINCT odi."deliveryDocument", odi."referenceSdDocument", odi."referenceSdDocumentItem", odi."plant", odi."actualDeliveryQuantity" '
        'FROM outbound_delivery_items odi '
        'JOIN billing_document_items bdi ON bdi."referenceSdDocument" = odi."deliveryDocument" '
        'WHERE bdi."billingDocument" = ?',
        (billing_doc,),
    ).fetchall()

    sales_orders = conn.execute(
        'SELECT DISTINCT soh."salesOrder", soh."soldToParty", soh."creationDate", soh."totalNetAmount", soh."transactionCurrency" '
        'FROM sales_order_headers soh '
        'JOIN outbound_delivery_items odi ON odi."referenceSdDocument" = soh."salesOrder" '
        'JOIN billing_document_items bdi ON bdi."referenceSdDocument" = odi."deliveryDocument" '
        'WHERE bdi."billingDocument" = ?',
        (billing_doc,),
    ).fetchall()

    journals = conn.execute(
        'SELECT DISTINCT "accountingDocument","accountingDocumentItem","postingDate","amountInTransactionCurrency","transactionCurrency" '
        'FROM journal_entry_items_ar WHERE "referenceDocument" = ?',
        (billing_doc,),
    ).fetchall()

    payments = conn.execute(
        'SELECT DISTINCT "accountingDocument","clearingAccountingDocument","clearingDate","amountInTransactionCurrency","transactionCurrency" '
        'FROM payments_ar WHERE "accountingDocument" IN '
        '(SELECT "accountingDocument" FROM journal_entry_items_ar WHERE "referenceDocument" = ?)',
        (billing_doc,),
    ).fetchall()

    # Customer name lookup
    cust_id = header[8] if header else (sales_orders[0][1] if sales_orders else None)
    cust_name = None
    if cust_id:
        row = conn.execute(
            'SELECT "businessPartnerFullName" FROM business_partners WHERE "businessPartner" = ? OR "customer" = ? LIMIT 1',
            (cust_id, cust_id),
        ).fetchone()
        if row:
            cust_name = row[0]

    # Build answer
    if not header and not items:
        if cancelled:
            answer = (
                f"Answer: Billing document {billing_doc} is cancelled.\n"
                "Evidence: It appears in the cancellations table with a cancelled flag.\n"
                "Insight: Cancelled documents do not have a complete flow to trace.\n"
                "Coverage: No flow records found."
            )
        else:
            delivery_row = conn.execute(
                'SELECT 1 FROM outbound_delivery_headers WHERE "deliveryDocument" = ? LIMIT 1',
                (billing_doc,),
            ).fetchone()
            if delivery_row:
                billing_docs = conn.execute(
                    'SELECT DISTINCT "billingDocument" FROM billing_document_items '
                    'WHERE "referenceSdDocument" = ? '
                    'AND "billingDocument" NOT IN (SELECT "billingDocument" FROM billing_document_cancellations)',
                    (billing_doc,),
                ).fetchall()
                doc_ids = [r[0] for r in billing_docs if r and r[0]]
                if doc_ids:
                    answer = _build_structured(
                        f"{billing_doc} looks like a delivery document, not a billing document.",
                        f"Delivery {billing_doc} links to billing document(s): {', '.join(doc_ids[:5])}.",
                        "Use one of the billing documents above to trace the full flow.",
                        f"Based on {len(doc_ids)} linked billing documents.",
                    )
                    results = [{"delivery_id": billing_doc}] + [{"billing_document": d} for d in doc_ids]
                    return {
                        "answer": answer,
                        "sql": None,
                        "results": results,
                        "is_relevant": True,
                        "error": None,
                        "auto_followup": f"Trace the full flow of billing document {doc_ids[0]}",
                        "auto_followup_reason": "Detected a delivery document ID. Auto-tracing the linked billing document.",
                    }
                answer = _build_structured(
                    f"{billing_doc} looks like a delivery document, not a billing document.",
                    "The delivery exists but no linked billing documents were found.",
                    "This suggests the billing step is missing for this delivery in the dataset.",
                    "No billing documents found.",
                )
                results = [{"delivery_id": billing_doc}]
                return {
                    "answer": answer,
                    "sql": None,
                    "results": results,
                    "is_relevant": True,
                    "error": None,
                    "auto_followup": None,
                    "auto_followup_reason": None,
                }
            answer = (
                f"Answer: I could not find billing document {billing_doc} in this dataset.\n"
                "Evidence: No header or item records match this billing document.\n"
                "Insight: The document may be outside the loaded data or typed incorrectly.\n"
                "Coverage: No records found."
            )
        return {"answer": answer, "sql": None, "results": [], "is_relevant": True, "error": None}

    so_ids = [r[0] for r in sales_orders]
    del_ids = [r[0] for r in deliveries]
    je_ids = [r[0] for r in journals]
    pay_ids = [r[1] for r in payments if r[1]]

    header_line = f"Answer: Billing document {billing_doc} found."
    if header:
        header_line = (
            f"Answer: Billing document {billing_doc} found. "
            f"Type {header[2]}, date {header[1]}, amount {header[3]} {header[4]}."
        )

    evidence_parts = []
    if cust_id:
        evidence_parts.append(f"Customer {cust_id}" + (f" ({cust_name})" if cust_name else ""))
    evidence_parts.append("Sales orders " + (", ".join(so_ids[:5]) if so_ids else "not found"))
    evidence_parts.append("Deliveries " + (", ".join(del_ids[:5]) if del_ids else "not found"))
    evidence_parts.append("Journal entries " + (", ".join(je_ids[:5]) if je_ids else "not found"))
    evidence_parts.append("Payments " + (", ".join(pay_ids[:5]) if pay_ids else "not found"))

    insight_bits = []
    if cancelled:
        insight_bits.append("This billing document is cancelled, so later steps can be missing.")
    missing = []
    if not so_ids:
        missing.append("sales order")
    if not del_ids:
        missing.append("delivery")
    if not je_ids:
        missing.append("journal entry")
    if not pay_ids:
        missing.append("payment")
    if missing:
        insight_bits.append("Missing steps: " + ", ".join(missing) + ".")
        insight_bits.append("This usually means the process did not reach those stages in this dataset.")
    else:
        insight_bits.append("All major steps are present.")

    material_line = ""
    if materials:
        mat_list = [f"{m[0]}{f' ({m[1]})' if m[1] else ''}" for m in materials[:5]]
        material_line = " Materials " + ", ".join(mat_list)

    answer = (
        f"{header_line}\n"
        f"Evidence: " + "; ".join(evidence_parts) + (material_line + "." if material_line else ".") + "\n"
        f"Insight: " + " ".join(insight_bits) + "\n"
        f"Coverage: Based on "
        f"{len(items)} billing item rows, {len(deliveries)} delivery rows, "
        f"{len(journals)} journal rows, {len(payments)} payment rows."
    )

    # Build results for UI highlighting
    results = []
    results.append({"billing_document": billing_doc})
    if cust_id:
        results.append({"customer_id": cust_id})
    for so in so_ids:
        results.append({"sales_order_id": so})
    for d in del_ids:
        results.append({"delivery_id": d})
    for je in je_ids:
        results.append({"accounting_document": je})
    for m in [m[0] for m in materials]:
        results.append({"material": m})

    return {"answer": answer, "sql": None, "results": results, "is_relevant": True, "error": None}


def _trace_sales_order_flow(conn: sqlite3.Connection, sales_order_id: str) -> dict:
    header = conn.execute(
        'SELECT "salesOrder","salesOrderType","creationDate","totalNetAmount","transactionCurrency","soldToParty" '
        'FROM sales_order_headers WHERE "salesOrder" = ? LIMIT 1',
        (sales_order_id,),
    ).fetchone()

    items = conn.execute(
        'SELECT "salesOrderItem","material","requestedQuantity","netAmount","transactionCurrency" '
        'FROM sales_order_items WHERE "salesOrder" = ?',
        (sales_order_id,),
    ).fetchall()

    deliveries = conn.execute(
        'SELECT DISTINCT "deliveryDocument" FROM outbound_delivery_items WHERE "referenceSdDocument" = ?',
        (sales_order_id,),
    ).fetchall()
    delivery_ids = [r[0] for r in deliveries if r and r[0]]

    billing_docs = []
    if delivery_ids:
        placeholders = ",".join("?" for _ in delivery_ids)
        billing_docs = conn.execute(
            f'SELECT DISTINCT "billingDocument" FROM billing_document_items WHERE "referenceSdDocument" IN ({placeholders})',
            delivery_ids,
        ).fetchall()
    billing_ids = [r[0] for r in billing_docs if r and r[0]]

    journals = []
    if billing_ids:
        placeholders = ",".join("?" for _ in billing_ids)
        journals = conn.execute(
            f'SELECT DISTINCT "accountingDocument" FROM journal_entry_items_ar WHERE "referenceDocument" IN ({placeholders})',
            billing_ids,
        ).fetchall()
    journal_ids = [r[0] for r in journals if r and r[0]]

    payments = []
    if journal_ids:
        placeholders = ",".join("?" for _ in journal_ids)
        payments = conn.execute(
            f'SELECT DISTINCT "clearingAccountingDocument" FROM payments_ar WHERE "accountingDocument" IN ({placeholders})',
            journal_ids,
        ).fetchall()
    payment_ids = [r[0] for r in payments if r and r[0]]

    materials = conn.execute(
        'SELECT DISTINCT soi."material", pd."productDescription" '
        'FROM sales_order_items soi '
        'LEFT JOIN product_descriptions pd ON pd."product" = soi."material" AND pd."language" = "EN" '
        'WHERE soi."salesOrder" = ?',
        (sales_order_id,),
    ).fetchall()

    cust_id = header[5] if header else None
    cust_name = None
    if cust_id:
        row = conn.execute(
            'SELECT "businessPartnerFullName" FROM business_partners WHERE "businessPartner" = ? OR "customer" = ? LIMIT 1',
            (cust_id, cust_id),
        ).fetchone()
        if row:
            cust_name = row[0]

    if not header and not items:
        return {
            "answer": _build_structured(
                f"I could not find sales order {sales_order_id}.",
                "No header or item records match this sales order.",
                "The sales order may be outside the loaded data or typed incorrectly.",
                "No records found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    answer_line = f"Sales order {sales_order_id} found."
    if header:
        answer_line = (
            f"Sales order {sales_order_id} found. "
            f"Type {header[1]}, date {header[2]}, value {header[3]} {header[4]}."
        )

    evidence_parts = []
    if cust_id:
        evidence_parts.append(f"Customer {cust_id}" + (f" ({cust_name})" if cust_name else ""))
    evidence_parts.append("Deliveries " + (", ".join(delivery_ids[:5]) if delivery_ids else "not found"))
    evidence_parts.append("Billing docs " + (", ".join(billing_ids[:5]) if billing_ids else "not found"))
    evidence_parts.append("Journal entries " + (", ".join(journal_ids[:5]) if journal_ids else "not found"))
    evidence_parts.append("Payments " + (", ".join(payment_ids[:5]) if payment_ids else "not found"))

    missing = []
    if not delivery_ids:
        missing.append("delivery")
    if not billing_ids:
        missing.append("billing document")
    if not journal_ids:
        missing.append("journal entry")
    if not payment_ids:
        missing.append("payment")

    insight = "All major steps are present."
    if missing:
        insight = "Missing steps: " + ", ".join(missing) + ". This usually means the process did not reach those stages in this dataset."

    material_line = ""
    if materials:
        mat_list = [f"{m[0]}{f' ({m[1]})' if m[1] else ''}" for m in materials[:5]]
        material_line = " Materials " + ", ".join(mat_list) + "."

    answer = _build_structured(
        answer_line,
        "; ".join(evidence_parts) + (material_line if material_line else ""),
        insight,
        f"Based on {len(items)} item rows, {len(delivery_ids)} delivery rows, {len(billing_ids)} billing rows.",
    )

    results = [{"sales_order_id": sales_order_id}]
    if cust_id:
        results.append({"customer_id": cust_id})
    for d in delivery_ids:
        results.append({"delivery_id": d})
    for b in billing_ids:
        results.append({"billing_document": b})
    for j in journal_ids:
        results.append({"accounting_document": j})
    for m in [m[0] for m in materials]:
        results.append({"material": m})

    return {"answer": answer, "sql": None, "results": results, "is_relevant": True, "error": None}


def _trace_delivery_flow(conn: sqlite3.Connection, delivery_id: str) -> dict:
    header = conn.execute(
        'SELECT "deliveryDocument","creationDate","shippingPoint" '
        'FROM outbound_delivery_headers WHERE "deliveryDocument" = ? LIMIT 1',
        (delivery_id,),
    ).fetchone()

    items = conn.execute(
        'SELECT "deliveryDocumentItem","referenceSdDocument","referenceSdDocumentItem","plant","actualDeliveryQuantity" '
        'FROM outbound_delivery_items WHERE "deliveryDocument" = ?',
        (delivery_id,),
    ).fetchall()

    sales_orders = [r[1] for r in items if r and r[1]]
    sales_orders = list(dict.fromkeys(sales_orders))

    billing_docs = conn.execute(
        'SELECT DISTINCT "billingDocument" FROM billing_document_items WHERE "referenceSdDocument" = ?',
        (delivery_id,),
    ).fetchall()
    billing_ids = [r[0] for r in billing_docs if r and r[0]]

    journals = []
    if billing_ids:
        placeholders = ",".join("?" for _ in billing_ids)
        journals = conn.execute(
            f'SELECT DISTINCT "accountingDocument" FROM journal_entry_items_ar WHERE "referenceDocument" IN ({placeholders})',
            billing_ids,
        ).fetchall()
    journal_ids = [r[0] for r in journals if r and r[0]]

    payments = []
    if journal_ids:
        placeholders = ",".join("?" for _ in journal_ids)
        payments = conn.execute(
            f'SELECT DISTINCT "clearingAccountingDocument" FROM payments_ar WHERE "accountingDocument" IN ({placeholders})',
            journal_ids,
        ).fetchall()
    payment_ids = [r[0] for r in payments if r and r[0]]

    materials = conn.execute(
        'SELECT DISTINCT soi."material", pd."productDescription" '
        'FROM outbound_delivery_items odi '
        'LEFT JOIN sales_order_items soi ON soi."salesOrder" = odi."referenceSdDocument" '
        'AND soi."salesOrderItem" = odi."referenceSdDocumentItem" '
        'LEFT JOIN product_descriptions pd ON pd."product" = soi."material" AND pd."language" = "EN" '
        'WHERE odi."deliveryDocument" = ?',
        (delivery_id,),
    ).fetchall()

    cust_id = None
    if sales_orders:
        row = conn.execute(
            'SELECT "soldToParty" FROM sales_order_headers WHERE "salesOrder" = ? LIMIT 1',
            (sales_orders[0],),
        ).fetchone()
        if row:
            cust_id = row[0]
    cust_name = None
    if cust_id:
        row = conn.execute(
            'SELECT "businessPartnerFullName" FROM business_partners WHERE "businessPartner" = ? OR "customer" = ? LIMIT 1',
            (cust_id, cust_id),
        ).fetchone()
        if row:
            cust_name = row[0]

    if not header and not items:
        return {
            "answer": _build_structured(
                f"I could not find delivery {delivery_id}.",
                "No header or item records match this delivery document.",
                "The delivery may be outside the loaded data or typed incorrectly.",
                "No records found.",
            ),
            "sql": None,
            "results": [],
            "is_relevant": True,
            "error": None,
        }

    answer_line = f"Delivery {delivery_id} found."
    if header:
        answer_line = (
            f"Delivery {delivery_id} found. "
            f"Date {header[1]}, shipping point {header[2]}."
        )

    evidence_parts = []
    if cust_id:
        evidence_parts.append(f"Customer {cust_id}" + (f" ({cust_name})" if cust_name else ""))
    evidence_parts.append("Sales orders " + (", ".join(sales_orders[:5]) if sales_orders else "not found"))
    evidence_parts.append("Billing docs " + (", ".join(billing_ids[:5]) if billing_ids else "not found"))
    evidence_parts.append("Journal entries " + (", ".join(journal_ids[:5]) if journal_ids else "not found"))
    evidence_parts.append("Payments " + (", ".join(payment_ids[:5]) if payment_ids else "not found"))

    missing = []
    if not sales_orders:
        missing.append("sales order")
    if not billing_ids:
        missing.append("billing document")
    if not journal_ids:
        missing.append("journal entry")
    if not payment_ids:
        missing.append("payment")

    insight = "All major steps are present."
    if missing:
        insight = "Missing steps: " + ", ".join(missing) + ". This usually means the process did not reach those stages in this dataset."

    material_line = ""
    if materials:
        mat_list = [f"{m[0]}{f' ({m[1]})' if m[1] else ''}" for m in materials[:5]]
        material_line = " Materials " + ", ".join(mat_list) + "."

    answer = _build_structured(
        answer_line,
        "; ".join(evidence_parts) + (material_line if material_line else ""),
        insight,
        f"Based on {len(items)} delivery item rows, {len(billing_ids)} billing rows.",
    )

    results = [{"delivery_id": delivery_id}]
    if cust_id:
        results.append({"customer_id": cust_id})
    for so in sales_orders:
        results.append({"sales_order_id": so})
    for b in billing_ids:
        results.append({"billing_document": b})
    for j in journal_ids:
        results.append({"accounting_document": j})
    for m in [m[0] for m in materials]:
        results.append({"material": m})

    return {"answer": answer, "sql": None, "results": results, "is_relevant": True, "error": None}


def _extract_billing_document_id(query: str) -> str | None:
    m = re.search(r"billing\s+document\s*(\d{6,10})", query, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b\d{8}\b", query)
    if m:
        return m.group(0)
    return None


def _extract_sales_order_id(query: str) -> str | None:
    m = re.search(r"(?:sales\s+order|so)\s*(\d{5,10})", query, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_delivery_id(query: str) -> str | None:
    m = re.search(r"(?:delivery|del)\s*(\d{5,10})", query, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _extract_product_id(query: str) -> str | None:
    m = re.search(r"(?:product|material)\s*([A-Za-z0-9_-]{6,})", query, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\bS\d{6,}\b", query, re.IGNORECASE)
    if m:
        return m.group(0)
    return None


def _check_billing_document_status(conn: sqlite3.Connection, billing_doc: str) -> str:
    """
    Returns:
      cancelled, exists, missing
    """
    try:
        row = conn.execute(
            'SELECT "billingDocumentIsCancelled" FROM billing_document_cancellations WHERE "billingDocument" = ? LIMIT 1',
            (billing_doc,),
        ).fetchone()
        if row is not None:
            val = str(row[0]).lower()
            if val in {"1", "true", "t", "yes", "y"}:
                return "cancelled"
    except Exception:
        pass

    try:
        row = conn.execute(
            'SELECT 1 FROM billing_document_headers WHERE "billingDocument" = ? LIMIT 1',
            (billing_doc,),
        ).fetchone()
        if row is not None:
            return "exists"
    except Exception:
        pass

    try:
        row = conn.execute(
            'SELECT 1 FROM billing_document_items WHERE "billingDocument" = ? LIMIT 1',
            (billing_doc,),
        ).fetchone()
        if row is not None:
            return "exists"
    except Exception:
        pass

    return "missing"


def _build_structured(answer: str, evidence: str, insight: str, coverage: str) -> str:
    return (
        f"Answer: {answer}\n"
        f"Evidence: {evidence}\n"
        f"Insight: {insight}\n"
        f"Coverage: {coverage}"
    )


def _ensure_structured_answer(answer: str, rows: list[dict]) -> str:
    lines = [l.strip() for l in answer.splitlines() if l.strip()]
    if lines and all(re.match(r"^(Answer|Evidence|Insight|Coverage):", l) for l in lines):
        return answer

    cleaned = " ".join(answer.split())
    if not cleaned:
        cleaned = "No records were found for this request."

    if not rows:
        return _build_structured(
            cleaned if cleaned.endswith(".") else cleaned + ".",
            "0 rows returned.",
            "This specific data does not appear in the dataset.",
            "No rows found.",
        )

    sample_parts = []
    first = rows[0] if rows else {}
    for k, v in first.items():
        if v is None or v == "":
            continue
        sample_parts.append(f"{k}={v}")
        if len(sample_parts) >= 3:
            break
    if not sample_parts and first:
        k = list(first.keys())[0]
        sample_parts.append(f"{k}={first.get(k)}")

    evidence = f"{len(rows)} rows. Sample: " + ", ".join(sample_parts) + "."
    return _build_structured(
        cleaned if cleaned.endswith(".") else cleaned + ".",
        evidence,
        "These are the closest matches in the dataset.",
        f"Based on {len(rows)} rows.",
    )


def _fallback_answer(results: list[dict]) -> str:
    if not results:
        return (
            "Answer: No records were found for this request.\n"
            "Evidence: 0 rows returned.\n"
            "Insight: This specific data does not appear in the dataset.\n"
            "Coverage: No rows found."
        )
    if len(results) == 1:
        parts = [f"{k}: {v}" for k, v in results[0].items() if v]
        return (
            "Answer: 1 record found.\n"
            f"Evidence: {', '.join(parts[:6])}.\n"
            "Insight: This is the single matching entry for your request.\n"
            "Coverage: Based on 1 row."
        )
    keys = list(results[0].keys())
    vals = [str(r.get(keys[0], "")) for r in results[:5]]
    return (
        f"Answer: {len(results)} records found.\n"
        f"Evidence: Sample values {', '.join(vals)}.\n"
        "Insight: These are the top matches for your request.\n"
        f"Coverage: Based on {len(results)} rows."
    )
