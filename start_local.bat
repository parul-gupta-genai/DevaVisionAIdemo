@echo off
echo Installing Python dependencies...
pip install fastapi uvicorn sqlalchemy pydantic loguru python-jose passlib python-multipart slowapi prometheus-client redis diskcache aiofiles opencv-python-headless pillow numpy scikit-learn joblib

echo Building frontend...
cd frontend
call npm install
call npm run build
cd ..

echo Starting DevaVisionAI...
cd backend
set PYTHONPATH=%CD%
python -m uvicorn mini_backend:app --host 127.0.0.1 --port 8000
pause
