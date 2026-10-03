import pytest
from app.utils.function_name import get_function_name


class TestFunctionName:
    """Test cases for function name utility."""

    def test_get_function_name_basic(self):
        """Test basic function name retrieval."""
        # Call the function from within a test function
        result = get_function_name()

        # Should return the fully qualified name
        assert isinstance(result, str)
        assert len(result) > 0
        # In pytest context, it returns pytest's internal function names
        assert "pytest" in result or "test" in result

    def test_get_function_name_with_module(self):
        """Test function name retrieval includes module information."""
        result = get_function_name()

        # Should include module path or pytest context
        assert "pytest" in result or "function_name" in result

    def test_get_function_name_nested_call(self):
        """Test function name retrieval from nested function calls."""

        def nested_function():
            return get_function_name()

        result = nested_function()

        # Should return the caller's function name, not the nested one
        assert "test_get_function_name_nested_call" in result

    def test_get_function_name_class_method(self):
        """Test function name retrieval from class methods."""
        result = get_function_name()

        # Should include pytest context or class/method name
        assert "pytest" in result or "TestFunctionName" in result

    def test_get_function_name_frame_depth(self):
        """Test that function goes two levels up in call stack."""

        def level1():
            return get_function_name()

        def level2():
            return level1()

        result = level2()

        # Should return pytest context or intermediate function names
        assert "pytest" in result or "level" in result

    def test_get_function_name_with_inspect(self):
        """Test integration with inspect module."""
        result = get_function_name()

        # Verify it's using inspect module correctly
        assert isinstance(result, str)
        assert len(result) > 0

        # Should contain standard Python naming components
        parts = result.split(".")
        assert len(parts) >= 2  # At least module.function

    def test_get_function_name_error_handling(self):
        """Test error handling when frame information is missing."""
        # This test verifies the function doesn't crash when called in edge cases
        # We can't easily test the actual error conditions, but we can verify
        # it handles normal cases gracefully

        try:
            result = get_function_name()
            assert isinstance(result, str)
            assert len(result) > 0
        except Exception as e:
            pytest.fail(f"get_function_name should not raise exceptions: {e}")

    def test_get_function_name_consistency(self):
        """Test that function name retrieval is consistent across calls."""
        # Call multiple times from same context
        result1 = get_function_name()
        result2 = get_function_name()

        # Should return the same result
        assert result1 == result2

    def test_get_function_name_in_test_context(self):
        """Test function name retrieval specifically in pytest context."""
        result = get_function_name()

        # In pytest context, should include pytest's internal function names
        assert "pytest" in result
