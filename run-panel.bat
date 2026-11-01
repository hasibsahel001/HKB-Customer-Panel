@echo off
cd /d "%~dp0"
if not exist frontend\dist\index.html (
  echo Building the frontend for the first time...
  pushd frontend
  call npm install
  call npm run build
  popd
)
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause