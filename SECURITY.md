# Security and privacy

Run this service only on your own device. The HTTP server binds to loopback, validates Host and Origin, and requires an in-memory CSRF token for annotations. It is not designed as an authenticated multi-user or internet-facing service. Do not forward its port publicly.

Usage records, chat titles, project names and annotations are private. Never attach unredacted session logs, SQLite databases, CSV exports, credentials or real-data screenshots to public issues.

Report vulnerabilities privately through GitHub's private vulnerability reporting when enabled. If unavailable, open an issue asking for a private reporting channel without including exploit details or private data.

The optional inline customization enables a temporary local debugging port after an explicit launcher confirmation. It depends on internal UI structures, is not necessary for the dashboard, and should not be used to bypass any host automation restriction.
