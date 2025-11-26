"""Unit tests for base agent classes and result types."""

import unittest
from unittest.mock import patch

from app.agents.base_agent import AgentResult, BaseAgent


class TestAgentResult(unittest.TestCase):
    """Test AgentResult factory methods and attributes."""

    def test_success_result_creation(self):
        """Test creating a successful result."""
        output_data = {"key": "value", "count": 42}
        result = AgentResult.success_result(output_data, metric1="test", metric2=100)

        self.assertTrue(result.success)
        self.assertEqual(result.output, output_data)
        self.assertIsNone(result.error)
        self.assertEqual(result.metadata["metric1"], "test")
        self.assertEqual(result.metadata["metric2"], 100)

    def test_success_result_without_metadata(self):
        """Test creating a successful result without metadata."""
        output_data = "simple string output"
        result = AgentResult.success_result(output_data)

        self.assertTrue(result.success)
        self.assertEqual(result.output, output_data)
        self.assertIsNone(result.error)
        self.assertEqual(result.metadata, {})

    def test_error_result_creation(self):
        """Test creating an error result."""
        error_msg = "Something went wrong"
        result = AgentResult.error_result(error_msg, error_code="ERR_001", context="validation")

        self.assertFalse(result.success)
        self.assertIsNone(result.output)
        self.assertEqual(result.error, error_msg)
        self.assertEqual(result.metadata["error_code"], "ERR_001")
        self.assertEqual(result.metadata["context"], "validation")

    def test_error_result_without_metadata(self):
        """Test creating an error result without metadata."""
        error_msg = "Critical failure"
        result = AgentResult.error_result(error_msg)

        self.assertFalse(result.success)
        self.assertIsNone(result.output)
        self.assertEqual(result.error, error_msg)
        self.assertEqual(result.metadata, {})

    def test_success_result_with_none_output(self):
        """Test creating a successful result with None output."""
        result = AgentResult.success_result(None)

        self.assertTrue(result.success)
        self.assertIsNone(result.output)
        self.assertIsNone(result.error)


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing BaseAgent."""

    async def execute(self, input_data):
        """Simple execute implementation."""
        return AgentResult.success_result({"processed": input_data})


class TestBaseAgent(unittest.IsolatedAsyncioTestCase):
    """Test BaseAgent abstract class and logging methods."""

    def setUp(self):
        """Set up test agent."""
        self.correlation_id = "test-correlation-123"
        self.agent = ConcreteAgent(name="TestAgent", correlation_id=self.correlation_id)

    def test_agent_initialization(self):
        """Test agent initialization with name and correlation ID."""
        self.assertEqual(self.agent.name, "TestAgent")
        self.assertEqual(self.agent.correlation_id, self.correlation_id)
        self.assertIsNotNone(self.agent.logger)

    def test_agent_initialization_without_correlation_id(self):
        """Test agent initialization without correlation ID defaults to 'unknown'."""
        agent = ConcreteAgent(name="TestAgent")
        self.assertEqual(agent.name, "TestAgent")
        self.assertEqual(agent.correlation_id, "unknown")

    def test_log_info_includes_correlation_id(self):
        """Test log_info includes correlation ID in extra."""
        with patch.object(self.agent.logger, "info") as mock_info:
            self.agent.log_info("Test message", custom_field="value")

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            self.assertIn("[TestAgent] Test message", call_args[0])
            self.assertEqual(call_args[1]["extra"]["correlation_id"], self.correlation_id)
            self.assertEqual(call_args[1]["extra"]["custom_field"], "value")

    def test_log_warning_includes_correlation_id(self):
        """Test log_warning includes correlation ID in extra."""
        with patch.object(self.agent.logger, "warning") as mock_warning:
            self.agent.log_warning("Warning message", warning_type="validation")

            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            self.assertIn("[TestAgent] Warning message", call_args[0])
            self.assertEqual(call_args[1]["extra"]["correlation_id"], self.correlation_id)
            self.assertEqual(call_args[1]["extra"]["warning_type"], "validation")

    def test_log_error_includes_correlation_id(self):
        """Test log_error includes correlation ID in extra."""
        with patch.object(self.agent.logger, "error") as mock_error:
            self.agent.log_error("Error message", error_code="E001")

            mock_error.assert_called_once()
            call_args = mock_error.call_args
            self.assertIn("[TestAgent] Error message", call_args[0])
            self.assertEqual(call_args[1]["extra"]["correlation_id"], self.correlation_id)
            self.assertEqual(call_args[1]["extra"]["error_code"], "E001")

    async def test_execute_implementation(self):
        """Test concrete execute implementation."""
        result = await self.agent.execute({"test": "data"})

        self.assertTrue(result.success)
        self.assertEqual(result.output, {"processed": {"test": "data"}})
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
