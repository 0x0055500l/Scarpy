import asyncio

from app.agent.browser import BrowserService


async def main():
    service = BrowserService(task_id="test_task", session_id="test_session")
    print("Starting service...")
    await service.start()
    print("Started!")
    await service.new_context()
    print("Context created!")
    await service.stop()
    print("Stopped!")

if __name__ == "__main__":
    asyncio.run(main())
