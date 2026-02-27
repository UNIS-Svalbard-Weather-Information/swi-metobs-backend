from fastapi import APIRouter, Response, status, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import json
from app.api.v3.endpoints._health_config import (
    HEALTH_CHECK_PATHS,
    CRITICAL_PATHS,
    OPTIONAL_PATHS,
)

router = APIRouter()


def check_paths(paths_to_check: list) -> dict:
    """
    Check if specified data paths are accessible.
    Returns a dictionary with path status information.
    """
    status_info = {}
    all_healthy = True

    for name in paths_to_check:
        if name not in HEALTH_CHECK_PATHS:
            logger.error("Missing file path for {}".format(name))
            continue

        path = HEALTH_CHECK_PATHS[name]
        try:
            if path.suffix == ".json":
                # For JSON files, try to read them
                with open(path, "r") as f:
                    json.load(f)  # Validate JSON
                status_info[name] = {"status": "healthy", "path": str(path)}
            else:
                # For directories, check if they exist and are accessible
                if path.exists() and path.is_dir():
                    status_info[name] = {"status": "healthy", "path": str(path)}
                else:
                    status_info[name] = {
                        "status": "unhealthy",
                        "path": str(path),
                        "error": "Directory not found or inaccessible",
                    }
                    all_healthy = False
        except FileNotFoundError:
            status_info[name] = {
                "status": "unhealthy",
                "path": str(path),
                "error": "File not found",
            }
            all_healthy = False
        except json.JSONDecodeError:
            status_info[name] = {
                "status": "unhealthy",
                "path": str(path),
                "error": "Invalid JSON",
            }
            all_healthy = False
        except Exception as e:
            status_info[name] = {
                "status": "unhealthy",
                "path": str(path),
                "error": str(e),
            }
            all_healthy = False

    return status_info, all_healthy


def check_all_paths() -> dict:
    """
    Check all configured health check paths.
    """
    critical_status, critical_healthy = check_paths(CRITICAL_PATHS)
    optional_status, optional_healthy = check_paths(OPTIONAL_PATHS)

    all_status = {**critical_status, **optional_status}
    all_healthy = critical_healthy  # Only critical paths determine overall health

    return all_status, all_healthy


@router.get("/health", tags=["Health"], summary="Health Check")
async def health_check():
    """
    Comprehensive health check endpoint.
    Checks service status and critical data path availability.
    Returns detailed status information.
    """
    path_status, all_healthy = check_all_paths()

    if all_healthy:
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "swi-metobs-backend",
                "data_paths": path_status,
            },
            status_code=status.HTTP_200_OK,
        )
    else:
        return JSONResponse(
            content={
                "status": "degraded",
                "service": "swi-metobs-backend",
                "data_paths": path_status,
            },
            status_code=status.HTTP_200_OK,  # Still return 200, but with degraded status
        )


@router.get("/live", tags=["Health"], summary="Liveness Probe")
async def liveness_probe():
    """
    Liveness probe endpoint.
    Indicates that the application is running (not crashed).
    Used by Kubernetes and container orchestrators.
    """
    return Response(
        status_code=status.HTTP_200_OK, content="OK", media_type="text/plain"
    )


@router.get("/ready", tags=["Health"], summary="Readiness Probe")
async def readiness_probe():
    """
    Readiness probe endpoint.
    Indicates that the application is ready to serve traffic.
    Checks that all critical data paths are available before returning ready.
    Used by Kubernetes and container orchestrators to determine
    when to start sending traffic to a pod.
    """
    path_status, all_healthy = check_all_paths()

    if all_healthy:
        return Response(
            status_code=status.HTTP_200_OK, content="Ready", media_type="text/plain"
        )
    else:
        # Return 503 Service Unavailable if critical paths are missing
        logger.error(
            "Readiness probe failed - critical data paths unavailable: {}".format(
                [
                    name
                    for name, info in path_status.items()
                    if info["status"] == "unhealthy"
                ]
            )
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "missing_paths": [
                    name
                    for name, info in path_status.items()
                    if info["status"] == "unhealthy"
                ],
            },
        )
