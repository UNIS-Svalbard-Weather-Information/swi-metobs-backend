from fastapi import HTTPException
from loguru import logger
import uuid
from pydantic import BaseModel
from typing import Type, Any


def handle_validation_error(model: Type[BaseModel], **kwargs: Any) -> None:
    try:
        model(**kwargs)
    except Exception as e:
        uid = uuid.uuid4()
        logger.error("Invalid request format: {}, - Error UUID : {}".format(e, uid))
        raise HTTPException(
            status_code=400,
            detail="Invalid request format. Contact the support giving them the following error code {}".format(uid),
        )
