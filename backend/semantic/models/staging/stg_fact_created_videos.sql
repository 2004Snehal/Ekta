{{
  config(materialized='view')
}}

SELECT
    f.id,
    f.video_id,
    f.client_id,
    f.channel_id,
    f.user_id,
    f.team_id,
    f.input_type_id,
    f.output_type_id,
    f.language_id,

    -- durations
    f.uploaded_duration_secs,
    f.created_duration_secs,
    f.published_duration_secs,

    -- timestamps
    f.uploaded_at,

    -- publish info
    f.published_flag,
    f.published_platform_id,

    -- content fields (for SQL path row-level queries)
    f.headline,
    f.source_url,

    -- channel attributes (denormalized for MetricFlow dimensions)
    c.channel_name,
    c.channel_code,
    c.content_focus              AS channel_content_focus,

    -- user attributes
    u.user_name,
    u.role                       AS user_role,
    u.is_bot,

    -- team attributes
    t.team_name,

    -- input type attributes
    it.type_name                 AS input_type_name,
    it.category                  AS input_type_category,

    -- output type attributes
    ot.type_name                 AS output_type_name,
    ot.is_short_form,

    -- language attributes
    l.language_name,
    l.language_code,

    -- platform attributes
    p.platform_name,
    p.platform_type

FROM {{ source('frammer', 'fact_created_videos') }} f
LEFT JOIN {{ source('frammer', 'dim_channel') }}     c  ON f.channel_id            = c.channel_id
LEFT JOIN {{ source('frammer', 'dim_user') }}        u  ON f.user_id               = u.user_id
LEFT JOIN {{ source('frammer', 'dim_team') }}        t  ON f.team_id               = t.team_id
LEFT JOIN {{ source('frammer', 'dim_input_type') }}  it ON f.input_type_id         = it.input_type_id
LEFT JOIN {{ source('frammer', 'dim_output_type') }} ot ON f.output_type_id        = ot.output_type_id
LEFT JOIN {{ source('frammer', 'dim_language') }}    l  ON f.language_id           = l.language_id
LEFT JOIN {{ source('frammer', 'dim_platform') }}    p  ON f.published_platform_id = p.platform_id
