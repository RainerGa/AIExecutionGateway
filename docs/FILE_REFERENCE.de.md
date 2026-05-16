# Dateireferenz

Diese Referenz beschreibt jede relevante Programmdatei des Projekts, ihren Zweck, ihre Verantwortlichkeit und ihre wichtigsten technischen Details.

## Laufzeiteinstieg und Betrieb

### `start_server.sh`

Verantwortung:
Startet die Anwendung lokal oder auf einem Server mit konsistenten Umgebungsvariablen.

Wichtige Details:
- aktiviert optional `venv`
- validiert `uvicorn`
- validiert `CODEX_BIN`
- unterstützt `APP_CONFIG_FILE`, `APP_ACTIVE_PROFILE`, `HOST`, `PORT`, `CODEX_MODEL`, `UVICORN_RELOAD`, `UVICORN_LOG_LEVEL`
- reicht auch Monitoring-Overrides wie `MONITORING_ENABLED`, `MONITORING_HISTORY_SIZE`, `MONITORING_STREAM_ENABLED` durch
- nutzt `exec uvicorn`, damit das gestartete Uvicorn-Prozessmodell korrekt das PID-1-Verhalten übernehmen kann

### `monitor_live.py`

Verantwortung:
Stellt eine Shell-TUI im Stil von `top` für Administratoren bereit.

Wichtige Details:
- liest `GET /api/v1/monitoring/snapshot`
- kann zusätzlich `GET /api/v1/monitoring/events` als SSE-Stream konsumieren
- unterstützt Filter nach Benutzer, Session, Status und Fehlern
- verzichtet bewusst auf zusätzliche schwere UI-Abhängigkeiten

### `requirements.txt`

Verantwortung:
Definiert die minimalen Python-Abhängigkeiten für API, Validierung, Test und Codex-SDK.

### `config/app.toml`

Verantwortung:
Definiert die Profilkonfiguration der Anwendung für `home` und `company`.

Wichtige Details:
- enthält sichere Defaults
- kapselt Auth-Modi, Rollenmapping und Audit-Flags
- dient als Hauptschalter für Entwicklung ohne Auth und Unternehmensbetrieb mit SSO

## Anwendungspaket

### `app/__init__.py`

Verantwortung:
Markiert das Verzeichnis als Python-Paket und hält die zentrale Applikationsversion.

Wichtige Symbole:
- `__version__`: wird von `app/core/config.py` übernommen

### `app/main.py`

Verantwortung:
Erzeugt die FastAPI-Anwendung, registriert Middleware, CORS, Router und Exception-Handler.

Wichtige Funktionen:
- `create_application()`: Factory für die vollständige App
- `request_context_middleware()`: erzeugt Request-ID, misst Laufzeit und schreibt Header
- `root()`: minimaler Root-Endpunkt ohne OpenAPI-Schemaeintrag

Wichtige Abhängigkeiten:
- `app/api/router.py`
- `app/api/error_handlers.py`
- `app/core/config.py`
- `app/core/logging.py`
- `app/core/request_context.py`
- `app/services/monitoring_service.py`

Wichtige Betriebsdetails:
- hält `MonitoringService` als Singleton in `app.state`
- erzeugt `request_started`-Ereignisse bereits in der Middleware

## Core-Schicht

### `app/core/__init__.py`

Verantwortung:
Paketmarker und semantische Gruppierung der Core-Bausteine.

### `app/core/config.py`

Verantwortung:
Liest Umgebungsvariablen zentral ein und kapselt sie in `AppSettings`.

Wichtige Funktionen und Typen:
- `_parse_csv()`: normiert CORS-Konfigurationen
- `_resolve_profile_document()`: führt Defaults, Datei, Profil und Env-Overrides zusammen
- `AppSettings`: unveränderliches Konfigurationsobjekt (inkl. `codex_project_source` und `codex_sessions_base_path`)
- `AuthSettings`, `OidcSettings`, `TrustedHeaderSettings`, `AuthorizationSettings`, `AuditSettings`, `MonitoringSettings`
- `get_settings()`: gecachter Zugriff auf die Prozesskonfiguration

### `app/core/request_context.py`

Verantwortung:
Stellt Request-Kontext für Logging und Korrelation über `contextvars` bereit.

Wichtige Funktionen:
- `get_request_id()`
- `set_request_id()`
- `reset_request_id()`

### `app/core/logging.py`

Verantwortung:
Initialisiert das Prozess-Logging und ergänzt jeden Logeintrag um `request_id`.

Wichtige Elemente:
- `RequestContextFilter`
- `configure_logging()`

### `app/core/exceptions.py`

Verantwortung:
Definiert stabile Domänenfehler, die von Services ausgelöst und von der API in HTTP-Responses umgewandelt werden.

