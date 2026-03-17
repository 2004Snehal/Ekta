/**
 * Universal Chart Specification Types
 *
 * Every backend response that contains a chart should conform to one of these types.
 * The ChartRenderer component reads these types and decides what to render.
 *
 * Supports two flavours so the frontend stays backward-compatible:
 *   - Legacy flat spec   (x, y, yAxis on the top-level chart object)
 *   - Universal spec     (axes.x.field / axes.y.field / category / value / group_by)
 */

// ─── Axis descriptor ─────────────────────────────────────────────────────────

export interface AxisSpec {
  /** The data-object key for this axis */
  field: string;
  /** Optional human-readable label shown on the axis */
  label?: string;
}

export interface AxesSpec {
  x: AxisSpec;
  y: AxisSpec;
}

// ─── Individual chart types ───────────────────────────────────────────────────

export type ChartType =
  | 'bar'
  | 'line'
  | 'pie'
  | 'scatter'
  | 'stacked_bar'
  | 'table';

// ─── Universal chart spec (new format) ───────────────────────────────────────

export interface UniversalChartSpec {
  /** Discriminator: which kind of chart to render */
  chart_type: ChartType;

  /** Human-readable title shown in the card header */
  title?: string;

  /** Short description of what the chart shows */
  description?: string;

  /**
   * Axis mapping.
   * Required for: bar, line, scatter, stacked_bar.
   */
  axes?: AxesSpec;

  /**
   * For pie charts: the data-key that supplies slice labels.
   * @example "output_type"
   */
  category?: string;

  /**
   * For pie charts: the data-key that supplies slice sizes.
   * @example "count"
   */
  value?: string;

  /**
   * For stacked_bar: the data-key used to derive the stack series names.
   * @example "input_type"
   */
  group_by?: string;

  /** Row data — an array of plain objects */
  data: Record<string, unknown>[];

  /** Optional custom colour palette (hex strings) */
  colors?: string[];

  /** Drill-down configuration: clicking a chart element navigates to another page */
  drillDown?: {
    /** Which data key to extract the clicked value from */
    dimensionKey: string;
    /** Target route path (e.g. '/dashboard/analysis') */
    targetPage: string;
    /** How to pass the value: 'dim1' sets dim1 param, 'filter' sets filter_<dimensionKey> param */
    targetParam: 'dim1' | 'filter';
  };

  /** Reference links shown below the chart */
  refLinks?: Array<{ label: string; href: string }>;

  // ─── Legacy flat fields (kept for backward compatibility) ──────────────────

  /** @deprecated Use axes.x.field instead */
  x?: string;
  /** @deprecated Use axes.y.field instead */
  y?: string;
  /** @deprecated Use axes.y.field instead */
  yAxis?: string;
}

// ─── Full backend response wrapper ───────────────────────────────────────────

/**
 * The complete payload returned by any analytics endpoint.
 * The frontend only needs `visualization` (or `charts`) to render.
 */
export interface AnalyticsResponse {
  /** Single chart response */
  visualization?: {
    id?: string;
    title?: string;
    chart_type: ChartType;
    description?: string;
    axes?: AxesSpec;
    category?: string;
    value?: string;
    group_by?: string;
    data: Record<string, unknown>[];
    colors?: string[];
    meta?: {
      generated_sql?: string;
      row_count?: number;
    };
  };

  /** Multi-chart dashboard response */
  charts?: UniversalChartSpec[];

  /** Raw tabular data (mirrors visualization.data) */
  table?: Record<string, unknown>[];

  /** SQL that produced the data */
  sql?: string;

  /** One- or two-sentence human-readable insight */
  insight?: string;
}
