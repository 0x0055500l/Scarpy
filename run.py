import sys
import asyncio
import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        # Required for Playwright/Stagehand to spawn subprocesses on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
