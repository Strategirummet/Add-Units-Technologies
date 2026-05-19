import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.app:app",  # module_name:fastapi_instance
        host="0.0.0.0",
        port=8000,
        reload=True
    )