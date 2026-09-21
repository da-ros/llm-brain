## ADDED Requirements

### Requirement: Message scan form and popup alert

The web app SHALL provide an English form to paste email, SMS, or message
text and/or attach an image or short video, then submit
`POST /api/shield/scan`. When the response has `alert` equal to true, the
UI SHALL show a popup (modal or equivalent) with `severity`, `summary`,
`likelihood`, and `reasons`. When `alert` is false, the UI SHALL not show
a threat popup. The form MAY live on a minimal Shield page if the Frame 7
dashboard shell is not present yet.

#### Scenario: Alert popup on phishing

- **GIVEN** a premium JWT and a scan response with `alert` true
- **WHEN** the user submits the scan form
- **THEN** a popup is shown with severity, summary, and at least one reason, in English

#### Scenario: No popup on ham

- **GIVEN** a premium JWT and a scan response with `alert` false
- **WHEN** the user submits the scan form
- **THEN** the UI does not show a threat popup and may show a short English “no threat detected” status

#### Scenario: Free token cannot scan in the UI

- **GIVEN** a free-tier JWT
- **WHEN** the user opens the Shield scan UI
- **THEN** the form is not submitted to `/api/shield/scan` and an English premium-only message is shown

### Requirement: Incidents list uses the Frame 7 contract

The web app SHALL load `GET /api/shield/incidents` and render
`severity` and `summary` for each item. An empty `incidents` array SHALL
show an English empty state, not an error.

#### Scenario: Incidents listed after an alert

- **GIVEN** a premium user who just received an alert that was persisted
- **WHEN** the incidents list refreshes
- **THEN** the new item appears with `severity` and `summary`

#### Scenario: Empty incidents

- **GIVEN** a premium user with `incidents` equal to `[]`
- **WHEN** the list loads
- **THEN** an English empty state is shown and the scan form remains usable
