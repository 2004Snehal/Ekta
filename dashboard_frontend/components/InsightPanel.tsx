"use client";

interface InsightPanelProps {
  insights: {
    title: string;
    description: string;
    actionable?: boolean;
  }[];
  label?: string;
}

export function InsightPanel({
  insights,
  label = "Insights",
}: InsightPanelProps) {
  if (!insights.length) return null;

  return (
    <div>
      <span
        className="section-id"
        style={{ marginBottom: "12px", display: "flex" }}
      >
        {label}
      </span>
      <div>
        {insights.map((ins, i) => (
          <div
            key={i}
            className="insight-row"
            style={{ animationDelay: `${i * 0.1}s` }}
          >
            <p
              style={{
                fontFamily: "var(--font-condensed)",
                fontSize: "0.78rem",
                fontWeight: 600,
                color: "var(--on)",
                letterSpacing: "0.02em",
                marginBottom: "3px",
              }}
            >
              {ins.title}
            </p>
            <p
              style={{
                fontSize: "0.75rem",
                color: "var(--on-mid)",
                lineHeight: 1.5,
              }}
            >
              {ins.description}
            </p>
            {ins.actionable && (
              <span
                style={{
                  display: "inline-block",
                  marginTop: "5px",
                  fontFamily: "var(--font-condensed)",
                  fontSize: "0.65rem",
                  fontWeight: 700,
                  letterSpacing: "0.14em",
                  color: "var(--action)",
                  cursor: "pointer",
                  textTransform: "uppercase",
                }}
              >
                ACT →
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
