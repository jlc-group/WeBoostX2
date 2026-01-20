"""
Run the WeBoostX 2.0 application
"""
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8201,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )

