## Purpose

The user-interface capability is the Encefalus web app. It is the welcome
screen, Home, and the product screens. A screen that shows product data
SHALL render the API Router JSON for that screen. It SHALL NOT call a
service port and SHALL NOT compute a correlation, a decision tree, or a
shield verdict in the browser.

## ADDED Requirements

### Requirement: Welcome before the product

The web app SHALL show the welcome screen when `sessionStorage` has no
access token. Sign-up SHALL call `POST /api/auth/signup` with name, email,
password, and `plan` equal to `"free"`. Sign-in SHALL call
`POST /api/auth/signin` with email and password. A successful response
SHALL store the access token and the returned user. The welcome screen
SHALL NOT offer Apple or Google sign-in. It SHALL NOT call any other
`/api` route.

#### Scenario: No token

- **GIVEN** no access token in the client
- **WHEN** the web app opens
- **THEN** only the welcome screen is shown and the only `/api` calls it can make are sign-up and sign-in

#### Scenario: Sign-up creates a free account

- **GIVEN** the welcome screen in sign-up mode
- **WHEN** the person submits a name, email, and matching passwords
- **THEN** the app calls `POST /api/auth/signup` with `plan` equal to `"free"` and, on HTTP 201, opens the product shell

#### Scenario: Sign-in opens the shell

- **GIVEN** an existing account
- **WHEN** sign-in returns HTTP 200 with `access_token` and `user`
- **THEN** the product shell replaces the welcome screen

### Requirement: Home and navigation

Home SHALL be served at `/` and SHALL NOT call the API. The Encefalus mark
SHALL link to `/`. The sidebar SHALL link to `/brain`, `/memory`,
`/decisions`, `/analytics`, `/shield`, `/learning`, and `/settings`.
The interface SHALL be in English.

#### Scenario: Home has no backend call

- **GIVEN** a signed-in user
- **WHEN** they open `/`
- **THEN** the six product entries are shown and no `/api` request is made for that screen

#### Scenario: The mark returns home

- **GIVEN** a signed-in user on a product screen
- **WHEN** they activate the Encefalus mark
- **THEN** the app navigates to `/`

### Requirement: Free plan is Brain and Settings

On the free plan the app SHALL allow Brain and Settings. Memory, Decisions,
Analytics, Shield, and Learning SHALL show an English notice that the
screen is on the Premium plan and SHALL NOT present that module's data.
Brain on the free plan SHALL send `use_rag` false and SHALL NOT load or
save calendar notes.

#### Scenario: Free user opens Memory

- **GIVEN** a signed-in user whose plan is `"free"`
- **WHEN** they open `/memory`, `/decisions`, `/analytics`, `/shield`, or `/learning`
- **THEN** the screen shows the premium notice and does not render that module's list, chart, or result

#### Scenario: Free Brain chat

- **GIVEN** a signed-in free user on `/brain`
- **WHEN** they send a question
- **THEN** the app calls `POST /api/chat` with `use_rag` false and does not call `GET /api/calendar` or `PUT /api/calendar/{day}`

### Requirement: Brain is the chat

Brain SHALL list chats with `GET /api/chats`, load a chat with
`GET /api/chats/{id}/turns`, create a chat with `POST /api/chats`, and
send a question with `POST /api/chat` including `session_id` set to that
chat id. One question SHALL accept at most five attachments, each as
`filename` and `content_base64`. A premium user SHALL be able to load and
save calendar notes with `GET /api/calendar` and `PUT /api/calendar/{day}`.

#### Scenario: Reopening a chat shows its turns

- **GIVEN** a chat that already has turns
- **WHEN** the user opens that chat
- **THEN** the app calls `GET /api/chats/{id}/turns` and renders each returned turn's role and text

#### Scenario: A question can carry five files

- **GIVEN** a chat and five chosen files
- **WHEN** the user sends the question
- **THEN** `POST /api/chat` includes an `attachments` array of length 5 and the chat id as `session_id`

