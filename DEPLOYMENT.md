# Django deployment

Django is the permanent web/API runtime; Flask is retired. Use `config.wsgi:application` or `config.asgi:application` behind the college HTTPS reverse proxy. Do not serve the repository directory as static content.

Install requirements, configure an uncommitted `.env`, and run `python manage.py migrate` against Django's separate SQLite application database. This includes persistent confirmation replay protection. Migrations never target ERP MariaDB. Set `VOXERP_ENV=production`, a random `DJANGO_SECRET_KEY` of at least 32 characters, `DEBUG=False`, and explicit `ALLOWED_HOSTS`. Create trusted Django accounts whose usernames match ERP student IDs; user-supplied headers/body fields cannot establish identity. Teacher scope remains fail-closed until verified mapping is available.

Local Gemma 4 E4B is the primary intent engine. Its existing MLX runtime requires a compatible model host; requirements-gemma.txt is optional. Missing inference fails closed. RBAC and the DataRouter authorize all academic reads through db_adapter. RAG contains policy documents only.

Keep `VOXERP_USE_REAL_DB=False` as the safe configuration default. Production must explicitly enable it to read ramco_academic_system. Production rejects fixture mode. Keep `VOXERP_ALLOW_REAL_WRITES=False` for validation. Signed, expiring, user-bound confirmations are consumed atomically in Django's application database across sessions/workers, and reauthorized before modification. Disabled real writes return before an ERP connection.

Use the existing private/Tailscale network for remote MariaDB. Never expose port 3306 publicly or forward it through the web proxy. Verify Tailscale peer reachability, private TCP connectivity, then database authentication/SELECT permissions. A failed TCP connection does not identify whether firewall, listener, or Tailscale caused it; do not change credentials or application code to compensate.

Run `python scripts/validate_real_reads.py --student-id <approved-id> --subject <course-code>` from the backend host. It forces read-only MariaDB sessions, checks consolidated marks, hourly subject attendance and course-resolved timetable through the adapter/service, and reports that inference is stubbed. It performs no attendance writes and logs no credentials or academic results. Ordinary pytest blocks network/MariaDB connections and excludes manual production transaction probes.
