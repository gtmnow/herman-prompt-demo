# HermanPrompt

ChatGPT-like shell with Prompt Transformer in the middle.

## Structure

- `frontend/`: Vite + React + TypeScript UI
- `backend/`: FastAPI chat orchestration API
- `docs/`: product and technical specifications

## Local development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Example URL

```text
http://localhost:5173/?user_id_hash=user_1&theme=dark
```

## Local ports

- Frontend: `5173`
- HermanPrompt backend: `8002`
- Prompt Transformer: `8001`
