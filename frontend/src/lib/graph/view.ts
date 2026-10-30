import type { AccountOutcome, ExposureGraph, GraphEdge, GraphNode } from "./types";

/** View helpers: filtering, deterministic layout and zoom/pan. Pure functions; no DOM access. */

export type OutcomeFilter = "all" | AccountOutcome;

export interface GraphFilter {
  outcome: OutcomeFilter;
  query: string;
}

export const MAX_RENDERED_ACCOUNTS = 400;

export interface VisibleGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  matchedAccounts: number;
  hiddenByCap: number;
}

function accountMatches(node: GraphNode, filter: GraphFilter, query: string): boolean {
  if (filter.outcome !== "all" && node.outcome !== filter.outcome) return false;
  return query === "" || node.label.toLowerCase().includes(query);
}

/** Context nodes (market, assets, case file, claims) always stay; accounts follow the filter and search. */
export function filterGraph(graph: ExposureGraph, filter: GraphFilter): VisibleGraph {
  const query = filter.query.trim().toLowerCase();
  const context = graph.nodes.filter((n) => n.kind !== "account");
  const matched = graph.nodes.filter((n) => n.kind === "account" && accountMatches(n, filter, query));
  const shown = matched.slice(0, MAX_RENDERED_ACCOUNTS);
  const nodes = [...context, ...shown];
  const ids = new Set(nodes.map((n) => n.id));
  return {
    nodes,
    edges: graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    matchedAccounts: matched.length,
    hiddenByCap: matched.length - shown.length,
  };
}

export interface Point {
  x: number;
  y: number;
}

export interface Layout {
  width: number;
  height: number;
  positions: Record<string, Point>;
}

const COLUMN_X = { claim: 70, evidence: 240, market: 420, asset: 610, account: 800 } as const;
const ROW_GAP = 58;
const PADDING = 60;
const MIN_HEIGHT = 420;

function spread(ids: string[], x: number, height: number): Record<string, Point> {
  const gap = height / (ids.length + 1);
  return Object.fromEntries(ids.map((id, i) => [id, { x, y: Math.round(gap * (i + 1)) }]));
}

/** Column layout in a fixed order, so the same data always draws the same picture. */
export function layoutGraph(nodes: GraphNode[]): Layout {
  const of = (kind: GraphNode["kind"]) => nodes.filter((n) => n.kind === kind).map((n) => n.id);
  const accounts = of("account");
  const height = Math.max(MIN_HEIGHT, accounts.length * ROW_GAP + PADDING * 2);
  const accountPositions = Object.fromEntries(
    accounts.map((id, i) => [id, { x: COLUMN_X.account, y: PADDING + i * ROW_GAP + ROW_GAP / 2 }]),
  );
  return {
    width: COLUMN_X.account + 170,
    height,
    positions: {
      ...spread(of("claim"), COLUMN_X.claim, height),
      ...spread(of("evidence"), COLUMN_X.evidence, height),
      ...spread(of("market"), COLUMN_X.market, height),
      ...spread([...of("collateralAsset"), ...of("debtAsset")], COLUMN_X.asset, height),
      ...accountPositions,
    },
  };
}

export interface ViewTransform {
  k: number;
  x: number;
  y: number;
}

export const IDENTITY: ViewTransform = { k: 1, x: 0, y: 0 };
export const MIN_ZOOM = 0.3;
export const MAX_ZOOM = 4;

/** Zoom by `factor` keeping the point (px, py), in view coordinates, fixed on screen. */
export function zoomAt(t: ViewTransform, factor: number, px: number, py: number): ViewTransform {
  if (!Number.isFinite(factor) || factor <= 0) return t;
  const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, t.k * factor));
  const ratio = k / t.k;
  return { k, x: px - (px - t.x) * ratio, y: py - (py - t.y) * ratio };
}

export function panBy(t: ViewTransform, dx: number, dy: number): ViewTransform {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return t;
  return { ...t, x: t.x + dx, y: t.y + dy };
}

/** Nodes linked to `id` by an edge, for highlighting the selection's neighbourhood. */
export function neighbours(edges: GraphEdge[], id: string | null): Set<string> {
  if (!id) return new Set();
  const out = new Set<string>([id]);
  for (const e of edges) {
    if (e.source === id) out.add(e.target);
    if (e.target === id) out.add(e.source);
  }
  return out;
}

/** Keep the selection only while the node is still visible. */
export function resolveSelection(nodes: GraphNode[], selectedId: string | null): GraphNode | null {
  if (!selectedId) return null;
  return nodes.find((n) => n.id === selectedId) ?? null;
}
