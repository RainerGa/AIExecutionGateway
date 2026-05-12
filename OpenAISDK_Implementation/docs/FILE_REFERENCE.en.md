# File Reference

This reference describes every relevant program file of the project, its purpose, its responsibility, and its most important technical details.

## Runtime Entry and Operation

### `start_server.sh`

Responsibility:
Starts the application locally or on a server with consistent environment variables.

Important details:
- optionally activates `venv`
- validates `uvicorn`
- validates `CODEX_BIN`
- supports `APP_CONFIG_FILE`, `APP_ACTIVE_PROFILE`, `HOST`, `PORT`, `CODEX_MODEL`, `UVICORN_RELOAD`, `UVICORN_LOG_LEVEL`
- uses `exec uvicorn` so that the started Uvicorn process model can correctly adopt PID-1 behavior

### `requirements.txt`

Responsibility:
Defines the minimum Python dependencies for API, validation, testing, and Codex SDK.

### `config/app.toml`

Responsibility:
Defines the application's profile configuration for `home` and `company`.

Important details:
- contains safe defaults
- encapsulates auth modes, role mapping, and audit flags
- serves as a master switch for development without auth and enterprise operation with SSO

## Application Package

### `app/__init__.py`

Responsibility:
Marks the directory as a Python package and holds the central application version.

Important symbols:
- `__version__`: adopted by `app/core/config.py`

### `app/main.py`

Responsibility:
Creates the FastAPI application, registers middleware, CORS, routers, and exception handlers.

Important functions:
- `create_application()`: factory for the complete app
- `request_context_middleware()`: generates request ID, measures runtime, and writes headers
- `root()`: minimal root endpoint without OpenAPI schema entry

Important dependencies:
- `app/api/router.py`
- `app/api/error_handlers.py`
- `app/core/config.py`
- `app/core/logging.py`
- `app/core/request_context.py`

## Core Layer

### `app/core/__init__.py`

Responsibility:
Package marker and semantic grouping of core components.

### `app/core/config.py`

Responsibility:
Reads environment variables centrally and encapsulates them in `AppSettings`.

Important functions and types:
- `_parse_csv()`: normalizes CORS configurations
- `_resolve_profile_document()`: merges defaults, file, profile, and env overrides
- `AppSettings`: immutable configuration object (incl. `codex_project_source` and `codex_sessions_base_path`)
- `AuthSettings`, `OidcSettings`, `TrustedHeaderSettings`, `AuthorizationSettings`, `AuditSettings`
- `get_settings()`: cached access to the process configuration

### `app/core/request_context.py`

Responsibility:
Provides request context for logging and correlation via `contextvars`.

Important functions:
- `get_request_id()`
- `set_request_id()`
- `reset_request_id()`

### `app/core/logging.py`

Responsibility:
Initializes process logging and supplements every log entry with `request_id`.

Important elements:
- `RequestContextFilter`
- `configure_logging()`

### `app/core/exceptions.py`

Responsibility:
Defines stable domain errors triggered by services and converted by the API into HTTP responses.

Important classes:
- `ApplicationError`
- `InvalidTaskRequestError`
- `CodexRuntimeBusyError`
- `CodexExecutionError`
- `ConfigurationError`
- `AuthenticationRequiredError`
- `AuthenticationFailedError`
- `AuthorizationDeniedError`

## Security Layer

### `app/security/__init__.py`

Responsibility:
Package marker for authentication and authorization.

### `app/security/models.py`

Responsibility:
Defines the user context for a single request.

Important classes:
- `UserPrincipal`

### `app/security/authentication.py`

Responsibility:
Implements configurable auth modes and role-based release for task execution.

Important functions and classes:
- `AuthenticationService`
- `resolve_principal()`
- `require_execute_task_access()`
- `readiness_components()`

Important operational details:
- supports `disabled`, `trusted_header`, `oidc_jwt`
- maps groups to roles
- validates OIDC dependencies and readiness
- provides basis for audit and actor context

## API Layer

### `app/api/__init__.py`

Responsibility:
Package marker for the HTTP layer.

### `app/api/router.py`

Responsibility:
Aggregates all API versions and integrates them under the configured prefix.

### `app/api/dependencies.py`

