import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from intelligence.chart_insight_agent.agent import generate_chart_insights
from intelligence.chart_insight_agent.schemas import ChartInsightRequest

req = ChartInsightRequest(
    chart_title="Video Count Over Time",
    chart_type="line",
    data=[
        {"period": "2024-01", "count": 150},
        {"period": "2024-02", "count": 200},
        {"period": "2024-03", "count": 180}
    ]
)
try:
    res = generate_chart_insights(req)
    print("SUCCESS")
    print(res)
except Exception as e:
    import traceback
    traceback.print_exc()
