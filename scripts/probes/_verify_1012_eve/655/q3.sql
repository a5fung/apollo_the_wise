-- #655 rule B (one-night wait) tonight: prior_members must be < 3 and non-null. READ-ONLY.
SELECT id, detail::json->>'theme' th, detail::json->>'members' m, detail::json->>'prior_members' prior
FROM mi_audit_log WHERE event_type='theme_retired_small_fading' AND created_at >= '2026-10-12 16:30:00-04' ORDER BY id;
