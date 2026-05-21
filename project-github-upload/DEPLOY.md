# Cloud deployment

This project is configured for container-based deployment. The container builds the Vite frontend, copies `frontend/dist` into the Python runtime image, and serves it from FastAPI at `/frontend/index.html`.

## Local container test

```bash
docker build -t hallym-track-diagnosis .
docker run --rm -p 8000:8000 -e PORT=8000 hallym-track-diagnosis
```

Open:

- App: `http://localhost:8000/`
- App direct path: `http://localhost:8000/frontend/index.html`
- Health check: `http://localhost:8000/api/v1/health`
- API docs: `http://localhost:8000/docs`

## Cloud settings

Use the repository root as the build context and `Dockerfile` as the Dockerfile path.

Recommended service settings:

- Service type: Web service / container
- Port: use the platform-provided `PORT` environment variable
- Health check path: `/api/v1/health`

Recommended environment variables:

```text
DEBUG_MODE=0
SERVER_RELOAD=0
TRACK_DATA_SOURCE=db
OCR_MODE=mock
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

The app now runs from PostgreSQL only. Before starting the service, apply
`backend/data/schema.sql` to the database and run
`backend/scripts/migrate_json_to_db.py` once to import the current track rules.

For real OCR in the deployed container, set:

```text
OCR_MODE=tesseract
OCR_TESSERACT_LANGS=kor+eng
```

If the frontend is hosted separately from the API, also set `CORS_ORIGINS` to the exact frontend origin, for example:

```text
CORS_ORIGINS=https://your-frontend.example.com
```
