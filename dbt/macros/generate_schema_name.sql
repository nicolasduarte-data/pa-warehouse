{#
  generate_schema_name — override dbt's default schema naming behavior.

  Default dbt behavior: output dataset = "{profile_dataset}_{custom_schema}"
  e.g., staging models → "raw_staging", core → "raw_core". Not what we want.

  This override: use custom_schema_name directly when set.
  Result: staging models → "staging" dataset, core → "core", marts → "marts".
  These map exactly to the three BigQuery datasets created in Story 1.2.5.

  When custom_schema_name is None (no +schema in dbt_project.yml), fall back
  to the profile's default dataset ("raw"). No model in this project should
  hit that path — every layer has an explicit +schema override.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
