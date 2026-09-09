# College-hosted deployment

This is the proposed college-managed production deployment, not evidence of a
completed deployment. The current development handoff uses a Windows ERP/database
machine reached through Tailscale. The final model/backend host must independently
validate access; a developer laptop check does not establish production readiness.

```text
Students and faculty -> HTTPS :443 -> college reverse proxy / IdP
                                        -> VoxERP WSGI service (private)
                                        -> private MariaDB :3306
```

## Development network: Tailscale

Use the existing Tailscale network to reach the Windows ERP/database machine.
Set `DB_HOST` to its approved Tailscale address or private hostname in the local
secret configuration; no actual address or credentials are recorded here.
MariaDB port 3306 must not be exposed publicly. Tailscale access does not replace
MariaDB account/host authorization or application RBAC.

Validate from the intended backend/model environment in this order:

1. Verify local Tailscale is connected and the ERP peer is reachable using
   `tailscale status`, then `tailscale ping <erp-tailscale-address>`.
2. Verify TCP with PowerShell:
   `Test-NetConnection -ComputerName <erp-tailscale-address> -Port 3306`.
   A timeout/refusal is a listener/network issue, not proof of a bad password.
3. Verify MariaDB authentication using the existing account and protected
   credentials. Do not put passwords in commands, output, screenshots or logs.
   Distinguish a host-not-authorized error from an authentication failure;
   an access-denied response may require DBA inspection of both the matched
   user/host account and credentials. Do not randomly change passwords/grants.
4. Verify access to `ramco_academic_system` and SELECT permission on the required
   tables in [SCHEMA_MAPPING.md](SCHEMA_MAPPING.md). Successful login alone does
   not prove database/table permission. Ask the DBA to inspect existing host
   grants, bind configuration and private firewall scope if needed; do not open
   a public listener or broaden grants as a diagnostic shortcut.
5. Keep `VOXERP_ALLOW_REAL_WRITES=False` and `VOXERP_INITIALIZE_DATABASE=False`
   for real READ validation. Verify own marks, attendance and timetable through
   the integrated application, and verify cross-student requests are denied.

Record pass/fail and the failing layer without credentials or academic records.
Release validation confirmed the local Tailscale node online and localhost
MariaDB READ access. Remote B/C reachability and firewall/public-exposure checks
have not been certified; a local successful login does not prove remote grants. See [README.md](README.md) for isolated
SQLite testing and collection settings.

## Production application configuration

Store these values in the college secret manager or a file readable only by the
VoxERP service account. Do not commit that file. The database password and
`VOXERP_PENDING_SECRET` are secret values and are intentionally not shown here.

```env
VOXERP_ENV=production
VOXERP_USE_REAL_DB=True
VOXERP_ALLOW_REAL_WRITES=False
VOXERP_AUTH_MODE=proxy
VOXERP_INITIALIZE_DATABASE=False
VOXERP_TRUSTED_PROXY_CIDRS=127.0.0.1/32
VOXERP_ROLE_GROUPS=college-voxerp-admins:admin,college-voxerp-teachers:teacher,college-voxerp-students:student
VOXERP_CONFIRMATION_TTL_SECONDS=300
DB_HOST=<private-college-db-dns-name>
DB_PORT=3306
DB_USER=<college-provisioned-service-account>
DB_NAME=ramco_academic_system
```

`VOXERP_INITIALIZE_DATABASE` is ignored in production. Importing the WSGI application performs no database operations. `/healthz`
performs a read-only connection check; production bootstrap never creates, seeds,
migrates or modifies MariaDB objects.

The WSGI service can be run with Waitress, bound only to loopback or a private
interface:

```bash
waitress-serve --listen=127.0.0.1:5050 wsgi:app
```

The reverse proxy is the only component exposed to users. It terminates HTTPS,
integrates with the college IdP, removes any user-supplied forwarded-identity
headers, and injects only trusted headers after authentication:

- `X-Forwarded-User`: immutable college principal ID
- `X-Forwarded-Groups`: comma-separated college groups
- `X-Forwarded-Student-Id`: ERP student ID, for authenticated students only

Set `VOXERP_TRUSTED_PROXY_CIDRS` to the actual proxy source address(es). Do not
publish port 5050. Do not allow a client path that can reach the backend and
forge these headers.

## Persistent access model

- Normal students/faculty: college IdP account plus a persistent VoxERP group;
  HTTPS application/API access only.
- Person A/B/C: managed accounts in a college VPN/zero-trust developer group;
  access the app host and approved staging resources, not MariaDB by default.
- Administrator/owner: a persistent college administrator group for server,
  proxy, deployment, and secret-management administration. Database access is
  granted separately by the DBA when required and is audited.

The college firewall must allow MariaDB port 3306 only from the VoxERP backend
host (and separately approved DBA paths). Never expose MariaDB to the public
internet or to every VPN user.

## Deployment sequence

1. College IT provisions the always-on app host, DNS name, TLS certificate,
   reverse proxy/IdP integration, service account, log collection, monitoring,
   backup ownership, and developer access groups.
2. The DBA provisions the least-privilege VoxERP database account and permits
   it only from approved backend hosts. Own-data READ operations use the ERP
   academic tables; they do not require `voxerp_write_log`. The current demo
   `/users` route lists local SQLite fixture users only; proxy/real modes disable
   that route. Do not enable initialization to create demo objects on the ERP.
3. Place production environment values in the managed secret store and deploy
   the code/dependencies to the college host.
4. Start the WSGI service and configure the reverse proxy to reach only its
   private listener. Verify `/healthz` through the internal health-check path.
5. Verify an authenticated student, faculty member, and developer account;
   verify direct backend and direct MariaDB access are denied.
6. Run reviewed READ-only checks with real writes disabled. Existing MariaDB
   suites include initialization/write expectations and are not read-only suites.
   Controlled writes belong in SQLite tests; any future isolated MariaDB write
   validation requires explicit owner approval. Do not run manual transaction
   probes or the complete real-MariaDB suite against production.
7. After rollback and monitoring checks pass, direct the college DNS name to
   the new proxy. The service then remains available while any developer laptop
   is offline.

## Remaining application limitation

The current Flask code contains attendance confirmation branches for `student`
and `teacher`, but real ERP writes remain disabled and the complete production
write workflow is not approved. The `admin` group is for college infrastructure administration unless
the RBAC owner explicitly approves an application-level administrator policy.

Flask now integrates B's reviewed pipeline with trusted proxy identity and signed
confirmations. Only `index.html` is served by the root route; project-root static
serving is disabled. Students require a nonempty trusted ERP identity mapping.
Confirmations bind principal, role and student identity and invoke B's RBAC again.
B's teacher scope remains fail-closed until an authorized mapping exists.

Model dependencies and exact-version handoff are described in README.md. Do not
install the optional MLX stack on an unverified host. The frontend uses a ten-second
request timeout; C must validate it against actual model cold-start latency.
