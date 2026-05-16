# Developer Documentation

## System Purpose

The application provides a versioned REST API based on FastAPI that accepts natural language tasks and forwards them to a local or configured Codex runtime via the OpenAI Codex App Server SDK.

The reorganization pursues four enterprise goals:

1. Separation of HTTP layer, service layer, configuration, and schemas.
2. Stable operability through health endpoints, structured errors, and request correlation.
3. Maintainability through clearly named modules and documented extension points.
4. Extensibility for future multi-user, security, and governance requirements.

## Architecture Overview

### Layers

- `app/main.py`: Application Factory, Middleware, CORS, and Bootstrapping.
- `app/api/`: Routers, Dependency Injection, and global error mapping.
- `app/services/`: Business logic and integration with the Codex runtime.
- `app/security/`: Authentication, role resolution, and user context.
- `app/schemas/`: Input, output, error, and health contracts.
- `app/core/`: Configuration, logging, request context, and domain errors.
- `config/`: Profile-driven runtime configuration via TOML.
- `tests/`: Layer-specific unit and endpoint tests.
- `docs/`: Operational and developer documentation.

### Request Flow

1. An HTTP request reaches FastAPI.
2. The middleware generates or adopts `X-Request-ID`.
3. The request ID is stored in the request state and logging context.
4. The router validates the payload against `TaskExecutionRequest`.
5. For protected endpoints, the user profile is resolved via the configured auth mode.
6. The monitoring subsystem records request and principal events in the process-wide runtime state.
7. Optional role validation is executed against the profile-driven authorization configuration.
8. The endpoint delegates to `CodexExecutionService`.
9. The service reports task start, workspace usage, completion, or failure to `MonitoringService`.
10. The service starts the Codex runtime, executes the task, and translates runtime errors into domain errors.
11. Global exception handlers generate a structured error response if needed.
12. The response provides the result, metadata, and headers like `X-Request-ID`.

## Runtime Configuration

The application reads configuration centrally via `app/core/config.py` and by default from `config/app.toml`.

### Profile Model

Configuration is resolved in four steps:

1. Internal safe defaults.
2. Values from `config/app.toml`.
3. Active profile from `active_profile` or `APP_ACTIVE_PROFILE`.
4. Environment variables as targeted overrides.

The included profiles are:

- `home`: Local development without authentication.
- `company`: Enterprise mode with prepared SSO and role logic.

### Key Environment Variables

- `APP_ENV`: Runtime environment, e.g., `development`, `test`, `production`.
- `API_PREFIX`: Base prefix of the versioned API, default `/api/v1`.
- `ENABLE_DOCS`: `1` enables Swagger/ReDoc, `0` disables API documentation.
- `LOG_LEVEL`: Logging level, default `INFO`.
- `CORS_ALLOWED_ORIGINS`: Comma-separated origins, default `http://localhost,http://127.0.0.1`.
- `CODEX_BIN`: Optional path to the Codex binary.
- `CODEX_MODEL`: Optional model override. If empty, local Codex default is used.
- `APP_CONFIG_FILE`: Optional path to an alternative TOML file.
- `APP_ACTIVE_PROFILE`: Forces a specific configuration profile.
- `AUTH_MODE`: Overrides the auth mode of the active profile.
- `AUTHORIZATION_ENABLED`: Enables or disables role validation.
- `AUDIT_ENABLED`: Enables or disables audit events in logging.
- `MONITORING_ENABLED`: Enables or disables live monitoring.
- `MONITORING_HISTORY_SIZE`: Number of recently completed tasks kept in in-memory history.
- `MONITORING_STREAM_ENABLED`: Enables the SSE stream for live events.
- `MONITORING_REFRESH_INTERVAL_MS`: Suggested refresh interval for terminal clients.
- `HOST`, `PORT`, `UVICORN_LOG_LEVEL`, `UVICORN_RELOAD`: Evaluated by the startup script.

### Auth Modes

- `disabled`
  Purpose:
  Development mode without login. The application generates a deterministic local principal `local-development`.

- `trusted_header`
  Purpose:
  Suitable for Windows SSO behind IIS, reverse proxy, or API gateway. The API trusts configured user headers only within the intended network path.

- `oidc_jwt`
  Purpose:
  Suitable for modern enterprise SSO architectures with bearer tokens, e.g., Microsoft Entra ID via OpenID Connect.

### Role Resolution

Phase 1 provides a configurable role base:

- `Codex-Admins` groups become role `admin`.
- `Codex-Users` groups become role `user`.
- `Codex-Readonly` groups become role `readonly`.

The concrete assignment comes from the active profile and can later be extended tenant-specifically.

## API Surface

### Functional Endpoints

- `POST /api/v1/execute_task`
  Purpose:
  Executes a single task via the Codex runtime.

### Operational Endpoints

- `GET /api/v1/health/live`
  Purpose:
  Liveness probe for process monitoring.

- `GET /api/v1/health/ready`
  Purpose:
  Readiness probe with simple validation of Codex runtime configuration.

