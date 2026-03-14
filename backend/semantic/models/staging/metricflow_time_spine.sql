{{
  config(
    materialized = 'table',
  )
}}

SELECT
    date_day::date AS date_day
FROM
    generate_series(
        '2020-01-01'::date,
        current_date + interval '2 years',
        interval '1 day'
    ) AS t(date_day)
