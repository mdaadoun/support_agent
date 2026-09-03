"""Main service runner entrypoint for 8_support_agent."""

import uvicorn

from api.app import app, create_app
from core.config import get_settings

__all__ = ["app", "create_app"]

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.support_agent_env == "development",
    )
