## Purpose

The life-analytics-web capability is the premium English React dashboard that
plots two interactive Chart.js correlations, shows Frame 6 simulation
history, and renders Frame 8 shield incidents with a safe empty state.

## ADDED Requirements

### Requirement: Premium login to the web dashboard

The web app SHALL require a valid JWT from the API Router login flow before
showing analytics. Free-tier tokens SHALL be refused with an English message.
Unauthenticated users SHALL see a login screen only.

#### Scenario: Premium user reaches the dashboard

- **GIVEN** a user with a valid premium JWT
- **WHEN** they open the web app
- **THEN** the dashboard shell is shown in English (sleep/productivity and meetings/focus sections visible)

#### Scenario: Free user is blocked

- **GIVEN** a valid free-tier JWT
- **WHEN** they open the web app
- **THEN** the app does not render correlation charts and shows that the dashboard is premium-only

#### Scenario: No token

- **GIVEN** no JWT in the client
- **WHEN** they open the web app
- **THEN** only a login form is shown and no analytics HTTP calls are made except login

### Requirement: Two interactive Chart.js correlations

The dashboard SHALL render two interactive Chart.js charts: sleep hours vs
productivity, and meeting hours vs focus hours, using `GET /api/analytics/correlations`.
Each chart SHALL display `r` and `n`. Insufficient samples SHALL still render
an empty or sparse chart with an English “insufficient data” label, not a fake r.

#### Scenario: Charts with enough points

- **GIVEN** correlations with `status` equal to `"ok"` and `n` ≥ 2
- **WHEN** the dashboard loads
- **THEN** both Chart.js charts plot the returned `points` and show the numeric `r` and `n`

#### Scenario: Insufficient data is explicit

- **GIVEN** a pair with `status` equal to `"insufficient"`
- **WHEN** the dashboard loads
- **THEN** that chart area shows an English insufficient-data message and does not display a numeric `r`

#### Scenario: Ingest from the UI

- **GIVEN** a premium user on the dashboard
- **WHEN** they upload a diary or schedule as `.csv`, `.xlsx`, `.docx`, `.ics`, or an image
- **THEN** the app calls `POST /api/analytics/ingest` and refreshes both charts and the insights panel from `GET /api/analytics/correlations`

### Requirement: LLM insights panel

The dashboard SHALL show the English narrative returned with correlations.
It SHALL NOT compute that narrative in the browser.

#### Scenario: Narrative is visible

- **GIVEN** correlations include a non-empty `narrative` and `llm_used` true
- **WHEN** the dashboard loads
- **THEN** the insights panel shows that narrative in English

### Requirement: Simulation history panel

The dashboard SHALL list the user's Frame 6 simulations via
`GET /api/simulations` and SHALL show scenario count plus the original
question. It SHALL NOT recompute the decision tree in the browser.

#### Scenario: History listed

- **GIVEN** a premium user with stored simulations
- **WHEN** the dashboard loads
- **THEN** the simulations panel lists those items with question and `scenario_count`

#### Scenario: Empty history

- **GIVEN** a premium user with no simulations
- **WHEN** the dashboard loads
- **THEN** the panel shows an English empty state and does not error

### Requirement: Shield incidents panel degrades safely

The dashboard SHALL call `GET /api/shield/incidents`. When the endpoint
returns incidents, they SHALL be listed. When it returns 404, 501, or a
network error (Frame 8 not applied yet), the panel SHALL show an English
empty/unavailable state and the rest of the dashboard SHALL still work.

#### Scenario: Incidents present

- **GIVEN** `GET /api/shield/incidents` returns HTTP 200 with items
- **WHEN** the dashboard loads
- **THEN** the incidents panel lists `severity` and `summary` for each item

#### Scenario: Shield not available

- **GIVEN** `GET /api/shield/incidents` fails with 404, 501, or network error
- **WHEN** the dashboard loads
- **THEN** the incidents panel shows an empty or unavailable English state and both correlation charts still render
