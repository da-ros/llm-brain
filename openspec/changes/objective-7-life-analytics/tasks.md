## Tasks

### A. Project Setup

- [ ] A.1 Initialize React project with Vite + TypeScript
- [ ] A.2 Add dependencies: chart.js, react-chartjs-2, @tanstack/react-query, axios
- [ ] A.3 Set up project structure: `src/components/charts/`, `src/hooks/`, `src/api/`
- [ ] A.4 Configure ESLint + Prettier

### B. Data Layer

- [ ] B.1 Implement API client for analytics endpoints
- [ ] B.2 Implement React Query hooks: useAnalytics(), useCorrelation()
- [ ] B.3 Define TypeScript types for analytics data
- [ ] B.4 Add data normalization utilities

### C. Chart Components

- [ ] C.1 Implement LineChart component (time series: sleep, productivity over time)
- [ ] C.2 Implement BarChart component (comparisons: daily/weekly averages)
- [ ] C.3 Implement ScatterChart component (correlations: sleep vs productivity)
- [ ] C.4 Implement ChartContainer with loading/error states

### D. Dashboard Layout

- [ ] D.1 Implement responsive grid layout (CSS Grid)
- [ ] D.2 Implement date range selector (7/30/90 days)
- [ ] D.3 Implement metric selector (choose which metrics to display)
- [ ] D.4 Implement correlation selector (choose which correlations to view)

### E. Integration

- [ ] E.1 Wire dashboard to backend analytics API
- [ ] E.2 Add authentication guard (premium users only)
- [ ] E.3 Add responsive design (desktop, tablet, mobile)
- [ ] E.4 Add dark mode support (match web app theme)

### F. Testing

- [ ] F.1 Unit tests for chart components (render with mock data)
- [ ] F.2 Unit tests for data normalization
- [ ] F.3 Integration test: dashboard loads and displays charts
- [ ] F.4 Visual regression test: chart snapshots
