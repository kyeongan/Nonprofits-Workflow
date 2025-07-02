# Nonprofits Workflow Backend

This is a simple backend API implementation for the nonprofits workflow using FastAPI. It simulates a system for nonprofit grant communication and includes functionality to manage nonprofits and send templated emails.

## Features
- Create nonprofits (name, address, email)
- Bulk send templated emails to nonprofits
- Retrieve all sent emails
- In-memory data storage (no database required)
- Mocked email sending (no real emails sent)

## Quickstart

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the server
```bash
uvicorn main:app --reload
```

### 3. API Docs
Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive Swagger UI.

Redoc documentation is also available at [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

## 🔍 Preview

![Swagger UI](./docs/swagger-ui.png)

## API Endpoints
- `POST /nonprofits` — Create a nonprofit
```json
{
  "name": "Helping Hands",
  "address": "123 Aid St, NY",
  "email": "help@hands.org"
}
```
- `GET /nonprofits` — List all nonprofits
- `POST /send-email` — Send a templated email to nonprofits
```json
{
  "template": "Sending money to nonprofit {name} at address {address}",
  "emails": ["help@hands.org"]
}
```
- `GET /sent-emails` — List all sent emails

## Notes
- No authentication required
- Email is the unique identifier for nonprofits
- 5 sample nonprofits are preloaded at startup for testing


