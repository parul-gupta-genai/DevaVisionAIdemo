#!/bin/bash
# DevaVisionAI Local Run Script

echo "Installing Python dependencies..."
pip install fastapi uvicorn sqlalchemy pydantic loguru python-jose passlib python-multipart slowapi prometheus-client redis diskcache aiofiles opencv-python-headless pillow numpy scikit-learn joblib alembic httpx python-dotenv psutil bcrypt

echo "Installing Node dependencies & building frontend..."
cd frontend && npm install && npm run build && cd ..

echo "Starting DevaVisionAI..."
cd backend
python -m uvicorn mini_backend:app --host 0.0.0.0 --port 8000
