# SWI MetObs Backend

[![Code Coverage](https://img.shields.io/codecov/c/github/UNIS-Svalbard-Weather-Information/swi-metobs-backend)](https://codecov.io/gh/UNIS-Svalbard-Weather-Information/swi-metobs-backend)
[![Test and Lint](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/actions/workflows/test-and-lint.yml/badge.svg)](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/actions/workflows/test-and-lint.yml)
[![Docker Build and Push](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/actions/workflows/docker-build-push.yml/badge.svg)](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend/actions/workflows/docker-build-push.yml)

A backend service for meteorological observations, serving as the public data API for the SWIApp (Svalbard Weather Information). This service provides precached realtime and historical weather observation and forecast data, as well as multiple other public data.

## Installation

### Prerequisites

- Python 3.8+ (use python 3.13 for Production)
- Docker (optional, for containerized deployment)

### Steps

1. Clone the repository:

   ```bash
   git clone https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-backend.git
   cd swi-metobs-backend
   ```

2. Install dependencies using uv:

   ```bash
   uv venv
   uv sync --extra dev
   ```

3. Run the application:

   ```bash
   uvicorn app.main:app --reload
   ```

**Note**: This project requires Python 3.13.

## Configuration

The spheres functionality can be configured using environment variables:

**Sphere Data Sources:**
- `SPHERE_LIP_GEOJSON_FETCH`: URL for The Living Ice Project GeoJSON data (default: `https://livingiceproject.com/static/shapes/spheres.geojson`)
- `SPHERE_LIP_BASE_URL`: Base URL for The Living Ice Project assets (default: `https://livingiceproject.com/`)

**Caching:**
- The system automatically caches GeoJSON data and computed distance/bearing matrices for 1 hour

## Usage

### API Endpoints

The API provides the following endpoints:

- `/api/v3/stations`: Retrieve station information.
- `/api/v3/forecast`: Retrieve forecast data.
- `/api/v3/observations`: Retrieve observational data.
- `/api/v3/spheres`: Access spherical panorama data and navigation.

### Example Request

```bash
curl http://localhost:8000/api/v3/stations
```

## Testing

Run the test suite:

```bash
uv sync --extra test
uv run pytest
```

> [!NOTE]
> This is designed to run on linux based system so some tests will fail on windows because of the need of elevated privilege to create symlink.

## Docker

Build and run the Docker container:

```bash
docker build -t swi-metobs-backend .
docker run -p 8000:8000 swi-metobs-backend
```

## Contributing

Contributions are welcome! Please coordinate with the complete SWI project team before starting work on significant changes. All pull requests must:

- Be well-documented
- Pass all tests
- Pass linting checks
- Follow the project's coding standards

## License

This project is licensed under the European Union Public License (EUPL) 1.2. See the LICENCE file for details.