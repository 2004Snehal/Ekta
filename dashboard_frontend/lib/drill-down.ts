/**
 * URL-param based drill-down helpers.
 * Keeps navigation state shareable, back-button friendly, and stateless.
 */

export interface DrillParams {
  dim1?: string;
  dim2?: string;
  metric?: string;
  filter?: Record<string, string>;
  from?: string;
  group_by?: string;
}

/** Build a drill-down URL string from a target page and params. */
export function buildDrillUrl(targetPage: string, params: DrillParams): string {
  const sp = new URLSearchParams();
  if (params.dim1) sp.set('dim1', params.dim1);
  if (params.dim2) sp.set('dim2', params.dim2);
  if (params.metric) sp.set('metric', params.metric);
  if (params.from) sp.set('from', params.from);
  if (params.group_by) sp.set('group_by', params.group_by);
  if (params.filter) {
    for (const [k, v] of Object.entries(params.filter)) {
      sp.set(`filter_${k}`, v);
    }
  }
  const qs = sp.toString();
  return qs ? `${targetPage}?${qs}` : targetPage;
}

/** Parse drill-down params from URLSearchParams. */
export function parseDrillParams(searchParams: URLSearchParams): {
  dim1: string | null;
  dim2: string | null;
  metric: string | null;
  filters: Record<string, string>;
  source: string | null;
  group_by: string | null;
} {
  const filters: Record<string, string> = {};
  searchParams.forEach((v, k) => {
    if (k.startsWith('filter_')) {
      filters[k.slice(7)] = v;
    }
  });
  return {
    dim1: searchParams.get('dim1'),
    dim2: searchParams.get('dim2'),
    metric: searchParams.get('metric'),
    filters,
    source: searchParams.get('from'),
    group_by: searchParams.get('group_by'),
  };
}
