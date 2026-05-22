# CineVault — PT LINKIT SRE Technical Test
**Candidate:** Aldiansyah Dwi Putra

## Project Structure
```
linkit-sre-test/
├── backend/
│   ├── src/
│   │   ├── app.py              # Flask app factory
│   │   ├── server.py           # Entry point
│   │   ├── models/
│   │   │   ├── user.py         # Master: users
│   │   │   └── movie.py        # Master: movies + Transactional: watchlist
│   │   ├── routes/
│   │   │   ├── auth.py         # POST /auth/login|register, GET /auth/me
│   │   │   ├── movies.py       # CRUD + /sync from SampleAPIs
│   │   │   ├── watchlist.py    # CRUD transactional entries
│   │   │   └── health.py       # /health, /metrics, /alerts
│   │   └── utils/
│   │       ├── logger.py       # Structured logging (app/transaction/error)
│   │       ├── alert_simulator.py  # In-memory alert simulation
│   │       └── response.py     # JSON response helpers
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html              # Single-file dashboard
│   └── Dockerfile
├── docs/
│   └── ANSWERS.md              # Section 1 & 2 written answers
├── docker-compose.yml
└── README.md
```

## Quick Start

```bash
# Docker
docker-compose up --build

# Local
cd backend && pip install -r requirements.txt
cd src && python server.py
# Open frontend/index.html in a browser

# Credentials: admin/admin123 · demo/demo123
```

## Endpoints
- Frontend: http://localhost:3000
- Backend:  http://localhost:5000
- Health:   http://localhost:5000/api/health
- Metrics:  http://localhost:5000/api/metrics
- Alerts:   http://localhost:5000/api/alerts
