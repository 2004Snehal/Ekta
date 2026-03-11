# Backend
cd backend
pip install google-generativeai fastapi uvicorn psycopg2-binary python-dotenv
uvicorn api.main:app --reload

# Frontend
cd dashboard_2
npm install
npm run dev   # opens on :5174