import { DriveStep } from "driver.js";

// Helper to determine steps based on current route
export const getTutorialSteps = (pathname: string): DriveStep[] => {
  // Normalize path (handle trailing slashes or sub-paths)
  const path = pathname.replace(/\/$/, "") || "/";

  // 1. DASHBOARD (Main View) - Detailed
  if (path === "/" || path === "/dashboard") {
    return [
      {
        element: "#sidebar-link-natural-language-query",
        popover: {
          title: "Natural Language Query",
          description: "Ask questions in plain English here (e.g., 'Show me error rates for last week').",
          side: "right",
          align: "start",
        }
      },
      {
        element: "#sidebar-link-insight-narrator",
        popover: {
          title: "Insight Narrator",
          description: "Access AI-generated data stories and anomaly reports.",
          side: "right",
          align: "start",
        }
      },
      {
        element: "#sidebar-link-kpi-lab",
        popover: {
          title: "KPI Laboratory",
          description: "Deep dive into specific metrics and analyze trends.",
          side: "right",
          align: "start",
        }
      },
      {
        element: "#sidebar-link-workspace",
        popover: {
          title: "Workspace",
          description: "Manage your saved reports, team settings, and preferences.",
          side: "right",
          align: "start",
        }
      },
      {
        element: "#dashboard-filters-section",
        popover: {
          title: "Global Filters",
          description: "Filter all dashboard data by Client, Platform, Language, and more here.",
          side: "bottom",
          align: "start",
        }
      },
      {
        element: "#dashboard-kpis-strip",
        popover: {
          title: "Key Performance Indicators",
          description: "Track critical metrics like <b>Published Videos</b>, <b>Processing Time</b>, and <b>Error Rates</b> at a glance.",
          side: "bottom",
          align: "start",
        }
      },
      {
        element: "#tutorial-restart-btn",
        popover: {
          title: "Replay Tutorial",
          description: "Click here anytime to see these tips again.",
          side: "top",
          align: "start",
        }
      }
    ];
  }

  // 2. NLQ (Query) Page
  if (path.startsWith("/query")) {
    return [
      { 
        element: "#query-input-container", 
        popover: { 
          title: "Ask Anything", 
          description: "Type your question here. E.g., <i>'Compare video duration vs processing time for YouTube'</i>.", 
          side: "bottom", 
          align: "center" 
        } 
      }
    ];
  }

  // 3. KPI Lab
  if (path.startsWith("/kpi-lab")) {
    return [
      { 
        element: "#kpi-lab-container", 
        popover: { 
          title: "KPI Laboratory", 
          description: "Discover new metrics and analyze anomalies in your data automatically detected by AI.", 
          side: "top", 
          align: "center" 
        } 
      }
    ];
  }

  // 4. Insight Narrator
  if (path.startsWith("/narrator")) {
    return [
      { 
        element: "main", 
        popover: { 
          title: "Insight Narrator", 
          description: "Your automated data storyteller. View AI-generated reports on anomalies and trends here.", 
          side: "top", 
          align: "center" 
        } 
      }
    ];
  }

  // Default Fallback
  return [
    {
      element: "#sidebar-nav",
      popover: {
        title: "Navigation",
        description: "Use the sidebar to explore different modules.",
        side: "right",
        align: "start"
      }
    }
  ];
};
