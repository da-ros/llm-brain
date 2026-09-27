# Web dashboard

Frame 7 (React + Chart.js) is not in this tree yet.

The minimal Shield page is `shield/index.html` (`/shield/`). It posts to
`POST /api/shield/scan`, shows a threat popup when `alert` is true, and
lists `GET /api/shield/incidents`. A free-tier token never submits the form.
