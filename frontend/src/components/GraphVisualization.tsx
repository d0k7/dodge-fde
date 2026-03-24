import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { GraphData, GraphNode } from '../types';
// @ts-ignore
import ForceGraph2D from 'react-force-graph-2d';

interface Props {
  data: GraphData;
  highlightedNodes?: Set<string>;
  onNodeClick: (node: GraphNode) => void;
  isLoading: boolean;
}

const COLORS: Record<string, string> = {
  SalesOrder:    '#3B82F6',
  Delivery:      '#10B981',
  Invoice:       '#F59E0B',
  JournalEntry:  '#8B5CF6',
  Customer:      '#EF4444',
  Product:       '#06B6D4',
  Plant:         '#84CC16',
  Payment:       '#F97316',
  Unknown:       '#6B7280',
};

const GLOW: Record<string, string> = {
  SalesOrder:    '#3B82F640',
  Delivery:      '#10B98140',
  Invoice:       '#F59E0B40',
  JournalEntry:  '#8B5CF640',
  Customer:      '#EF444440',
  Product:       '#06B6D440',
  Plant:         '#84CC1640',
  Payment:       '#F9731640',
  Unknown:       '#6B728040',
};

const TYPE_ORDER = ['Customer','SalesOrder','Delivery','Invoice','JournalEntry','Product','Payment','Plant'];
const BLINK = ['#FF2D2D', '#1BFF6B'];