Wichtige Klassen:
- `ApplicationError`
- `InvalidTaskRequestError`
- `CodexRuntimeBusyError`
- `CodexExecutionError`
- `ConfigurationError`
- `AuthenticationRequiredError`
- `AuthenticationFailedError`
- `AuthorizationDeniedError`

## Security-Schicht

### `app/security/__init__.py`

Verantwortung:
Paketmarker für Authentifizierung und Autorisierung.

### `app/security/models.py`

Verantwortung:
Definiert den Benutzerkontext für eine einzelne Anfrage.

Wichtige Klassen:
- `UserPrincipal`

### `app/security/authentication.py`

Verantwortung:
Implementiert die konfigurierbaren Auth-Modi und die rollenbasierte Freigabe für Task-Ausführung.

Wichtige Funktionen und Klassen:
- `AuthenticationService`
- `resolve_principal()`
- `require_execute_task_access()`
- `require_admin_access()`
- `readiness_components()`

Wichtige Betriebsdetails:
- unterstützt `disabled`, `trusted_header`, `oidc_jwt`
- mappt Gruppen zu Rollen
- validiert OIDC-Abhängigkeiten und Readiness
- liefert Grundlagen für Audit- und Actor-Kontext

## API-Schicht

### `app/api/__init__.py`

Verantwortung:
Paketmarker für die HTTP-Schicht.

### `app/api/router.py`

Verantwortung:
Aggregiert alle API-Versionen und bindet sie unter dem konfigurierten Prefix ein.

### `app/api/dependencies.py`

Verantwortung:
Kapselt FastAPI-Dependencies für Settings, Services und Request-Kontext.

Wichtige Funktionen:
- `get_request_id()`
- `get_monitoring_service()`
- `get_codex_execution_service()`
- `get_authentication_service()`
- `get_current_principal()`
- `require_task_execution_principal()`
- `require_admin_principal()`

### `app/api/error_handlers.py`

Verantwortung:
Registriert globale Fehlerbehandlung und sorgt für ein stabiles Fehlerformat.

Wichtige Funktionen:
- `handle_application_error()`
- `handle_validation_error()`
- `handle_unexpected_error()`
- `register_exception_handlers()`

## API Version 1

### `app/api/v1/__init__.py`

Verantwortung:
Paketmarker für Version 1 der öffentlichen API.

### `app/api/v1/router.py`

Verantwortung:
Setzt die Endpunktgruppen von Version 1 aus Fach- und Betriebsrouten zusammen.

### `app/api/v1/endpoints/__init__.py`

Verantwortung:
Paketmarker für Endpunkte der API-Version 1.

### `app/api/v1/endpoints/codex.py`

Verantwortung:
Definiert den fachlichen Task-Endpunkt der API.

Wichtige Details:
- nutzt Dependency Injection für Service und Request-ID
- schützt den Task-Endpunkt über die Security-Dependency
- beschreibt OpenAPI-Responses für Fehlerfälle
- enthält keine Geschäftslogik mehr

Wichtige Funktion:
- `execute_task()`

### `app/api/v1/endpoints/health.py`

Verantwortung:
Definiert Liveness- und Readiness-Endpunkte für Monitoring, Orchestrierung und Load-Balancer.

Wichtige Funktionen:
- `read_liveness()`
- `read_readiness()`

### `app/api/v1/endpoints/monitoring.py`

Verantwortung:
Definiert die Admin-Endpunkte für Live-Snapshots und SSE-Live-Events.

Wichtige Funktionen:
- `read_monitoring_snapshot()`
- `stream_monitoring_events()`

Wichtige Details:
- nutzt `require_admin_principal()`
- liefert `MonitoringSnapshot` oder `text/event-stream`

## Schema-Schicht

### `app/schemas/__init__.py`

Verantwortung:
Paketmarker für wiederverwendbare API- und Service-Verträge.

### `app/schemas/codex.py`

Verantwortung:
Beschreibt Request, Response und Metadaten für Task-Ausführungen.

Wichtige Klassen:
- `TaskExecutionRequest`
- `TaskExecutionMetadata`
- `TaskExecutionResponse`

Wichtige Validierung:
- trimmt Leerraum
- verhindert leere oder reine Whitespace-Tasks
- begrenzt die maximale Request-Länge

### `app/schemas/errors.py`

Verantwortung:
Definiert das standardisierte Fehlerformat.

Wichtige Klassen:
- `ErrorDetail`
- `ErrorResponse`

### `app/schemas/health.py`

Verantwortung:
Definiert Health-Verträge für Betriebsendpunkte.

Wichtige Klassen:
- `HealthComponent`
- `HealthResponse`

### `app/schemas/monitoring.py`

Verantwortung:
Beschreibt Verträge für Live-Monitoring, Session-Sichten, Ereignisse und Snapshots.

