import asyncio
from bot import TelegramBot
from logger import logger


async def main():
    bot = TelegramBot()
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
