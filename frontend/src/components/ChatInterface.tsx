import { useState, useRef, useEffect } from 'react';
import type { KeyboardEvent } from 'react';
import { Send, Code2, ChevronDown, ChevronUp, AlertTriangle, Sparkles, Database, MessageCircle, BarChart3, Lightbulb, Layers, Copy, BookOpen, ListChecks, Gauge } from 'lucide-react';
import { api } from '../api/client';
import type { ChatMessage, AnalyticsSummary } from '../types';

interface Props { onNodeHighlight?: (ids: string[]) => void; }

const SUGGESTIONS = [
  "Which products are linked to the most billing documents?",
  "Which products have the highest billed revenue?",
  "Trace the full flow of billing document 90000001",
  "Find sales orders delivered but not billed",
  "Which customers have the highest total billed amount?",
  "Show all incomplete O2C flows",
  "Which plants handle the most deliveries?",
  "Which countries have the highest billed value?",
];

const THINKING_STEPS = [
  'Reading your question',
  'Finding related records',
  'Checking the graph flow',
  'Summarizing the answer',
];

let _id = 0;
const uid = () => `m${++_id}`;

export function ChatInterface({ onNodeHighlight }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: uid(), role: 'assistant', timestamp: new Date(),
    content: "Hi! I can help you analyze the **Order to Cash** process. Ask me about sales orders, deliveries, billing documents, journal entries, customers, or products.",
  }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedSql, setExpandedSql] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({});
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [insightMode, setInsightMode] = useState<'simple' | 'standard' | 'analyst'>('standard');
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [thinkingIdx, setThinkingIdx] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const autoFollowedRef = useRef<Set<string>>(new Set());
  const suppressedFollowupsRef = useRef<Set<string>>(new Set());
  const recentAssistantAnswersRef = useRef<string[]>([]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  useEffect(() => {
    if (!loading) return;
    setThinkingIdx(0);
    const t = setInterval(() => {
      setThinkingIdx(i => (i + 1) % THINKING_STEPS.length);
    }, 900);
    return () => clearInterval(t);
  }, [loading]);

  useEffect(() => {
    api.getSummary()
      .then(setSummary)
      .catch((e) => setSummaryError(e instanceof Error ? e.message : 'Failed to load summary'));
  }, []);

  const extractNodeIds = (results: Record<string, unknown>[]) => {
    const ids: string[] = [];
    for (const row of results.slice(0, 30)) {
      for (const [k, v] of Object.entries(row)) {
        if (!v) continue;
        const val = String(v);
        const key = k.toLowerCase();
        if (key.includes('billing') || key.includes('invoice')) ids.push(`INV_${val}`);
        else if (key.includes('delivery')) ids.push(`DEL_${val}`);
        else if (key.includes('salesorder') || key.includes('sales_order')) ids.push(`SO_${val}`);
        else if (key.includes('accounting')) ids.push(`JE_${val}`);
        else if (key.includes('customer') || key.includes('partner')) ids.push(`CUST_${val}`);
        else if (key.includes('plant')) ids.push(`PLANT_${val}`);
        else if (key.includes('material') || key.includes('product')) ids.push(`PROD_${val}`);
      }
    }
    return [...new Set(ids)];
  };

  const prepareQuery = (query: string) => {
    let q = query;
    if (insightMode === 'simple') {
      q = `Explain in very simple words. Use short sentences. Avoid jargon. If you must use a term, define it briefly. Question: ${query}`;
    } else if (insightMode === 'analyst') {
      q = `Answer like a business analyst. Include the key metric, a comparison or ranking, and a suggested next question. Question: ${query}`;
    }

    if (glossaryOpen) {
      const glossaryHint = "Definitions: Sales Order = customer request, Delivery = shipment, Billing Document = invoice, Journal Entry = accounting record, Payment = money received.";
      if ((q.length + glossaryHint.length + 1) <= 480) {
        q = `${q}\n${glossaryHint}`;
      }
    }
    return q;
  };

  const send = async (q?: string) => {
    const displayQuery = (q ?? input).trim();
    if (!displayQuery || loading) return;
    const preparedQuery = prepareQuery(displayQuery);
    if (onNodeHighlight) onNodeHighlight([]);
    setMessages(p => [...p, { id: uid(), role: 'user', content: displayQuery, timestamp: new Date() }]);
    setInput('');
    setLoading(true);

    const history = messages.slice(-6).map(m => ({ role: m.role, content: m.content }));
    try {
      const res = await api.sendChat(preparedQuery, history);
      const msgId = uid();
      const normalizedAnswer = res.answer.replace(/\s+/g, ' ').trim().toLowerCase();
      const recentAnswers = recentAssistantAnswersRef.current;
      const isRepeatAnswer = recentAnswers.includes(normalizedAnswer);
      const isTransformQuery = normalizedAnswer.length > 0 && (
        displayQuery.toLowerCase().startsWith('explain this in very simple words') ||
        displayQuery.toLowerCase().startsWith('give me 3 key takeaways')
      );
      if (isRepeatAnswer || isTransformQuery) {
        suppressedFollowupsRef.current.add(msgId);
      }
      recentAssistantAnswersRef.current = [normalizedAnswer, ...recentAnswers].slice(0, 3);

      setMessages(p => [...p, {
        id: msgId, role: 'assistant', content: res.answer,
        sql: res.sql, results: res.results,
        is_relevant: res.is_relevant, timestamp: new Date(),
      }]);

      if (res.results?.length && onNodeHighlight) {
        const ids = extractNodeIds(res.results);
        if (ids.length) onNodeHighlight(ids);
      }
      if (res.auto_followup) {
        const normalized = res.auto_followup.trim();
        const alreadyAsked = messages.some(m => m.role === 'user' && m.content.trim() === normalized)
          || displayQuery.trim() === normalized
          || autoFollowedRef.current.has(normalized);
        if (!alreadyAsked) {
          autoFollowedRef.current.add(normalized);
          setTimeout(() => send(normalized), 0);
        }
      }
    } catch (e) {
      setMessages(p => [...p, { id: uid(), role: 'assistant', timestamp: new Date(),
        content: `Connection error: ${e instanceof Error ? e.message : 'Unknown error'}` }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const parseStructuredAnswer = (content: string) => {
    const lines = content.split('\n').map(l => l.trim()).filter(Boolean);
    const keys = ['Answer', 'Evidence', 'Insight', 'Coverage'];
    if (lines.length < 2) return null;
    const parsed: { label: string; text: string }[] = [];
    for (const line of lines) {
      const match = line.match(/^([A-Za-z]+):\s*(.*)$/);
      if (!match) return null;
      const label = match[1];
      const text = match[2];
      if (!keys.includes(label)) return null;
      parsed.push({ label, text });
    }
    const labels = parsed.map(p => p.label);
    if (!keys.some(k => labels.includes(k))) return null;
    return parsed;
  };

  const structuredMeta = {
    Answer: { Icon: MessageCircle, border: 'border-blue-500/20', bg: 'bg-blue-500/10', text: 'text-blue-200' },
    Evidence: { Icon: BarChart3, border: 'border-emerald-500/20', bg: 'bg-emerald-500/10', text: 'text-emerald-200' },
    Insight: { Icon: Lightbulb, border: 'border-amber-500/20', bg: 'bg-amber-500/10', text: 'text-amber-200' },
    Coverage: { Icon: Layers, border: 'border-violet-500/20', bg: 'bg-violet-500/10', text: 'text-violet-200' },
  } as const;

  const isSystemError = (content: string) => {
    const c = content.toLowerCase();
    return c.startsWith('connection error') || c.startsWith('llm error');
  };

  const getStructuredSummary = (content: string) => {
    const structured = parseStructuredAnswer(content);
    if (!structured) return null;
    const byLabel = Object.fromEntries(structured.map(s => [s.label, s.text]));
    const answer = byLabel.Answer ?? '';
    const evidence = byLabel.Evidence ?? '';
    const insight = byLabel.Insight ?? '';
    return [answer, evidence, insight].filter(Boolean).join(' ');
  };

  const buildFollowupPrompt = (prefix: string, msg: ChatMessage, limit = 420) => {
    const structured = getStructuredSummary(msg.content);
    const base = structured ?? msg.content;
    const trimmed = base.length > limit ? `${base.slice(0, limit)}...` : base;
    const full = `${prefix} ${trimmed}`.trim();
    return full.length > 500 ? full.slice(0, 500) : full;
  };

  const copyStructured = async (structured: { label: string; text: string }[], id: string) => {
    const text = structured.map(s => `${s.label}: ${s.text}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopiedId(id);
    setTimeout(() => setCopiedId(current => (current === id ? null : current)), 1400);
  };

  const exportSummaryPdf = (data: AnalyticsSummary) => {
    const w = window.open('', '_blank', 'width=900,height=700');
    if (!w) return;
    const now = new Date().toLocaleString();
    const totals = Object.entries(data.totals)
      .map(([k, v]) => `<div class="card"><div class="label">${k.replace(/_/g, ' ')}</div><div class="value">${v}</div></div>`)
      .join('');

    const topProducts = data.top_products
      .map(p => `<li>${p.description || p.material} - ${p.billing_docs} docs</li>`)
      .join('');

    const topCustomers = data.top_customers
      .map(c => `<li>${c.name || c.customer} - ${c.total_billed.toFixed(2)}</li>`)
      .join('');

    const topPlants = data.top_plants
      .map(p => `<li>${p.name || p.plant} - ${p.deliveries} deliveries</li>`)
      .join('');

    const topRegions = data.top_regions
      .map(r => `<li>${r.region} ${r.country !== 'Unknown' ? `(${r.country})` : ''} - ${r.total_billed.toFixed(2)}</li>`)
      .join('');

    const broken = data.broken_flows;

    w.document.write(`
      <html>
      <head>
        <title>O2C Executive Summary</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 28px; color: #111; }
          h1 { font-size: 20px; margin: 0 0 6px; }
          h2 { font-size: 14px; margin: 18px 0 8px; text-transform: uppercase; letter-spacing: 1px; color: #555; }
          .muted { color: #777; font-size: 12px; margin-bottom: 14px; }
          .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
          .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; }
          .label { text-transform: uppercase; letter-spacing: 1px; font-size: 10px; color: #666; }
          .value { font-size: 14px; font-weight: 600; margin-top: 4px; }
          ul { margin: 6px 0 0 18px; padding: 0; }
          li { font-size: 12px; margin-bottom: 4px; }
          .section { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; margin-bottom: 10px; }
          .row { font-size: 12px; margin-bottom: 6px; }
        </style>
      </head>
      <body>
        <h1>Order to Cash Executive Summary</h1>
        <div class="muted">Generated ${now}</div>

        <h2>Totals</h2>
        <div class="grid">${totals}</div>

        <h2>Top Products</h2>
        <div class="section"><ul>${topProducts}</ul></div>

        <h2>Top Customers</h2>
        <div class="section"><ul>${topCustomers}</ul></div>

        <h2>Top Plants</h2>
        <div class="section"><ul>${topPlants}</ul></div>

        <h2>Top Regions</h2>
        <div class="section"><ul>${topRegions}</ul></div>

        <h2>Broken Flows</h2>
        <div class="section">
          <div class="row">Delivered not billed: ${broken.delivered_not_billed.count}</div>
          <div class="row">Billed no delivery: ${broken.billed_no_delivery.count}</div>
          <div class="row">Billed no journal: ${broken.billed_no_journal.count}</div>
          <div class="row">Unpaid: ${broken.unpaid.count}</div>
        </div>
      </body>
      </html>
    `);
    w.document.close();
    w.focus();
    w.print();
  };

  const renderMd = (text: string) =>
    text.split(/(\*\*[^*]+\*\*)/).map((p, i) =>
      p.startsWith('**') && p.endsWith('**')
        ? <strong key={i} className="font-semibold text-white/90">{p.slice(2,-2)}</strong>
        : <span key={i}>{p}</span>
    );

  const formatValue = (val: unknown) => {
    if (val === null || val === undefined || val === '') return 'N/A';
    return String(val);
  };

  const pickFirstValue = (rows: Record<string, unknown>[], keys: string[]) => {
    for (const row of rows) {
      for (const key of keys) {
        if (!(key in row)) continue;
        const val = row[key];
        if (val === null || val === undefined || val === '') continue;
        return String(val);
      }
    }
    return null;
  };

  const buildFollowUps = (msg: ChatMessage) => {
    if (!msg.results || msg.results.length === 0) return [];
    const rows = msg.results;
    const invoiceId = pickFirstValue(rows, [
      'billing_document', 'billingDocument', 'billingdocument', 'invoice', 'invoice_id', 'billingDocumentNumber',
    ]);
    const salesOrderId = pickFirstValue(rows, ['sales_order', 'salesOrder', 'salesorder', 'salesOrderNumber']);
    const deliveryId = pickFirstValue(rows, ['delivery', 'delivery_id', 'deliveryDocument', 'deliveryDocumentNumber']);
    const customerId = pickFirstValue(rows, ['customer', 'customer_id', 'sold_to_party', 'ship_to_party', 'partner']);
    const productId = pickFirstValue(rows, ['material', 'product', 'material_id', 'product_id']);

    const suggestions: string[] = [];
    if (invoiceId) suggestions.push(`Trace the full flow of billing document ${invoiceId}`);
    if (salesOrderId) suggestions.push(`Show deliveries for sales order ${salesOrderId}`);
    if (deliveryId) suggestions.push(`Find the billing document for delivery ${deliveryId}`);
    if (customerId) suggestions.push(`Show top billed products for customer ${customerId}`);
    if (productId) suggestions.push(`Show billing documents for product ${productId}`);

    const seen = new Set<string>();
    const unique: string[] = [];
    for (const s of suggestions) {
      const key = normalizeQuery(s);
      if (seen.has(key)) continue;
      seen.add(key);
      unique.push(s);
    }
    return unique.slice(0, 3);
  };

  const normalizeQuery = (q: string) => q.trim().toLowerCase();

  const filterFollowUps = (items: string[]) => {
    const recentUserQueries = messages
      .filter(m => m.role === 'user')
      .slice(-6)
      .map(m => normalizeQuery(m.content));
    const recentSuggestions = messages
      .filter(m => m.role === 'assistant')
      .slice(-3)
      .flatMap(m => buildFollowUps(m))
      .map(normalizeQuery);

    const seen = new Set<string>();
    const filtered = items.filter(s => {
      const key = normalizeQuery(s);
      if (seen.has(key)) return false;
      if (recentUserQueries.includes(key)) return false;
      if (recentSuggestions.includes(key)) return false;
      seen.add(key);
      return true;
    });
    if (filtered.length > 0) return filtered;
    // Fallback: keep at least one relevant suggestion for clarity
    const fallback = items.filter(s => !recentUserQueries.includes(normalizeQuery(s)));
    return fallback.length > 0 ? fallback.slice(0, 1) : items.slice(0, 1);
  };

  return (
    <div className="flex flex-col h-full" style={{ fontFamily: "'Inter', sans-serif" }}>

      {/* Header */}
      <div className="px-5 py-4 border-b border-white/[0.06]">
        <div className="flex items-center gap-2 mb-0.5">
          <Sparkles size={13} className="text-blue-400" />
          <p className="text-[11px] font-semibold text-white/30 tracking-widest uppercase">Chat with Graph</p>
        </div>
        <p className="text-sm font-medium text-white/70">Order to Cash</p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-widest text-white/25 font-semibold">Insight mode</span>
          {(['simple', 'standard', 'analyst'] as const).map(mode => (
            <button
              key={mode}
              onClick={() => setInsightMode(mode)}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${
                insightMode === mode
                  ? 'border-blue-500/40 text-white/80 bg-blue-500/10'
                  : 'border-white/[0.08] text-white/40 hover:text-white/70 hover:border-white/[0.18]'
              }`}
            >
              <span className="inline-flex items-center gap-1">
                <Gauge size={10} className={insightMode === mode ? 'text-blue-300' : 'text-white/30'} />
                {mode}
              </span>
            </button>
          ))}
          <button
            onClick={() => setGlossaryOpen(v => !v)}
            className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors inline-flex items-center gap-1"
          >
            <BookOpen size={10} />
            {glossaryOpen ? 'Hide glossary' : 'Glossary'}
          </button>
          {glossaryOpen && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30 text-emerald-300/80 bg-emerald-500/10">
              Glossary active
            </span>
          )}
        </div>

        {glossaryOpen && (
          <div className="mt-3 grid grid-cols-1 gap-2">
            {[
              { term: 'Sales Order', def: 'A customer request to buy specific products and quantities.' },
              { term: 'Delivery', def: 'Shipment of goods from a plant to the customer.' },
              { term: 'Billing Document', def: 'The invoice that charges the customer for delivered goods.' },
              { term: 'Journal Entry', def: 'Accounting record that posts the invoice in the ledger.' },
              { term: 'Payment', def: 'Money received to settle an invoice.' },
            ].map(row => (
              <div key={row.term} className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                <div className="text-[10px] uppercase tracking-widest text-white/30">{row.term}</div>
                <div className="text-xs text-white/60 mt-1">{row.def}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {/* Executive Summary */}
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.04] p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-semibold">Executive Summary</p>
              <p className="text-sm text-white/70">Snapshot of the O2C dataset</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => summary && exportSummaryPdf(summary)}
                disabled={!summary}
                className="text-[11px] text-white/40 hover:text-white/70 border border-white/[0.08] px-2.5 py-1 rounded-full disabled:opacity-40"
              >
                Export PDF
              </button>
              <button
                onClick={() => setSummaryOpen(v => !v)}
                className="text-[11px] text-white/40 hover:text-white/70 border border-white/[0.08] px-2.5 py-1 rounded-full"
              >
                {summaryOpen ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {summaryError && (
            <div className="text-xs text-amber-300/80">
              Summary unavailable: {summaryError}
            </div>
          )}

          {summary && summaryOpen && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(summary.totals).map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                    <div className="text-[10px] uppercase tracking-widest text-white/30">{k.replace(/_/g, ' ')}</div>
                    <div className="text-sm text-white/80 font-semibold">{v}</div>
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-1 gap-2">
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Products</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_products.map(p => (
                      <div key={p.material} className="flex justify-between gap-2">
                        <span className="text-white/80">{p.description || p.material}</span>
                        <span className="text-white/40">{p.billing_docs} docs</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Products by Revenue</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_products_revenue.map(p => (
                      <div key={p.material} className="flex justify-between gap-2">
                        <span className="text-white/80">{p.description || p.material}</span>
                        <span className="text-white/40">{p.revenue.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Customers</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_customers.map(c => (
                      <div key={c.customer} className="flex justify-between gap-2">
                        <span className="text-white/80">{c.name || c.customer}</span>
                        <span className="text-white/40">{c.total_billed.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Plants</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_plants.map(p => (
                      <div key={p.plant} className="flex justify-between gap-2">
                        <span className="text-white/80">{p.name || p.plant}</span>
                        <span className="text-white/40">{p.deliveries} deliveries</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Regions</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_regions.map(r => (
                      <div key={`${r.region}-${r.country}`} className="flex justify-between gap-2">
                        <span className="text-white/80">{r.region} {r.country !== 'Unknown' ? `(${r.country})` : ''}</span>
                        <span className="text-white/40">{r.total_billed.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Top Countries</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    {summary.top_countries.map(c => (
                      <div key={c.country} className="flex justify-between gap-2">
                        <span className="text-white/80">{c.country}</span>
                        <span className="text-white/40">{c.total_billed.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <div className="text-[10px] uppercase tracking-widest text-white/30">Broken Flows</div>
                  <div className="text-xs text-white/70 mt-1 space-y-1">
                    <div>Delivered not billed: {summary.broken_flows.delivered_not_billed.count}</div>
                    <div>Billed no delivery: {summary.broken_flows.billed_no_delivery.count}</div>
                    <div>Billed no journal: {summary.broken_flows.billed_no_journal.count}</div>
                    <div>Unpaid: {summary.broken_flows.unpaid.count}</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        {messages.map(msg => (
          <div key={msg.id}>
            {msg.role === 'user' ? (
              <div className="flex justify-end">
                <div className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed text-white/90"
                  style={{ background: 'linear-gradient(135deg, #2563EB, #4F46E5)' }}>
                  {msg.content}
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0 mt-0.5 shadow-lg shadow-blue-500/20">
                  <span className="text-white text-[10px] font-bold">D</span>
                </div>
                <div className="flex-1 min-w-0">
                {(() => {
                  const followups = (msg.is_relevant === false || isSystemError(msg.content) || suppressedFollowupsRef.current.has(msg.id))
                    ? []
                    : filterFollowUps(buildFollowUps(msg));
                  const results = msg.results ?? [];
                  return (
                    <>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[11px] font-semibold text-white/50">Dodge AI</span>
                    <span className="text-[10px] text-white/20">Graph Agent</span>
                    <span
                      className={`text-[9px] px-2 py-0.5 rounded-full border ${
                        msg.results && msg.results.length > 0
                          ? 'border-emerald-500/30 text-emerald-300/80 bg-emerald-500/10'
                          : 'border-white/[0.08] text-white/30 bg-white/[0.04]'
                      }`}
                    >
                      {msg.results && msg.results.length > 0 ? 'Data-backed' : 'No data'}
                    </span>
                    {(() => {
                      const structured = parseStructuredAnswer(msg.content);
                      if (!structured) return null;
                      const labels = structured.map(s => s.label);
                      return (
                        <div className="flex items-center gap-2 ml-1">
                          <div className="flex items-center gap-1.5">
                            {labels.map(label => {
                              const meta = structuredMeta[label as keyof typeof structuredMeta];
                              const Icon = meta?.Icon;
                              return (
                                <span
                                  key={label}
                                  className={`text-[9px] px-2 py-0.5 rounded-full border ${meta?.border ?? 'border-white/[0.08]'} ${meta?.bg ?? 'bg-white/[0.04]'} ${meta?.text ?? 'text-white/40'}`}
                                >
                                  <span className="inline-flex items-center gap-1">
                                    {Icon ? <Icon size={10} className={meta.text} /> : null}
                                    {label}
                                  </span>
                                </span>
                              );
                            })}
                          </div>
                          <button
                            onClick={() => copyStructured(structured, msg.id)}
                            className="text-[9px] px-2 py-0.5 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors inline-flex items-center gap-1"
                          >
                            <Copy size={10} />
                            {copiedId === msg.id ? 'Copied' : 'Copy report'}
                          </button>
                        </div>
                      );
                    })()}
                  </div>

                  {msg.is_relevant === false && (
                    <div className="flex items-center gap-2 text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 mb-2 text-xs">
                      <AlertTriangle size={12} />
                      Off-topic query
                    </div>
                  )}

                  <div className="text-sm text-white/60 leading-relaxed">
                    {(() => {
                      const structured = parseStructuredAnswer(msg.content);
                      if (!structured) return renderMd(msg.content);
                      return (
                        <div className="space-y-2">
                          {structured.map(row => (
                            <div
                              key={row.label}
                              className={`rounded-xl border px-3 py-2 ${structuredMeta[row.label as keyof typeof structuredMeta]?.border ?? 'border-white/[0.08]'} ${structuredMeta[row.label as keyof typeof structuredMeta]?.bg ?? 'bg-white/[0.04]'}`}
                            >
                              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-white/30 font-semibold">
                                {(() => {
                                  const meta = structuredMeta[row.label as keyof typeof structuredMeta];
                                  if (!meta) return null;
                                  const Icon = meta.Icon;
                                  return <Icon size={12} className={meta.text} />;
                                })()}
                                <span className={structuredMeta[row.label as keyof typeof structuredMeta]?.text ?? 'text-white/30'}>
                                  {row.label}
                                </span>
                              </div>
                              <div className="text-sm text-white/70 mt-0.5">
                                {row.text || 'N/A'}
                              </div>
                            </div>
                          ))}
                        </div>
                      );
                    })()}
                  </div>

                  {/* Actions */}
                  {!isSystemError(msg.content) && msg.is_relevant !== false && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        onClick={() => send(buildFollowupPrompt('Explain this in very simple words for a non-technical user:', msg))}
                        className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors"
                      >
                        Explain simply
                      </button>
                      <button
                        onClick={() => send(buildFollowupPrompt('Give me 3 key takeaways and 1 risk in simple words:', msg))}
                        className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors inline-flex items-center gap-1"
                      >
                        <ListChecks size={11} />
                        Key takeaways
                      </button>
                      {msg.results && msg.results.length > 0 && (
                        <>
                          <button
                            onClick={() => setExpandedEvidence(p => ({ ...p, [msg.id]: !p[msg.id] }))}
                            className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors"
                          >
                            {expandedEvidence[msg.id] ? 'Hide evidence' : 'Show evidence'}
                          </button>
                          <button
                            onClick={() => onNodeHighlight?.(extractNodeIds(msg.results || []))}
                            className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors"
                          >
                            Highlight nodes
                          </button>
                        </>
                      )}
                    </div>
                  )}

                  {/* Evidence table */}
                  {results.length > 0 && expandedEvidence[msg.id] && (
                    <div className="mt-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-2 overflow-x-auto">
                      <table className="min-w-full text-[11px] text-white/70">
                        <thead>
                          <tr className="text-white/40">
                            {Object.keys(results[0]).map((k) => (
                              <th key={k} className="text-left px-2 py-1 font-semibold">
                                {k}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {results.slice(0, 5).map((row, idx) => (
                            <tr key={idx} className="border-t border-white/[0.05]">
                              {Object.keys(results[0]).map((k) => (
                                <td key={k} className="px-2 py-1">
                                  {formatValue((row as Record<string, unknown>)[k])}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {results.length > 5 && (
                        <div className="text-[10px] text-white/30 px-2 pt-1">
                          Showing 5 of {results.length} rows.
                        </div>
                      )}
                    </div>
                  )}

                  {/* SQL reveal */}
                  {msg.sql && (
                    <div className="mt-3">
                      <button
                        onClick={() => setExpandedSql(p => ({ ...p, [msg.id]: !p[msg.id] }))}
                        className="flex items-center gap-1.5 text-[11px] text-white/25 hover:text-white/50 transition-colors"
                      >
                        <Code2 size={11} />
                        <Database size={10} />
                        View generated SQL
                        {expandedSql[msg.id] ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                      </button>
                      {expandedSql[msg.id] && (
                        <div className="mt-2 rounded-xl overflow-hidden border border-white/[0.08]">
                          <div className="flex items-center gap-2 px-3 py-1.5 bg-white/[0.03] border-b border-white/[0.06]">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400/60" />
                            <span className="text-[10px] text-white/30 font-mono">SQLite</span>
                          </div>
                          <pre className="text-[11px] text-emerald-300/80 p-3 overflow-x-auto leading-relaxed font-mono"
                            style={{ background: 'rgba(0,0,0,0.4)' }}>
                            {msg.sql}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {msg.results && msg.results.length > 0 && (
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <div className="w-1 h-1 rounded-full bg-emerald-400/60" />
                      <span className="text-[11px] text-white/25">
                        {msg.results.length} row{msg.results.length !== 1 ? 's' : ''} returned
                      </span>
                    </div>
                  )}

                  {/* Follow-up suggestions */}
                  {followups.length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] uppercase tracking-widest text-white/25 mb-1">Suggested follow ups</div>
                      <div className="flex flex-wrap gap-2">
                        {followups.map(s => (
                          <button
                            key={s}
                            onClick={() => send(s)}
                            className="text-[11px] px-2.5 py-1 rounded-full border border-white/[0.08] bg-white/[0.04] text-white/40 hover:text-white/70 hover:border-white/[0.18] transition-colors"
                          >
                            {s}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              );
            })()}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shrink-0 shadow-lg shadow-blue-500/20">
              <span className="text-white text-[10px] font-bold">D</span>
            </div>
            <div className="flex flex-col gap-1 pt-1">
              <div className="flex items-center gap-1">
                {[0,1,2].map(i => (
                  <div key={i} className="w-1.5 h-1.5 rounded-full bg-blue-400/60 animate-bounce"
                    style={{ animationDelay: `${i * 120}ms` }} />
                ))}
              </div>
              <div className="text-[11px] text-white/40">
                {THINKING_STEPS[thinkingIdx]}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="px-4 pb-3">
          <p className="text-[10px] font-semibold text-white/20 uppercase tracking-widest mb-2">Try asking</p>
          <div className="flex flex-col gap-1.5">
            {SUGGESTIONS.slice(0, 4).map(q => (
              <button key={q} onClick={() => send(q)}
                className="text-left text-xs text-white/40 hover:text-white/70 px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-white/[0.07] border border-white/[0.06] hover:border-white/[0.12] transition-all leading-snug">
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Status */}
      <div className="px-4 pb-2">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full transition-colors ${loading ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`} />
          <span className="text-[11px] text-white/25">{loading ? 'Analyzing data...' : 'Dodge AI is awaiting instructions'}</span>
        </div>
      </div>

      {/* Input */}
      <div className="px-4 pb-4">
        <div className="flex items-end gap-2.5 rounded-2xl border border-white/[0.1] px-4 py-3 focus-within:border-blue-500/40 transition-all"
          style={{ background: 'rgba(255,255,255,0.04)' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Analyze anything..."
            rows={1}
            className="flex-1 resize-none text-sm text-white/80 placeholder-white/20 outline-none bg-transparent leading-relaxed"
            style={{ maxHeight: '100px', overflowY: 'auto' }}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="p-2 rounded-xl transition-all shrink-0 disabled:opacity-30"
            style={{ background: input.trim() && !loading ? 'linear-gradient(135deg, #2563EB, #4F46E5)' : 'rgba(255,255,255,0.1)' }}
          >
            <Send size={13} className="text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
