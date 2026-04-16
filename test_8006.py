from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World from 8006"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)
