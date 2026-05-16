# Entwicklerdokumentation

## Ziel des Systems

Die Anwendung stellt eine versionierte REST-API auf Basis von FastAPI bereit, die natürlichsprachige Aufgaben annimmt und diese über das OpenAI-Codex-App-Server-SDK an eine lokale oder konfigurierte Codex-Laufzeit weiterleitet.

Die Reorganisation verfolgt vier Enterprise-Ziele:

1. Trennung von HTTP-Schicht, Service-Schicht, Konfiguration und Schemas.
2. Stabilere Betriebsfähigkeit durch Health-Endpunkte, strukturierte Fehler und Request-Korrelation.
3. Wartbarkeit durch klar benannte Module und dokumentierte Erweiterungspunkte.
4. Erweiterbarkeit für spätere Multiuser-, Security- und Governance-Anforderungen.

## Architekturüberblick

### Schichten

- `app/main.py`: Application Factory, Middleware, CORS und Bootstrapping.
- `app/api/`: Router, Dependency Injection und globale Fehlerabbildung.
- `app/services/`: Geschäftslogik und Integration mit der Codex-Laufzeit.
- `app/security/`: Authentifizierung, Rollenauflösung und Benutzerkontext.
- `app/schemas/`: Eingabe-, Ausgabe-, Error- und Health-Verträge.
- `app/core/`: Konfiguration, Logging, Request-Kontext und Domänenfehler.
- `config/`: profilgesteuerte Laufzeitkonfiguration über TOML.
- `tests/`: Schichtenspezifische Unit- und Endpoint-Tests.
- `docs/`: Betriebs- und Entwicklerdokumentation.

### Request-Flow

1. Ein HTTP-Request erreicht FastAPI.
2. Die Middleware erzeugt oder übernimmt `X-Request-ID`.
3. Die Request-ID wird im Request-State und im Logging-Kontext gespeichert.
4. Der Router validiert das Payload gegen `TaskExecutionRequest`.
5. Für geschützte Endpunkte wird das Benutzerprofil über den konfigurierten Auth-Modus aufgelöst.
6. Das Monitoring registriert Request- und Principal-Ereignisse im prozessweiten Laufzeitstatus.
7. Optional wird die Rollenprüfung gegen die profilgesteuerte Autorisierungskonfiguration ausgeführt.
8. Der Endpoint delegiert an `CodexExecutionService`.
9. Der Service meldet Task-Start, Workspace-Nutzung, Abschluss oder Fehler an `MonitoringService`.
10. Der Service startet die Codex-Laufzeit, führt den Task aus und übersetzt Laufzeitfehler in Domänenfehler.
11. Globale Exception-Handler erzeugen bei Bedarf ein strukturiertes Error-Response.
12. Die Response liefert Ergebnis, Metadaten und Header wie `X-Request-ID`.

## Laufzeitkonfiguration

Die Anwendung liest Konfiguration zentral über `app/core/config.py` und standardmäßig aus `config/app.toml`.

### Profilmodell

Die Konfiguration wird in vier Schritten aufgelöst:

1. interne sichere Defaults
2. Werte aus `config/app.toml`
3. aktives Profil aus `active_profile` oder `APP_ACTIVE_PROFILE`
4. Umgebungsvariablen als gezielte Overrides

Die mitgelieferten Profile sind:

- `home`: lokale Entwicklung ohne Authentifizierung
- `company`: Unternehmensmodus mit vorbereiteter SSO- und Rollenlogik

### Wichtige Umgebungsvariablen

- `APP_ENV`: Laufzeitumgebung, z. B. `development`, `test`, `production`.
- `API_PREFIX`: Basispräfix der versionierten API, Standard `/api/v1`.
- `ENABLE_DOCS`: `1` aktiviert Swagger/ReDoc, `0` deaktiviert API-Dokumentation.
- `LOG_LEVEL`: Logging-Level, Standard `INFO`.
- `CORS_ALLOWED_ORIGINS`: Kommagetrennte Origins, Standard `http://localhost,http://127.0.0.1`.
- `CODEX_BIN`: Optionaler Pfad zur Codex-Binärdatei.
- `CODEX_MODEL`: Optionales Modell-Override. Ohne Wert wird das lokale Codex-Default genutzt.
- `APP_CONFIG_FILE`: Optionaler Pfad auf eine alternative TOML-Datei.
- `APP_ACTIVE_PROFILE`: Erzwingt ein bestimmtes Konfigurationsprofil.
- `AUTH_MODE`: Überschreibt den Auth-Modus des aktiven Profils.
- `AUTHORIZATION_ENABLED`: Schaltet Rollenprüfung an oder aus.
- `AUDIT_ENABLED`: Schaltet Audit-Events im Logging an oder aus.
- `MONITORING_ENABLED`: Aktiviert oder deaktiviert das Live-Monitoring.
- `MONITORING_HISTORY_SIZE`: Anzahl zuletzt abgeschlossener Tasks im In-Memory-Verlauf.
- `MONITORING_STREAM_ENABLED`: Aktiviert den SSE-Stream für Live-Events.
- `MONITORING_REFRESH_INTERVAL_MS`: Empfohlenes Refresh-Intervall für Terminal-Clients.
- `HOST`, `PORT`, `UVICORN_LOG_LEVEL`, `UVICORN_RELOAD`: werden vom Startskript ausgewertet.

