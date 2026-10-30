"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import type { GraphEdge, GraphNode } from "@/lib/graph/types";
import { outcomeLabel } from "@/lib/graph/buildGraph";
import { IDENTITY, layoutGraph, neighbours, panBy, zoomAt, type Point, type ViewTransform } from "@/lib/graph/view";
import { EDGE_STYLE, KIND_LABEL, nodeColor } from "./graphStyle";

interface ExposureGraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const WHEEL_STEP = 1.15;
const BUTTON_STEP = 1.3;
const DRAG_THRESHOLD = 4;

function nodeAriaLabel(node: GraphNode): string {
  const outcome = node.outcome ? `, ${outcomeLabel(node.outcome)}` : "";
  return `${KIND_LABEL[node.kind]} ${node.label}${outcome}${node.synthetic ? ", synthetic" : ""}`;
}

function NodeShape({ node, color }: { node: GraphNode; color: string }) {
  switch (node.kind) {
    case "account":
      return <circle r={11} fill={color} fillOpacity={0.25} stroke={color} strokeWidth={2} />;
    case "market":
      return <rect x={-16} y={-16} width={32} height={32} fill={color} fillOpacity={0.2} stroke={color} strokeWidth={2.5} />;
    case "collateralAsset":
    case "debtAsset":
      return <rect x={-12} y={-12} width={24} height={24} transform="rotate(45)" fill={color} fillOpacity={0.15} stroke={color} strokeWidth={2} />;
    case "evidence":
      return <path d="M-12 -15 H6 L12 -9 V15 H-12 Z" fill={color} fillOpacity={0.15} stroke={color} strokeWidth={2} />;
    case "claim":
      return <polygon points="0,-14 12,-7 12,7 0,14 -12,7 -12,-7" fill={color} fillOpacity={0.15} stroke={color} strokeWidth={2} />;
  }
}

function labelOffset(node: GraphNode): { x: number; y: number; anchor: "start" | "middle" } {
  return node.kind === "account" ? { x: 18, y: 4, anchor: "start" } : { x: 0, y: 32, anchor: "middle" };
}

function useWheelZoom(ref: React.RefObject<SVGSVGElement>, toView: (x: number, y: number) => Point, setT: (f: (t: ViewTransform) => ViewTransform) => void) {
  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); // keep the page from scrolling while zooming the graph
      const p = toView(e.clientX, e.clientY);
      setT((t) => zoomAt(t, e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP, p.x, p.y));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [ref, toView, setT]);
}

export function ExposureGraphCanvas({ nodes, edges, selectedId, onSelect }: ExposureGraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [t, setT] = useState<ViewTransform>(IDENTITY);
  const layout = useMemo(() => layoutGraph(nodes), [nodes]);
  const focus = useMemo(() => neighbours(edges, selectedId), [edges, selectedId]);

  // Screen pixels -> viewBox units, so zoom and pan track the pointer at any rendered size.
  const toView = useCallback((clientX: number, clientY: number): Point => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }, []);
  useWheelZoom(svgRef, toView, setT);

  const onPointerDown = (e: PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    drag.current = { ...toView(e.clientX, e.clientY), moved: false };
  };
  const onPointerMove = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    const p = toView(e.clientX, e.clientY);
    if (!d.moved && Math.hypot(p.x - d.x, p.y - d.y) < DRAG_THRESHOLD) return;
    if (!d.moved) svgRef.current?.setPointerCapture(e.pointerId);
    drag.current = { x: p.x, y: p.y, moved: true };
    setT((cur) => panBy(cur, p.x - d.x, p.y - d.y));
  };
  const onPointerUp = (e: PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    drag.current = null;
    if (d?.moved) svgRef.current?.releasePointerCapture(e.pointerId);
    else if (e.target === svgRef.current) onSelect(null); // a click on empty space clears the selection
  };

  const zoomButton = (factor: number) => setT((cur) => zoomAt(cur, factor, layout.width / 2, layout.height / 2));
  const onNodeKey = (e: KeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id === selectedId ? null : id);
    }
  };

  const dim = (id: string) => selectedId !== null && !focus.has(id);

  return (
    <div className="relative w-full min-h-[360px] max-h-[680px] border-2 border-border bg-background overflow-hidden"
      style={{ aspectRatio: `${layout.width} / ${layout.height}` }}>
      <div className="absolute right-2 top-2 z-10 flex flex-col gap-1">
        {[
          { label: "Zoom in", icon: Plus, run: () => zoomButton(BUTTON_STEP) },
          { label: "Zoom out", icon: Minus, run: () => zoomButton(1 / BUTTON_STEP) },
          { label: "Reset view", icon: Maximize2, run: () => setT(IDENTITY) },
        ].map(({ label, icon: Icon, run }) => (
          <button key={label} type="button" onClick={run} aria-label={label} title={label}
            className="h-8 w-8 border border-border bg-card text-foreground flex items-center justify-center hover:border-[#ea580c] hover:text-[#ea580c]">
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>
      <p className="absolute left-2 bottom-2 z-10 text-[10px] uppercase text-muted-foreground pointer-events-none">
        Scroll or +/− to zoom · drag to pan · select a node for details · {Math.round(t.k * 100)}%
      </p>
      <svg ref={svgRef} role="group" aria-label="Exposure graph" viewBox={`0 0 ${layout.width} ${layout.height}`}
        preserveAspectRatio="xMidYMid meet" className="h-full w-full touch-none select-none cursor-grab active:cursor-grabbing"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={() => (drag.current = null)}>
        <g transform={`translate(${t.x} ${t.y}) scale(${t.k})`}>
          {edges.map((e) => {
            const a = layout.positions[e.source];
            const b = layout.positions[e.target];
            if (!a || !b) return null;
            const style = EDGE_STYLE[e.kind];
            const active = selectedId !== null && (e.source === selectedId || e.target === selectedId);
            return (
              <g key={e.id} opacity={selectedId === null ? 0.55 : active ? 1 : 0.12} pointerEvents="none">
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={style.color} strokeWidth={active ? 2 : 1.25} strokeDasharray={style.dash} />
                {active && (
                  <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 6} textAnchor="middle" className="fill-foreground" fontSize={11}>
                    {e.label}
                  </text>
                )}
              </g>
            );
          })}
          {nodes.map((n) => {
            const p = layout.positions[n.id];
            if (!p) return null;
            const color = nodeColor(n);
            const off = labelOffset(n);
            const selected = n.id === selectedId;
            return (
              <g key={n.id} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={0} aria-label={nodeAriaLabel(n)}
                aria-pressed={selected} opacity={dim(n.id) ? 0.25 : 1} className="cursor-pointer outline-none focus-visible:[&>circle:first-child]:stroke-foreground"
                onPointerDown={(e) => e.stopPropagation()} onPointerUp={(e) => e.stopPropagation()}
                onClick={() => onSelect(selected ? null : n.id)} onKeyDown={(e) => onNodeKey(e, n.id)}>
                <circle r={22} fill="transparent" stroke={selected ? "#ffffff" : "transparent"} strokeWidth={1.5} strokeDasharray="3 3" />
                <NodeShape node={n} color={color} />
                <text x={off.x} y={off.y} textAnchor={off.anchor} fontSize={12} className="fill-foreground font-mono">
                  {n.label.length > 28 ? `${n.label.slice(0, 27)}…` : n.label}
                </text>
                {n.synthetic && n.kind === "account" && (
                  <text x={off.x} y={off.y + 13} fontSize={9} className="fill-amber-400 font-mono">SYNTHETIC</text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
