{#
  Override dbt's default schema naming to prevent "public_public" double-prefix.
  Without this macro, dbt concatenates: target_schema + custom_schema → public_public.
  With this macro, we use the custom schema directly if provided, else target schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
