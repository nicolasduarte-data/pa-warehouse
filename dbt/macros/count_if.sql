{#
  count_if(condition) — cross-dialect equivalent of conditional counting.

  BigQuery:   COUNTIF(condition)
  Snowflake:  COUNT_IF(condition)

  Same semantics: counts the rows where `condition` evaluates to TRUE.
  NULL conditions are NOT counted (matches both dialects' behavior).

  Added for the Snowflake validation port. Use this macro
  instead of native countif() / count_if() anywhere in models so the SQL
  compiles against both targets.

  USAGE:
      select {{ count_if('is_hire') }} as hire_count
      from fact_workforce_events

  Compiles to (BigQuery):
      countif(is_hire) as hire_count
  Compiles to (Snowflake):
      count_if(is_hire) as hire_count
#}
{% macro count_if(condition) -%}
    {%- if target.type == 'bigquery' -%}
        countif({{ condition }})
    {%- else -%}
        count_if({{ condition }})
    {%- endif -%}
{%- endmacro %}
