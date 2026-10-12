select created_at at time zone 'America/New_York' as et, event_type, summary, left(detail, 600) from mi_audit_log
where created_at >= timestamptz '2026-10-12 07:00:00-04' and event_type in ('stop_refresh_ran','unified_allocation_decided','coverage_drift_detected','coverage_drift_alerted','ep_rt_admit','mna_filter_fired','health_heartbeat_ok','evening_verify_heartbeat_ok') order by created_at;
