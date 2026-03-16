"""
GET /profiles — returns all 5 user profile definitions.
GET /profiles/{profile_key} — returns a single profile by key.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()

PROFILES = {
    "founder": {
        "key": "founder",
        "display_name": "Founders / Leadership",
        "focus": "Strategic growth, revenue impact, portfolio",
        "default_kpis": ["publish_rate", "total_duration", "growth_pct"],
        "default_view": "/dashboard",
        "description": "High-level strategic view of the entire operation",
    },
    "client_success": {
        "key": "client_success",
        "display_name": "Client Success",
        "focus": "Client health, adoption, retention signals",
        "default_kpis": ["active_channels", "publish_rate", "usage_trend"],
        "default_view": "/dashboard/analysis",
        "description": "Client-centric health monitoring and adoption tracking",
    },
    "operations": {
        "key": "operations",
        "display_name": "Operations",
        "focus": "Throughput, bottlenecks, team efficiency",
        "default_kpis": ["processed_videos", "publish_rate", "avg_turnaround"],
        "default_view": "/dashboard/usage",
        "description": "Operational throughput and process efficiency",
    },
    "editorial": {
        "key": "editorial",
        "display_name": "Editorial / Production",
        "focus": "Content quality, type mix, editorial decisions",
        "default_kpis": ["output_type_mix", "input_type_trend", "publish_rate"],
        "default_view": "/dashboard/funnel",
        "description": "Content pipeline and editorial decision support",
    },
    "tech_product": {
        "key": "tech_product",
        "display_name": "Tech / Product",
        "focus": "Data quality, platform health, system metrics",
        "default_kpis": ["missing_data_pct", "error_rate", "platform_coverage"],
        "default_view": "/dashboard/explorer",
        "description": "Technical health monitoring and data quality",
    },
}


@router.get("/profiles")
def list_profiles():
    """Return all supported user profiles."""
    return {"profiles": list(PROFILES.values())}


@router.get("/profiles/{profile_key}")
def get_profile(profile_key: str):
    """Return a single profile by its key."""
    profile = PROFILES.get(profile_key)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Profile '{profile_key}' not found. "
                   f"Valid keys: {', '.join(PROFILES)}",
        )
    return profile
