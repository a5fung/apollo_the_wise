SET default_transaction_read_only = on;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,200), left(detail,300) FROM mi_audit_log WHERE created_at >= '2026-10-19' AND event_type='theme_sector_cap_absorbed' AND (
  detail ILIKE ANY (ARRAY['%Cloud Content, Nonprofit%','%Industrial Equipment Rental%','%Non-Alcoholic Beverages%','%Brazil Fintech%','%Recreational Vehicle%','%AI-Enabled Travel%','%Cloud Contact Center%'])) ORDER BY 1;
