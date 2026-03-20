"use client";

import React from "react";

interface ChartInsightPanelProps {
  visible: boolean;
  onClose: () => void;
  // Chart description (static — fetched from DB, generated once)
  description: string;
  descriptionLoading: boolean;
  descriptionError: boolean;
  // Data insights (dynamic — LLM on hover, client-side cached)
  summary: string;
  insights: string[];
  dataLoading: boolean;
  dataError: boolean;
}

export function ChartInsightPanel({
  visible,
  onClose,
  description,
  descriptionLoading,
  descriptionError,
  summary,
  insights,
  dataLoading,
  dataError,
}: ChartInsightPanelProps) {
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        width: "220px",
        background: "#0E0E0E",
        border: "1px solid #2C2C2C",
        padding: "12px",
        zIndex: 10,
        pointerEvents: visible ? "auto" : "none",
        opacity: visible ? 1 : 0,
        transform: visible ? "translateX(0)" : "translateX(8px)",
        transition: "opacity 0.2s ease, transform 0.2s ease",
      }}
    >
      {/* ── Header row with label + close button ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "6px",
        }}
      >
        <p style={{ ...labelStyle, margin: 0 }}>About this chart</p>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: "0 2px",
            color: "#555",
            fontSize: "0.75rem",
            lineHeight: 1,
            display: "flex",
            alignItems: "center",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.color = "#A3A3A3";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.color = "#555";
          }}
          title="Close"
        >
          ✕
        </button>
      </div>
      {/* ── Section 1: Chart Description ── */}

      {descriptionLoading ? (
        <Skeleton lines={[80, 65, 75]} />
      ) : descriptionError ? (
        <p style={mutedStyle}>Could not load description.</p>
      ) : description ? (
        <p
          style={{
            margin: "0 0 10px 0",
            fontFamily: "var(--font-mono)",
            fontSize: "0.68rem",
            color: "#F5F5F5",
            lineHeight: 1.6,
          }}
        >
          {description}
        </p>
      ) : null}

      {/* ── Divider ── */}
      <div style={{ borderTop: "1px solid #1E1E1E", margin: "8px 0" }} />

      {/* ── Section 2: Data Insights ── */}
      <p style={labelStyle}>Data insights</p>

      {dataLoading ? (
        <Skeleton lines={[90, 70, 80, 65, 75]} />
      ) : dataError ? (
        <p style={mutedStyle}>
          Could not load insights. Check that the backend is running.
        </p>
      ) : (
        <>
          {summary && (
            <p
              style={{
                margin: "0 0 8px 0",
                fontFamily: "var(--font-mono)",
                fontSize: "0.7rem",
                color: "#F5F5F5",
                lineHeight: 1.6,
              }}
            >
              {summary}
            </p>
          )}
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {insights.map((insight, i) => (
              <li
                key={i}
                style={{
                  display: "flex",
                  gap: "6px",
                  marginBottom: "6px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.65rem",
                  color: "#A3A3A3",
                  lineHeight: 1.6,
                }}
              >
                <span
                  style={{ color: "#E55A5A", flexShrink: 0, marginTop: "1px" }}
                >
                  —
                </span>
                <span>{insight}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  margin: "0 0 6px 0",
  fontFamily: "var(--font-condensed)",
  fontSize: "0.6rem",
  fontWeight: 700,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: "#A3A3A3",
};

const mutedStyle: React.CSSProperties = {
  margin: 0,
  fontFamily: "var(--font-mono)",
  fontSize: "0.65rem",
  color: "#A3A3A3",
  lineHeight: 1.6,
};

function Skeleton({ lines }: { lines: number[] }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        marginBottom: "6px",
      }}
    >
      {lines.map((w, i) => (
        <div
          key={i}
          style={{
            height: "8px",
            width: `${w}%`,
            background: "#1E1E1E",
            borderRadius: "2px",
            animation: "pulse 1.4s ease-in-out infinite",
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50%       { opacity: 0.9; }
        }
      `}</style>
    </div>
  );
}
