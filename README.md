# CineVault — PT LINKIT SRE Technical Test

**Candidate:** Aldiansyah Dwi Putra

## Project Structure

```
linkit-sre-test/
├── section-1-observability/
│   └── ANSWERS.md              # Root causes, alert rules, improvements
├── section-2-infrastructure/
│   └── ANSWERS.md              # Step-by-step troubleshooting with commands
├── section-3-cinevault/
│   ├── backend/
│   │   ├── src/
│   │   │   ├── server.js           # Entry point
│   │   │   ├── app.js              # Express app factory
│   │   │   ├── models/
│   │   │   │   ├── user.js         # Master: users
│   │   │   │   └── movie.js        # Master: movies + Transactional: watchlist
│   │   │   ├── routes/
│   │   │   │   ├── auth.js         # POST /auth/login|register, GET /auth/me
│   │   │   │   ├── movies.js       # CRUD + /sync from SampleAPIs
│   │   │   │   ├── watchlist.js    # CRUD transactional entries
│   │   │   │   └── health.js       # /health, /metrics, /alerts
│   │   │   └── utils/
│   │   │       ├── logger.js       # Structured logging (app/transaction/error)
│   │   │       ├── alertSimulator.js  # In-memory alert simulation
│   │   │       └── response.js     # JSON response helpers
│   │   ├── package.json
│   │   └── Dockerfile
│   ├── frontend/
│   │   ├── index.html              # Single-file dashboard
│   │   └── Dockerfile
│   ├── docker-compose.yml
└── README.md                       # Root overview linking all 3 sections
```

## Quick Start

```bash
# Please use docker-compose to make sure the apps run properly
# Docker
cd section-3-mini-app && docker-compose up --build

# Local
cd section-3-mini-app/backend && pip install -r requirements.txt
cd src && python server.py
# Open frontend/index.html in a browser

# Credentials: admin/admin123 · demo/demo123
```

## Endpoints

- Frontend: http://127.0.0.1:3000
- Backend: http://localhost:8383
- Health: http://localhost:8383/api/health
- Metrics: http://localhost:8383/api/metrics
- Alerts: http://localhost:8383/api/alerts
