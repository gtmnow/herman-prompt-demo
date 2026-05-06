from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.routes import router
from app.core.config import settings
from app.db.session import initialize_database
from app.schema_contract import SchemaContractError


logger = logging.getLogger("herman_prompt.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        initialize_database()
    except SchemaContractError:
        logger.warning(
            "Schema contract validation failed during startup; continuing with shared DB ownership model.",
            exc_info=True,
        )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="HermanPrompt API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