Wichtige Klassen:
- `MonitoringEvent`
- `TaskRuntimeRecord`
- `SessionRuntimeRecord`
- `MonitoringSnapshot`

## Service-Schicht

### `app/services/monitoring_service.py`

Verantwortung:
Hält den prozessweiten In-Memory-Zustand für aktives Monitoring.

Wichtige Funktionen:
- `record_request_started()`
- `record_principal_resolved()`
- `record_task_started()`
- `record_workspace_event()`
- `record_task_completed()`
- `record_task_failed()`
- `snapshot()`
- `events_after()`

Wichtige Details:
- schützt Zustand mit Lock
- verwaltet aktive Tasks, Sessions, Event-Historie und Kurz-Verlauf
- ist bewusst nicht persistent und nicht clusterweit aggregiert

### `app/services/__init__.py`

Verantwortung:
Paketmarker für fachliche Services.

### `app/services/codex_service.py`

Verantwortung:
Kapselt die gesamte Integration mit Codex inklusive Fehlerübersetzung und Health-Prüfung.

Wichtige Funktionen und Klassen:
- `CodexExecutionService`
- `execute_task()`
- `readiness_components()`
- `_build_app_server_config()`
- `_build_thread_start_kwargs()`

Wichtige Betriebsdetails:
- startet pro Request eine frische Codex-Session
- verwaltet dynamische Arbeitsverzeichnisse (`codex_sessions_base_path`), isoliert pro Session-ID
- kopiert optional ein Vorlagenprojekt (`codex_project_source`) in die neue Session
- misst Ausführungsdauer
- protokolliert Task-Größe statt Inhalt
- protokolliert Actor- und Audit-Kontext
- übersetzt SDK-Fehler in Domänenfehler

## Tests

### `tests/conftest.py`

Verantwortung:
Stellt sicher, dass das lokale Paket beim Testlauf importierbar ist.

Wichtige Details:
- leert den Settings-Cache automatisch pro Testfall

### `tests/test_codex.py`

Verantwortung:
Prüft die API-Endpunktdelegation auf Handler-Ebene.

Wichtige Tests:
- Endpoint-Aufruf delegiert korrekt an den injizierten Service

### `tests/test_codex_service.py`

Verantwortung:
Prüft die Kernlogik des Service-Layers.

Wichtige Testfälle:
- erfolgreicher Task-Lauf
- Verhalten ohne Modell-Override
- Übersetzung von JSON-RPC-Fehlern
- Übersetzung von Busy-Fehlern
- Übersetzung unerwarteter Fehler

### `tests/test_monitoring_service.py`

Verantwortung:
Prüft Live-Laufzeitstatus, Event-Historie und Fehlerbehandlung des Monitoring-Subsystems.

### `tests/test_monitoring_api.py`

Verantwortung:
Prüft direkte Admin-Snapshot-/SSE-Endpunktlogik und Monitoring-spezifische Helper.

### `tests/test_monitor_live.py`

Verantwortung:
Prüft Shell-TUI-Helfer wie Filter, Header-Building, SSE-Parsing und Stream-Fehlerpfade.

### `tests/test_dependencies.py`

Verantwortung:
Prüft FastAPI-Dependency-Wiring, Principal-Caching und Monitoring-Injektion.

### `tests/test_app_factory.py`

Verantwortung:
Prüft App-Factory-Wiring, veröffentlichte Routen und Erzeugung des Monitoring-Singletons.

### `tests/test_health.py`

Verantwortung:
Prüft die Liveness- und Readiness-Logik unabhängig vom HTTP-Transport.

### `tests/test_auth.py`

Verantwortung:
Prüft Auth-Modi, Gruppenmapping und rollenbasierte Zugriffskontrolle.

Wichtige Testfälle:
- lokaler `disabled`-Modus
- `trusted_header` mit und ohne Benutzerheader
- Rollenmapping aus Gruppen
- OIDC-Pfad mit gepatchter Token-Dekodierung

### `tests/test_config.py`

Verantwortung:
Prüft Profilauflösung und gezielte Umgebungsvariablen-Overrides.

### `tests/support.py`

Verantwortung:
Stellt wiederverwendbare Testfabriken für Settings und Principals bereit.

## Dokumentation

### `README.md`

Verantwortung:
Einführung, Betrieb, Setup und Nutzung aus Sicht von Anwendern und Integratoren.

### `docs/DEVELOPER_GUIDE.de.md`

Verantwortung:
Beschreibt Architektur, Schichten, Request-Flow, Erweiterungspunkte und Enterprise-Lücken.

### `docs/FILE_REFERENCE.de.md`

Verantwortung:
Bietet die genaue Dateidokumentation für Wartung, Onboarding und Code-Reviews.
