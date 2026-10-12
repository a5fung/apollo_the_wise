select created_at at time zone 'America/New_York' as et, event_type, summary, left(detail, 900) detail
from mi_audit_log where created_at >= timestamptz '2026-10-12 08:00:00-04' and created_at < timestamptz '2026-10-12 10:05:00-04'
and (event_type like 'paper_rehearsal%' or event_type in ('entry_partial_fill','planned_sale_stop_cancel','stop_cancel_by_planned_sale_silent','stop_ack_timeout_remediated','coverage_drift_alerted','ingest_proposed','stop_order_id_changed','order_status_reconciled','dead_stop_price_preserved'))
order by created_at;
