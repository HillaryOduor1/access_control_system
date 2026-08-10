from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import auth, users, employees, visitors, access_logs, sync,password_reset

app = FastAPI(title="ICTA Access Control API", version="1.0.0")

# CORS for desktop app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your desktop app's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth")
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(visitors.router)
app.include_router(access_logs.router)
app.include_router(sync.router)
app.include_router(password_reset.router)

@app.get("/")
async def root():
    return {"message": "ICTA Access Control API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}