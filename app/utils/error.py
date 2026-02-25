from fastapi import HTTPException
from loguru import logger
import uuid
from pydantic import BaseModel
from typing import Type, Any
import numpy as np


def handle_validation_error(model: Type[BaseModel], **kwargs: Any) -> None:
    try:
        model(**kwargs)
    except Exception as e:
        uid = uuid.uuid4()
        logger.error("Invalid request format: {}, - Error UUID : {}".format(e, uid))
        raise HTTPException(
            status_code=400,
            detail="Invalid request format. Contact the support giving them the following error code {}".format(
                uid
            ),
        )


def handle_processing_error(e, status_code=500, details="An error occured"):
    uid = uuid.uuid4()
    logger.error(
        "An error occured: {}, - Error UUID : {} - {}-{}".format(
            e, uid, status_code, details
        )
    )

    HTTPException(
        status_code=status_code,
        detail="{} ({})".format(details, uid),
    )