#### Scenario: A sixth file is refused in the composer

- **GIVEN** five files already chosen for the current question
- **WHEN** the user picks another file
- **THEN** the composer rejects it and does not send six attachments

### Requirement: Memory, Decisions, Shield, and Learning use their routes

Memory SHALL list and search with `GET /api/documents` and
`GET /api/documents/search`, and upload with `POST /api/upload`.
Decisions SHALL list past runs with `GET /api/simulations` and start a
run with `POST /api/simulate`. Opening a past run SHALL restore that
item's question, scenarios, assumptions, and sources without a second
fetch. Shield SHALL list `GET /api/shield/incidents` and scan with
`POST /api/shield/scan`, and SHALL show the returned summary, severity,
rationale, and reasons. Learning SHALL load `GET /api/learning` and,
when the batch status is ready, post `{batch_id}` to `POST /api/finetune`.
These four screens SHALL be premium-only in the interface.

#### Scenario: Decisions lists past runs

- **GIVEN** a premium user with stored simulations
- **WHEN** they open `/decisions`
- **THEN** the past-runs panel lists `GET /api/simulations`, and choosing one shows that run's question and scenarios

#### Scenario: Empty decisions history

- **GIVEN** a premium user and `GET /api/simulations` returns an empty list
- **WHEN** they open `/decisions`
- **THEN** the panel shows an English empty state and does not error

#### Scenario: Shield shows evidence from the scan

- **GIVEN** a premium user
- **WHEN** `POST /api/shield/scan` returns HTTP 200
- **THEN** the detail panel shows that response's severity, summary, and reasons

### Requirement: Analytics screen plots server correlations

The Analytics screen SHALL render two scatters, sleep hours against
productivity and meeting hours against focus hours, using
`GET /api/analytics/correlations`. Each pair SHALL display `r` and `n`
from that payload. A pair with `status` equal to `"insufficient"` SHALL
show an English insufficient-data message and SHALL NOT display a numeric
`r`. The reading panel SHALL show the `narrative` from that payload.
The days table SHALL use `GET /api/analytics/metrics`. An upload of
`.csv`, `.xlsx`, `.docx`, `.ics`, or an image SHALL call
`POST /api/analytics/ingest` and then refresh correlations and metrics.
The screen SHALL NOT compute Pearson or the narrative.

#### Scenario: Charts with enough points

- **GIVEN** a premium user and correlations with `status` equal to `"ok"` and `n` ≥ 2
- **WHEN** the Analytics screen loads
- **THEN** both scatters plot the returned `points` and show the numeric `r` and `n` from the payload

#### Scenario: Insufficient data is explicit

- **GIVEN** a pair with `status` equal to `"insufficient"`
- **WHEN** the Analytics screen loads
- **THEN** that pair shows an English insufficient-data message and does not display a numeric `r`

#### Scenario: Ingest from the screen

- **GIVEN** a premium user on Analytics
- **WHEN** they upload a `.csv`, `.xlsx`, `.docx`, `.ics`, or image
- **THEN** the app calls `POST /api/analytics/ingest` and refreshes the scatters from `GET /api/analytics/correlations`

### Requirement: Settings is the account screen

Settings SHALL load `GET /api/account`, `GET /api/status`, and
`GET /api/storage`. The status panel SHALL show the six service rows the
router returns (LLM core, Memory retrieval, Personal model, Analytics,
Agents, Shield). Changing the plan SHALL call `PATCH /api/account` and
store the new session. Delete all data SHALL call `DELETE /api/data`.
Log out SHALL clear the token and the account and return to the welcome
screen. Settings SHALL remain available on the free plan.

#### Scenario: Service rows come from status

- **GIVEN** a signed-in user and `GET /api/status` returns `services`
- **WHEN** Settings loads
- **THEN** each returned service is shown with its label and online or offline state

#### Scenario: Log out

- **GIVEN** a signed-in user
- **WHEN** they log out
- **THEN** the token and the account are removed and the welcome screen is shown
