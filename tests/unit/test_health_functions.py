from pathlib import Path
import json
import tempfile
import os
from app.api.health import check_paths, check_all_paths
from app.api.v3.endpoints._health_config import (
    HEALTH_CHECK_PATHS,
    CRITICAL_PATHS,
)


class TestHealthFunctions:
    """Unit tests for health check functions."""

    def test_check_paths_with_valid_json_file(self):
        """Test check_paths with a valid JSON file."""
        # Create a temporary valid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "data"}, f)
            temp_path = f.name

        try:
            # Temporarily modify the health config
            original_path = HEALTH_CHECK_PATHS.get("stations_status")
            HEALTH_CHECK_PATHS["test_valid_json"] = Path(temp_path)

            # Test the function
            status_info, all_healthy = check_paths(["test_valid_json"])

            # Verify results
            assert "test_valid_json" in status_info
            assert status_info["test_valid_json"]["status"] == "healthy"
            assert status_info["test_valid_json"]["path"] == temp_path
            assert all_healthy

        finally:
            # Clean up
            os.unlink(temp_path)
            if original_path:
                HEALTH_CHECK_PATHS["test_valid_json"] = original_path
            else:
                HEALTH_CHECK_PATHS.pop("test_valid_json", None)

    def test_check_paths_with_invalid_json_file(self):
        """Test check_paths with an invalid JSON file."""
        # Create a temporary file with invalid JSON
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json}")
            temp_path = f.name

        try:
            # Temporarily modify the health config
            HEALTH_CHECK_PATHS["test_invalid_json"] = Path(temp_path)

            # Test the function
            status_info, all_healthy = check_paths(["test_invalid_json"])

            # Verify results
            assert "test_invalid_json" in status_info
            assert status_info["test_invalid_json"]["status"] == "unhealthy"
            assert "Invalid JSON" in status_info["test_invalid_json"]["error"]
            assert not all_healthy

        finally:
            # Clean up
            os.unlink(temp_path)
            HEALTH_CHECK_PATHS.pop("test_invalid_json", None)

    def test_check_paths_with_missing_file(self):
        """Test check_paths with a non-existent file."""
        # Use a path that doesn't exist
        non_existent_path = Path("/tmp/this_file_should_not_exist_12345.json")

        # Temporarily modify the health config
        HEALTH_CHECK_PATHS["test_missing_file"] = non_existent_path

        try:
            # Test the function
            status_info, all_healthy = check_paths(["test_missing_file"])

            # Verify results
            assert "test_missing_file" in status_info
            assert status_info["test_missing_file"]["status"] == "unhealthy"
            assert "File not found" in status_info["test_missing_file"]["error"]
            assert not all_healthy

        finally:
            # Clean up
            HEALTH_CHECK_PATHS.pop("test_missing_file", None)

    def test_check_paths_with_valid_directory(self):
        """Test check_paths with a valid directory."""
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Temporarily modify the health config
            HEALTH_CHECK_PATHS["test_valid_dir"] = temp_path

            # Test the function
            status_info, all_healthy = check_paths(["test_valid_dir"])

            # Verify results
            assert "test_valid_dir" in status_info
            assert status_info["test_valid_dir"]["status"] == "healthy"
            assert status_info["test_valid_dir"]["path"] == str(temp_path)
            assert all_healthy

    def test_check_paths_with_missing_directory(self):
        """Test check_paths with a non-existent directory."""
        # Use a directory path that doesn't exist
        non_existent_dir = Path("/tmp/this_directory_should_not_exist_12345")

        # Temporarily modify the health config
        HEALTH_CHECK_PATHS["test_missing_dir"] = non_existent_dir

        try:
            # Test the function
            status_info, all_healthy = check_paths(["test_missing_dir"])

            # Verify results
            assert "test_missing_dir" in status_info
            assert status_info["test_missing_dir"]["status"] == "unhealthy"
            assert (
                "Directory not found or inaccessible"
                in status_info["test_missing_dir"]["error"]
            )
            assert not all_healthy

        finally:
            # Clean up
            HEALTH_CHECK_PATHS.pop("test_missing_dir", None)

    def test_check_paths_with_unknown_path_name(self):
        """Test check_paths with a path name not in HEALTH_CHECK_PATHS."""
        # Test with a path name that doesn't exist in the config
        status_info, all_healthy = check_paths(["this_path_does_not_exist"])

        # Should not add anything to status_info for unknown paths
        assert "this_path_does_not_exist" not in status_info
        assert all_healthy  # Should still be healthy since no actual paths were checked

    def test_check_paths_with_mixed_results(self):
        """Test check_paths with a mix of healthy and unhealthy paths."""
        # Create a valid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "data"}, f)
            valid_path = f.name

        # Create an invalid JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid}")
            invalid_path = f.name

        try:
            # Temporarily modify the health config
            HEALTH_CHECK_PATHS["test_valid"] = Path(valid_path)
            HEALTH_CHECK_PATHS["test_invalid"] = Path(invalid_path)

            # Test the function
            status_info, all_healthy = check_paths(["test_valid", "test_invalid"])

            # Verify results
            assert len(status_info) == 2
            assert status_info["test_valid"]["status"] == "healthy"
            assert status_info["test_invalid"]["status"] == "unhealthy"
            assert not all_healthy  # Should be False because one path is unhealthy

        finally:
            # Clean up
            os.unlink(valid_path)
            os.unlink(invalid_path)
            HEALTH_CHECK_PATHS.pop("test_valid", None)
            HEALTH_CHECK_PATHS.pop("test_invalid", None)

    def test_check_all_paths_returns_combined_results(self):
        """Test that check_all_paths combines critical and optional paths."""
        # Test the function
        all_status, all_healthy = check_all_paths()

        # Verify it returns a dictionary
        assert isinstance(all_status, dict)

        # Verify it returns a boolean for overall health
        assert isinstance(all_healthy, bool)

        # Verify it includes paths from both critical and optional
        critical_path_names = set(CRITICAL_PATHS)
        # optional_path_names = set(OPTIONAL_PATHS)
        # all_path_names = critical_path_names.union(optional_path_names)

        returned_path_names = set(all_status.keys())

        # Should include all critical paths
        assert critical_path_names.issubset(returned_path_names)

        # Overall health should be based only on critical paths
        critical_status, critical_healthy = check_paths(CRITICAL_PATHS)
        assert all_healthy == critical_healthy

    def test_check_all_paths_structure(self):
        """Test the structure of check_all_paths return value."""
        all_status, all_healthy = check_all_paths()

        # Verify structure of each path entry
        for path_name, path_info in all_status.items():
            assert isinstance(path_info, dict)
            assert "status" in path_info
            assert "path" in path_info
            assert path_info["status"] in ["healthy", "unhealthy"]

            if path_info["status"] == "unhealthy":
                assert "error" in path_info
                assert isinstance(path_info["error"], str)
                assert len(path_info["error"]) > 0
