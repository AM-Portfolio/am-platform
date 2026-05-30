# Runtime logs (git-ignored)

npm scripts write timestamped logs here via `automation/scripts/run-with-logs.js`.

Layout:

```text
logs/
├── platform/     # root npm scripts (build:all, ci, …)
├── identity/     # am-identity
├── automation/   # terraform, helm, compose
├── common/       # am-platform-common
└── security/     # am-platform-security
```

Clean old logs: `npm run logs:clean`
