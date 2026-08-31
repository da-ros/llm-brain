## Context

The Life Analytics dashboard is a React web application that visualizes correlations
between user data points. It uses Chart.js for rendering and connects to the backend
API for data retrieval.

## Goals / Non-Goals

**Goals:**
- React SPA with Chart.js integration
- >=2 interactive correlations (sleep/productivity, health/focus)
- Responsive layout (desktop-first)
- Data fetching from backend API
- Interactive filters (date range, metric selection)

**Non-Goals:**
- Real-time streaming charts
- Custom chart types
- Data export
- Mobile app dashboard

## Architecture Decisions

### 1. Framework: React (not Next.js, not Vue)

**Decision**: React with Create React App (CRA) or Vite.

**Rationale**:
- Consistent with web app stack
- Chart.js has excellent React bindings
- Simple deployment (static files)
- Team familiarity

### 2. Charting: Chart.js (not D3, not Recharts)

**Decision**: Chart.js via react-chartjs-2.

**Rationale**:
- Thesis specifies Chart.js
- Simple API for common chart types
- Good performance for data volumes
- Responsive by default

### 3. State Management: React Query (TanStack Query)

**Decision**: React Query for server state management.

**Rationale**:
- Automatic caching and refetching
- Loading/error states built-in
- Optimistic updates for mutations
- Pairs well with REST API

### 4. Layout: CSS Grid + Flexbox

**Decision**: CSS Grid for dashboard layout, Flexbox for components.

**Rationale**:
- No CSS framework dependency (lightweight)
- Responsive without media queries (grid auto-fit)
- Customizable for thesis presentation

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Chart.js performance with large datasets | Downsample data, virtual scrolling |
| Responsive design complexity | Mobile-first breakpoints, test on devices |
| Data format inconsistency | Normalize data before chart rendering |
| Browser compatibility | Target modern browsers (Chrome, Firefox, Safari) |

## Decisions Made

- Chart types: Line (time series), Bar (comparisons), Scatter (correlations)
- Date range: last 7/30/90 days (configurable)
- Correlations: sleep-productivity, health-focus, document-frequency
- API endpoint: GET /api/analytics/{user_id}
- Export: not in scope (future)