### Auth-Modi

- `disabled`
  Zweck:
  Entwicklungsmodus ohne Login. Die Anwendung erzeugt einen deterministischen lokalen Principal `local-development`.

- `trusted_header`
  Zweck:
  Geeignet für Windows-SSO hinter IIS, Reverse Proxy oder API-Gateway. Die API vertraut konfigurierten Benutzer-Headern nur innerhalb des vorgesehenen Netzwerkpfads.

- `oidc_jwt`
  Zweck:
  Geeignet für moderne Unternehmens-SSO-Architekturen mit Bearer-Token, z. B. Microsoft Entra ID über OpenID Connect.

### Rollenauflösung

Phase 1 liefert eine konfigurierbare Rollenbasis:

- Gruppen `Codex-Admins` werden zu Rolle `admin`
- Gruppen `Codex-Users` werden zu Rolle `user`
- Gruppen `Codex-Readonly` werden zu Rolle `readonly`

Die konkrete Zuordnung kommt aus dem aktiven Profil und kann später tenant-spezifisch erweitert werden.

## API-Oberfläche

### Fachliche Endpunkte

- `POST /api/v1/execute_task`
  Zweck:
  Führt einen einzelnen Task über die Codex-Laufzeit aus.

### Betriebsendpunkte

- `GET /api/v1/health/live`
  Zweck:
  Liveness-Probe für Prozessüberwachung.

- `GET /api/v1/health/ready`
  Zweck:
  Readiness-Probe mit einfacher Prüfung der Codex-Laufzeit-Konfiguration.

- `GET /api/v1/monitoring/snapshot`
  Zweck:
  Liefert den aktuellen Live-Snapshot mit aktiven Tasks, Sessions, Workspaces und Kurz-Historie.

- `GET /api/v1/monitoring/events`
  Zweck:
  Streamt Laufzeitereignisse im SSE-Format für die Shell-TUI oder andere Admin-Clients.

## Fehlerkonzept

Die API verwendet ein stabiles Fehlerformat:

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

### Fehlerquellen

- Validierungsfehler des HTTP-Payloads.
- Domänenfehler aus der Service-Schicht.
- Authentifizierungs- oder Autorisierungsfehler aus der Security-Schicht.
- Unerwartete interne Fehler.
- Überlastete oder fehlerhafte Codex-Laufzeit.

## Observability und Betrieb

### Bereits umgesetzt

- Request-Korrelation über `X-Request-ID`.
- Einheitliches Logging mit `request_id`.
- Health-Endpunkte für Orchestrierung.
- Strukturierte Responses für Fehlerfälle.
- Audit-Grundlage mit actor-bezogenen Log-Events bei geschützten Task-Ausführungen.
- Readiness-Sicht auf den konfigurierten Auth-Modus.
- Integriertes Live-Monitoring für Administratoren mit In-Memory-Status je Request, Task und Session.
- Shell-TUI `monitor_live.py` für Snapshot-Ansicht, Live-Events und Filter auf Benutzer/Session/Fehler.

### Monitoring-Architektur

- `MonitoringService` ist ein prozessweites Singleton in `app.state`.
- Das Monitoring hält nur Kurz-Historie im Speicher, keine Langzeit-Persistenz.
- Tracking-Ereignisse umfassen u. a. `request_started`, `principal_resolved`, `task_started`, `workspace_created`, `workspace_reused`, `task_completed`, `task_failed`.
- Monitoring-Endpunkte sind in produktiven Auth-Modi nur für Rolle `admin` freigegeben.
- Die TUI liest Snapshots über HTTP und optional Live-Events über `text/event-stream`.

### Empfohlene nächste Ausbaustufen

- Export von Metriken für Prometheus/OpenTelemetry.
- Zentrales Audit-Logging für Benutzeraktionen.
- Trace-Weitergabe an externe Monitoring-Plattformen.

## Teststrategie

Die Tests sind bewusst schichtennah aufgebaut:

- `tests/test_auth.py`: Auth-Modi und Rollenlogik.
- `tests/test_monitoring_service.py`: Laufzeitstatus, Event-Historie und Fehlerpfade des Monitorings.
- `tests/test_monitoring_api.py`: Admin-Snapshot, SSE-Streaming und Monitoring-Endpoint-Helfer.
- `tests/test_monitor_live.py`: Terminal-Filter, Header-Building, SSE-Parsing und Stream-Fehler.
- `tests/test_dependencies.py`: FastAPI-Dependency-Wiring und Principal-Caching.
- `tests/test_app_factory.py`: App-Factory, veröffentlichte Routen und Monitoring-Singleton.
- `tests/test_codex_service.py`: Kernlogik und Fehlerübersetzung.
- `tests/test_codex.py`: Endpoint-Vertrag und Delegation.
- `tests/test_config.py`: Profilauflösung und Overrides.
- `tests/test_health.py`: Betriebsendpunkte.
- `tests/support.py`: gemeinsame Testfabriken für Settings und Principals.

Diese Strategie vermeidet die bekannte Inkompatibilität von `TestClient` in der aktuellen lokalen Toolchain und hält die Tests trotzdem deterministisch.

## Erweiterungspunkte

### Neue API-Version

1. Neues Paket unter `app/api/v2/` anlegen.
2. Router analog zu `app/api/v1/router.py` aufbauen.
3. In `app/api/router.py` registrieren.

### Neue Services

1. Fachlogik im Paket `app/services/` ergänzen.
2. Neue Dependencies in `app/api/dependencies.py` bereitstellen.
3. Eigene Schemas in `app/schemas/` definieren.

### Neue Security-Modi

1. Erweiterung in `app/security/authentication.py` ergänzen.
2. Neues Settings-Segment in `app/core/config.py` definieren.
3. Konfiguration in `config/app.toml` dokumentieren.

### Neue Fehlerklassen

1. Neue Domänenfehler in `app/core/exceptions.py` ergänzen.
2. Bestehenden Handler weiterverwenden, solange `ApplicationError` erweitert wird.

## Fehlende Enterprise-Funktionalitäten für Multiuser-Betrieb

Die Anwendung ist jetzt sauber strukturiert, aber noch kein vollständiges Unternehmensprodukt. Für einen echten Multiuser-Einsatz fehlen insbesondere:

### Identity, Access und Mandantenfähigkeit

- Vollständige OIDC-Produktivverdrahtung mit echter IdP-Registrierung, Secret-/Zertifikatsmanagement und Betriebsdokumentation.
- Erweiterbares Rollen- und Rechtemodell pro Benutzer, Team, Tenant und Anwendungsfall.
- Mandantenfähigkeit oder Workspace-Isolation.
- Durchsetzung von Least-Privilege und Policy-basierten Freigaben.

### Persistenz und Nachvollziehbarkeit

- Datenbank für Benutzer, Sessions, Tasks, Ergebnisse, Audit-Trails und Policies.
- Versionierung und Historisierung von Ausführungen.
- Reproduzierbarkeit von Läufen mit gespeicherten Metadaten.
- Lösch- und Aufbewahrungsrichtlinien nach Compliance-Vorgaben.

### Sicherheit und Governance

- Sichere Prompt- und Tool-Governance.
- Inhaltsfilter, DLP-Regeln und Geheimniserkennung.
- Genehmigungsworkflows für riskante Aktionen.
- Secret-Management statt direkter Umgebungsvariablen in allen Umgebungen.
- Sicherheitsgrenzen für Dateisystem, Netzwerk und Prozessrechte je Benutzerkontext.

### Skalierung und Ressourcensteuerung

- Request-Queuing, Concurrency Limits und Priorisierung.
- Worker-Pool oder Job-System für lange Ausführungen.
- Rate Limiting pro Benutzer, Tenant und API-Key.
- Horizontale Skalierung mit zustandsloser API-Schicht.

### Betriebsreife

- Container- und Deployment-Artefakte.
- CI/CD-Pipelines mit Test-, Security- und Release-Stufen.
- Infrastruktur-as-Code.
- SLOs, Alarme, Dashboards und Fehlerbudgets.

### Integrationsfähigkeit

- API-Key- oder Token-basierte Maschinen-zu-Maschinen-Nutzung.
- Webhooks oder Eventing für asynchrone Ergebnisse.
- Asynchrone Job-API mit Statusabfrage.
- Admin-Endpunkte für Betriebs- und Policy-Konfiguration.
