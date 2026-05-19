from fastapi import FastAPI
from app.routes.router import router as router

app = FastAPI()
app.include_router(router)