- `GET /api/v1/monitoring/snapshot`
  Purpose:
  Returns the current live snapshot with active tasks, sessions, workspaces, and short history.

- `GET /api/v1/monitoring/events`
  Purpose:
  Streams runtime events in SSE format for the shell TUI or other admin clients.

## Error Concept

The API uses a stable error format:

```json
{
  "error": {
    "code": "invalid_task_request",
    "message": "Codex rejected the submitted task request.",
    "request_id": "9f3a0fd8-1d15-4ccf-8d64-6ab299f41f18",
    "details": "..."
  }
}
```

### Error Sources

- Validation errors of the HTTP payload.
- Domain errors from the service layer.
- Authentication or authorization errors from the security layer.
- Unexpected internal errors.
- Overloaded or faulty Codex runtime.

## Observability and Operations

### Already Implemented

- Request correlation via `X-Request-ID`.
- Consistent logging with `request_id`.
- Health endpoints for orchestration.
- Structured responses for error cases.
- Audit foundation with actor-related log events for protected task executions.
- Readiness view of the configured auth mode.
- Integrated live monitoring for administrators with in-memory runtime state per request, task, and session.
- Shell TUI `monitor_live.py` for snapshot view, live events, and filters by user/session/error.

### Monitoring Architecture

- `MonitoringService` is a process-wide singleton stored in `app.state`.
- Monitoring keeps only short in-memory history, not long-term persistence.
- Tracking events include `request_started`, `principal_resolved`, `task_started`, `workspace_created`, `workspace_reused`, `task_completed`, and `task_failed`.
- In production auth modes, monitoring endpoints are restricted to the `admin` role.
- The TUI reads snapshots over HTTP and optional live events over `text/event-stream`.

### Recommended Next Steps

- Export metrics for Prometheus/OpenTelemetry.
- Central audit logging for user actions.
- Trace propagation to external monitoring platforms.

## Test Strategy

Tests are intentionally built close to the layers:

- `tests/test_auth.py`: Auth modes and role logic.
- `tests/test_monitoring_service.py`: Runtime state, event history, and monitoring failure paths.
- `tests/test_monitoring_api.py`: Admin snapshot, SSE streaming, and monitoring endpoint helpers.
- `tests/test_monitor_live.py`: Terminal filters, header building, SSE parsing, and stream error handling.
- `tests/test_dependencies.py`: FastAPI dependency wiring and principal caching.
- `tests/test_app_factory.py`: Application factory, published routes, and monitoring singleton.
- `tests/test_codex_service.py`: Core logic and error translation.
- `tests/test_codex.py`: Endpoint contract and delegation.
- `tests/test_config.py`: Profile resolution and overrides.
- `tests/test_health.py`: Operational endpoints.
- `tests/support.py`: Shared test factories for settings and principals.

## Extension Points

### New API Version

1. Create a new package under `app/api/v2/`.
2. Build router analogous to `app/api/v1/router.py`.
3. Register in `app/api/router.py`.

### New Services

1. Add business logic in the `app/services/` package.
2. Provide new dependencies in `app/api/dependencies.py`.
3. Define own schemas in `app/schemas/`.

### New Security Modes

1. Add extension in `app/security/authentication.py`.
2. Define new settings segment in `app/core/config.py`.
3. Document configuration in `config/app.toml`.

### New Error Classes

1. Add new domain errors in `app/core/exceptions.py`.
2. Reuse existing handler as long as `ApplicationError` is extended.

## Missing Enterprise Functionality for Multi-user Operation

The application is now cleanly structured but not yet a full enterprise product. For real multi-user use, the following are especially missing:

### Identity, Access, and Multi-tenancy

- Full OIDC production wiring with real IdP registration, secret/certificate management, and operational documentation.
- Extensible role and permission model per user, team, tenant, and use case.
- Multi-tenancy or workspace isolation.
- Enforcement of least privilege and policy-based approvals.

### Persistence and Traceability

- Database for users, sessions, tasks, results, audit trails, and policies.
- Versioning and historization of executions.
- Reproducibility of runs with stored metadata.
- Deletion and retention policies according to compliance requirements.

### Security and Governance

- Secure prompt and tool governance.
- Content filters, DLP rules, and secret detection.
- Approval workflows for risky actions.
- Secret management instead of direct environment variables in all environments.
- Security boundaries for filesystem, network, and process rights per user context.

### Scaling and Resource Control

- Request queuing, concurrency limits, and prioritization.
- Worker pool or job system for long executions.
- Rate limiting per user, tenant, and API key.
- Horizontal scaling with stateless API layer.

### Operational Maturity

- Container and deployment artifacts.
- CI/CD pipelines with test, security, and release stages.
- Infrastructure-as-Code.
- SLOs, alarms, dashboards, and error budgets.

### Integratability

- API key or token-based machine-to-machine use.
- Webhooks or eventing for asynchronous results.
- Asynchronous job API with status query.
- Admin endpoints for operational and policy configuration.