export function GraphVisualization({ data, highlightedNodes, onNodeClick, isLoading }: Props) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 900, height: 600 });
  const [showLegend, setShowLegend] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [blinkVisible, setBlinkVisible] = useState(false);
  const [blinkColor, setBlinkColor] = useState<0 | 1>(0);
  const nodeIdSet = useMemo(() => new Set(data.nodes.map(n => n.id)), [data.nodes]);

  // Build degree map for node sizing
  const degreeMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const link of data.links) {
      const s = typeof link.source === 'string' ? link.source : (link.source as any).id;
      const t = typeof link.target === 'string' ? link.target : (link.target as any).id;
      map[s] = (map[s] || 0) + 1;
      map[t] = (map[t] || 0) + 1;
    }
    return map;
  }, [data.links]);

  const maxDegree = useMemo(() => Math.max(...Object.values(degreeMap), 1), [degreeMap]);

  useEffect(() => {
    const obs = new ResizeObserver(e => {
      const { width, height } = e[0].contentRect;
      setDims({ width: Math.max(width, 300), height: Math.max(height, 300) });
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!fgRef.current || !data.nodes.length) return;
    const t = setTimeout(() => { try { fgRef.current?.zoomToFit(500, 80); } catch (_) {} }, 700);
    return () => clearTimeout(t);
  }, [data.nodes.length]);

  const highlightKey = useMemo(
    () => highlightedNodes ? Array.from(highlightedNodes).sort().join('|') : '',
    [highlightedNodes]
  );

  useEffect(() => {
    if (!highlightedNodes || highlightedNodes.size === 0) {
      setBlinkVisible(false);
      setBlinkColor(0);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const pattern = [
      { visible: true,  color: 0 as const, duration: 120 },
      { visible: false, color: 0 as const, duration: 120 },
      { visible: true,  color: 1 as const, duration: 120 },
      { visible: false, color: 1 as const, duration: 900 },
    ];
    let idx = 0;
    const tick = () => {
      const step = pattern[idx];
      setBlinkVisible(step.visible);
      setBlinkColor(step.color);
      try { fgRef.current?.refresh(); } catch (_) {}
      idx = (idx + 1) % pattern.length;
      if (!cancelled) timer = setTimeout(tick, step.duration);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [highlightKey, highlightedNodes]);

  useEffect(() => {
    if (!fgRef.current || !highlightedNodes || highlightedNodes.size === 0) return;
    let raf = 0;
    const loop = () => {
      try { fgRef.current?.refresh(); } catch (_) {}
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [highlightKey, highlightedNodes]);

  useEffect(() => {
    if (!fgRef.current) return;
    if (highlightedNodes && highlightedNodes.size > 0) {
      const matchCount = Array.from(highlightedNodes).filter(id => nodeIdSet.has(id)).length;
      if (matchCount === 0) return;
      try {
        fgRef.current.zoomToFit(700, 140, (n: any) => highlightedNodes.has(n.id));
      } catch (_) {}
      return;
    }
    if (data.nodes.length > 0) {
      try { fgRef.current.zoomToFit(700, 80); } catch (_) {}
    }
  }, [highlightKey, highlightedNodes, data.nodes.length, nodeIdSet]);

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    // Guard: force-graph assigns x/y async; skip until positions are finite
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
    const isHL = highlightedNodes?.has(node.id);
    const isHov = hoveredNode === node.id;
    const deg = degreeMap[node.id] || 1;
    const baseR = 3.5 + (deg / maxDegree) * 8; // 3.5 to 11.5 based on connectivity
    const r = isHL ? baseR * 1.7 : isHov ? baseR * 1.2 : baseR;
    const baseColor = COLORS[node.type] ?? COLORS.Unknown;
    const baseGlow  = GLOW[node.type]  ?? GLOW.Unknown;
    const blinked = BLINK[blinkColor];
    const color = isHL ? (blinkVisible ? blinked : baseColor) : baseColor;
    const glow = isHL ? (blinkVisible ? blinked + '40' : baseGlow) : baseGlow;

    // Outer glow ring (highlight/hover)
    if (isHL || isHov) {
      const glowR = r + (isHL ? 14 : 4);
      const grad = ctx.createRadialGradient(node.x, node.y, r, node.x, node.y, glowR);
      grad.addColorStop(0, isHL ? color + 'B0' : color + '30');
      grad.addColorStop(1, color + '00');
      ctx.beginPath();
      ctx.arc(node.x, node.y, glowR, 0, 2 * Math.PI);
      ctx.fillStyle = grad;
      ctx.fill();
    }

    // Ambient glow for all nodes
    if (globalScale < 3) {
      const aGlow = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, r * 2.5);
      aGlow.addColorStop(0, glow);
      aGlow.addColorStop(1, color + '00');
      ctx.beginPath();
      ctx.arc(node.x, node.y, r * 2.5, 0, 2 * Math.PI);
      ctx.fillStyle = aGlow;
      ctx.fill();
    }

    // Core circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = isHL ? color : color + 'CC';
    ctx.fill();

    // White inner highlight
    ctx.beginPath();
    ctx.arc(node.x - r * 0.25, node.y - r * 0.25, r * 0.35, 0, 2 * Math.PI);
    ctx.fillStyle = 'rgba(255,255,255,0.25)';
    ctx.fill();

    // Crisp border
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.strokeStyle = isHL ? color : isHov ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.15)';
    ctx.lineWidth = (isHL ? 2.4 : 0.8) / globalScale;
    ctx.stroke();

    // Label
    if (globalScale > 2 || isHL) {
      const raw = String(node.label ?? node.id);
      const label = raw.length > 20 ? raw.slice(0, 18) + '...' : raw;
      const fs = Math.max(3.5, 6 / globalScale);
      ctx.font = `${isHL ? 600 : 400} ${fs}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      // text shadow trick
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.fillText(label, node.x + 0.5, node.y + r + 1.5);
      ctx.fillStyle = isHL ? '#FFFFFF' : 'rgba(255,255,255,0.7)';
      ctx.fillText(label, node.x, node.y + r + 1);
    }
  }, [highlightedNodes, hoveredNode, degreeMap, maxDegree, blinkVisible, blinkColor]);

  const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D) => {
    const src = link.source;
    const tgt = link.target;
    if (!Number.isFinite(src?.x) || !Number.isFinite(src?.y) || !Number.isFinite(tgt?.x) || !Number.isFinite(tgt?.y)) return;
    const isHL = highlightedNodes?.has(src.id) && highlightedNodes?.has(tgt.id);

    if (isHL) {
      const blinkStroke = blinkVisible ? BLINK[blinkColor] : '#3B82F6';
      // Glowing highlighted link
      ctx.beginPath();
      ctx.setLineDash([6, 5]);
      ctx.lineDashOffset = -((Date.now() / 40) % 11);
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = blinkStroke;
      ctx.lineWidth = 2.6;
      ctx.globalAlpha = 0.9;
      ctx.stroke();

      // Glow overlay
      ctx.beginPath();
      ctx.setLineDash([10, 8]);
      ctx.lineDashOffset = -((Date.now() / 40) % 18);
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = blinkStroke;
      ctx.lineWidth = 8;
      ctx.globalAlpha = 0.18;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.lineDashOffset = 0;
    } else {
      ctx.beginPath();
      ctx.setLineDash([]);
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.lineWidth = 0.7;
      ctx.globalAlpha = 1;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }, [highlightedNodes, blinkVisible, blinkColor]);

  const typeCounts = useMemo(() =>
    data.nodes.reduce<Record<string, number>>((acc, n) => {
      acc[n.type] = (acc[n.type] || 0) + 1;
      return acc;
    }, {}),
    [data.nodes]
  );

  return (
    <div ref={containerRef} className="relative w-full h-full overflow-hidden" style={{ background: 'radial-gradient(ellipse at 50% 50%, #0F1117 0%, #090A0D 100%)' }}>
      
      {/* Subtle grid overlay */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.5) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

      {isLoading ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="relative w-12 h-12 mx-auto mb-4">
              <div className="absolute inset-0 rounded-full border-2 border-blue-500/20" />
              <div className="absolute inset-0 rounded-full border-2 border-t-blue-500 animate-spin" />
              <div className="absolute inset-2 rounded-full border border-t-indigo-400 animate-spin" style={{ animationDuration: '0.7s', animationDirection: 'reverse' }} />
            </div>
            <p className="text-sm text-white/40 font-medium">Building knowledge graph</p>
            <p className="text-xs text-white/20 mt-1">Processing dataset</p>
          </div>
        </div>
      ) : data.nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-sm text-white/30">No graph data</p>
        </div>
      ) : (
        <ForceGraph2D
          ref={fgRef}
          width={dims.width}
          height={dims.height}
          graphData={data}
          nodeId="id"
          linkSource="source"
          linkTarget="target"
          onNodeClick={(n: any) => { try { onNodeClick(n); fgRef.current?.centerAt(n.x, n.y, 500); fgRef.current?.zoom(3.5, 500); } catch(_){} }}
          onNodeHover={(n: any) => {
            setHoveredNode(n?.id ?? null);
            if (containerRef.current) containerRef.current.style.cursor = n ? 'pointer' : 'default';
          }}
          nodeCanvasObject={nodeCanvasObject}
          linkCanvasObject={linkCanvasObject}
          nodeCanvasObjectMode={() => 'replace'}
          linkCanvasObjectMode={() => 'replace'}
          backgroundColor="transparent"
          cooldownTicks={100}
          d3AlphaDecay={0.015}
          d3VelocityDecay={0.25}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.85}
          linkDirectionalArrowColor={(l: any) => {
            const isHL = highlightedNodes?.has(l.source?.id) && highlightedNodes?.has(l.target?.id);
            return isHL ? '#93C5FD' : 'rgba(255,255,255,0.12)';
          }}
          onEngineStop={() => { try { fgRef.current?.zoomToFit(500, 80); } catch(_){} }}
        />
      )}

      {/* Toolbar */}
      {!isLoading && data.nodes.length > 0 && (
        <div className="absolute top-4 left-4 flex items-center gap-2">
          <button
            onClick={() => { try { fgRef.current?.zoomToFit(400, 60); } catch(_){} }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white/60 hover:text-white/90 bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] backdrop-blur-sm transition-all"
          >
            ⊡ Fit View
          </button>
          <button
            onClick={() => setShowLegend(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white/60 hover:text-white/90 bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.08] backdrop-blur-sm transition-all"
          >
            ◈ {showLegend ? 'Hide' : 'Show'} Legend
          </button>
        </div>
      )}

      {/* Legend */}
      {showLegend && !isLoading && (
        <div className="absolute bottom-4 left-4 rounded-2xl border border-white/[0.08] overflow-hidden backdrop-blur-xl"
          style={{ background: 'rgba(13,14,20,0.85)' }}>
          <div className="px-4 pt-3 pb-1">
            <p className="text-[10px] font-semibold text-white/30 tracking-widest uppercase mb-2.5">Node Types</p>
            <div className="space-y-1.5">
              {TYPE_ORDER.filter(t => typeCounts[t]).map(type => (
                <div key={type} className="flex items-center justify-between gap-8">
                  <div className="flex items-center gap-2.5">
                    <div className="relative w-2.5 h-2.5">
                      <div className="absolute inset-0 rounded-full opacity-40 blur-[3px]" style={{ backgroundColor: COLORS[type] }} />
                      <div className="absolute inset-0 rounded-full" style={{ backgroundColor: COLORS[type] }} />
                    </div>
                    <span className="text-xs text-white/60 font-medium">{type}</span>
                  </div>
                  <span className="text-xs text-white/30 font-mono tabular-nums">{typeCounts[type]}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="px-4 py-2.5 mt-1 border-t border-white/[0.06]">
            <p className="text-[10px] text-white/25">Node size = connectivity degree</p>
          </div>
        </div>
      )}

      {/* Stats badge */}
      {!isLoading && (
        <div className="absolute top-4 right-4 flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-white/[0.08] backdrop-blur-xl"
          style={{ background: 'rgba(13,14,20,0.7)' }}>
          <span className="text-xs text-white/40">
            <strong className="text-white/80 font-semibold">{data.nodes.length}</strong> nodes
            <span className="mx-1.5 text-white/20">·</span>
            <strong className="text-white/80 font-semibold">{data.links.length}</strong> edges
          </span>
        </div>
      )}
    </div>
  );
}