Responsibility:
Encapsulates FastAPI dependencies for settings, services, and request context.

Important functions:
- `get_request_id()`
- `get_codex_execution_service()`
- `get_authentication_service()`
- `get_current_principal()`
- `require_task_execution_principal()`

### `app/api/error_handlers.py`

Responsibility:
Registers global error handling and ensures a stable error format.

Important functions:
- `handle_application_error()`
- `handle_validation_error()`
- `handle_unexpected_error()`
- `register_exception_handlers()`

## API Version 1

### `app/api/v1/__init__.py`

Responsibility:
Package marker for version 1 of the public API.

### `app/api/v1/router.py`

Responsibility:
Assembles the endpoint groups of version 1 from functional and operational routes.

### `app/api/v1/endpoints/__init__.py`

Responsibility:
Package marker for endpoints of API version 1.

### `app/api/v1/endpoints/codex.py`

Responsibility:
Defines the functional task endpoint of the API.

Important details:
- uses dependency injection for service and request ID
- protects the task endpoint via the security dependency
- describes OpenAPI responses for error cases
- contains no business logic anymore

Important function:
- `execute_task()`

### `app/api/v1/endpoints/health.py`

Responsibility:
Defines liveness and readiness endpoints for monitoring, orchestration, and load balancers.

Important functions:
- `read_liveness()`
- `read_readiness()`

## Schema Layer

### `app/schemas/__init__.py`

Responsibility:
Package marker for reusable API and service contracts.

### `app/schemas/codex.py`

Responsibility:
Describes request, response, and metadata for task executions.

Important classes:
- `TaskExecutionRequest`
- `TaskExecutionMetadata`
- `TaskExecutionResponse`

Important validation:
- trims whitespace
- prevents empty or pure whitespace tasks
- limits maximum request length

### `app/schemas/errors.py`

Responsibility:
Defines the standardized error format.

Important classes:
- `ErrorDetail`
- `ErrorResponse`

### `app/schemas/health.py`

Responsibility:
Defines health contracts for operational endpoints.

Important classes:
- `HealthComponent`
- `HealthResponse`

## Service Layer

### `app/services/__init__.py`

Responsibility:
Package marker for functional services.

### `app/services/codex_service.py`

Responsibility:
Encapsulates the entire integration with Codex including error translation and health check.

Important functions and classes:
- `CodexExecutionService`
- `execute_task()`
- `readiness_components()`
- `_build_app_server_config()`
- `_build_thread_start_kwargs()`

Important operational details:
- starts a fresh Codex session per request
- manages dynamic workspaces (`codex_sessions_base_path`), isolated per session ID
- optionally copies a template project (`codex_project_source`) into the new session
- measures execution duration
- logs task size instead of content
- logs actor and audit context
- translates SDK errors into domain errors

## Tests

### `tests/conftest.py`

Responsibility:
Ensures that the local package is importable during the test run.

Important details:
- clears the settings cache automatically per test case

### `tests/test_codex.py`

Responsibility:
Checks the API endpoint delegation at the handler level.

Important tests:
- endpoint call delegates correctly to the injected service

### `tests/test_codex_service.py`

Responsibility:
Checks the core logic of the service layer.

Important test cases:
- successful task run
- behavior without model override
- translation of JSON-RPC errors
- translation of busy errors
- translation of unexpected errors

### `tests/test_health.py`

Responsibility:
Checks the liveness and readiness logic independently of the HTTP transport.

### `tests/test_auth.py`

Responsibility:
Checks auth modes, group mapping, and role-based access control.

Important test cases:
- local `disabled` mode
- `trusted_header` with and without user header
- role mapping from groups
- OIDC path with patched token decoding

### `tests/test_config.py`

Responsibility:
Checks profile resolution and targeted environment variable overrides.

### `tests/support.py`

Responsibility:
Provides reusable test factories for settings and principals.

## Documentation

### `README.md`

Responsibility:
Introduction, operation, setup, and usage from the perspective of users and integrators.

### `docs/DEVELOPER_GUIDE.md`

Responsibility:
Describes architecture, layers, request flow, extension points, and enterprise gaps.

### `docs/FILE_REFERENCE.md`

Responsibility:
Provides the exact file documentation for maintenance, onboarding, and code reviews.
