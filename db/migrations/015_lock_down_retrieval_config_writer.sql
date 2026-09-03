-- Supabase can grant function execution directly to API roles through default
-- privileges. Revoking PUBLIC alone therefore does not necessarily remove an
-- existing direct grant. The calibration writer is an administrative endpoint:
-- only the server-side service role may call it.
revoke all on function set_active_retrieval_config(
    real, integer, text, integer, text, date
) from public, anon, authenticated;

grant execute on function set_active_retrieval_config(
    real, integer, text, integer, text, date
) to service_role;
