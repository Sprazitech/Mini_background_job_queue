"""
Worker component tests for the Mini Background Job Queue.
Tests the worker loop, handlers, retry logic, and circuit breakers.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.worker.handlers import handle_send_email, handle_generate_report, HANDLERS
from app.worker.retry import calculate_next_attempt
from app.worker.loop import (
    run_worker_cycle,
    get_circuit_breaker_status,
    reset_circuit_breaker,
    get_worker_stats,
    CIRCUIT_BREAKER_THRESHOLD,
    CIRCUIT_BREAKER_RESET_TIMEOUT,
)


class TestWorkerHandlers:
    """Test worker job handlers."""
    
    async def test_handle_send_email_success(self):
        """Test successful email handler execution."""
        payload = {"to": "test@example.com", "subject": "Test"}
        start_time = datetime.now(timezone.utc)
        
        # Should complete without error
        await handle_send_email(payload)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        assert 1.9 <= duration <= 2.1, f"Handler should take ~2 seconds, took {duration}"
    
    async def test_handle_send_email_failure(self):
        """Test email handler failure simulation."""
        payload = {"to": "test@example.com", "subject": "Test", "force_fail": True}
        
        with pytest.raises(ValueError, match="Simulated email failure"):
            await handle_send_email(payload)
    
    async def test_handle_generate_report_success(self):
        """Test successful report generator execution."""
        payload = {"report_type": "daily", "format": "pdf"}
        start_time = datetime.now(timezone.utc)
        
        await handle_generate_report(payload)
        
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        assert 2.9 <= duration <= 3.1, f"Handler should take ~3 seconds, took {duration}"
    
    async def test_handle_generate_report_failure(self):
        """Test report generator failure simulation."""
        payload = {"report_type": "daily", "format": "pdf", "force_error": True}
        
        with pytest.raises(RuntimeError, match="Simulated report error"):
            await handle_generate_report(payload)
    
    def test_handler_registry(self):
        """Test that all handlers are registered correctly."""
        assert "send_email" in HANDLERS
        assert "generate_report" in HANDLERS
        assert HANDLERS["send_email"] == handle_send_email
        assert HANDLERS["generate_report"] == handle_generate_report


class TestRetryLogic:
    """Test exponential backoff retry logic."""
    
    def test_calculate_next_attempt_exponential(self):
        """Test exponential backoff calculation."""
        # Test first attempt (2^0 = 1, but min is 2)
        next_attempt = calculate_next_attempt(0)
        assert isinstance(next_attempt, datetime)
        
        # Verify it's in the future
        assert next_attempt > datetime.now(timezone.utc)
        
        # Check timing (should be ~1-2 seconds in future)
        time_diff = (next_attempt - datetime.now(timezone.utc)).total_seconds()
        assert 1 <= time_diff <= 2
    
    def test_calculate_next_attempt_attempt_sequence(self):
        """Test sequence of attempts produces increasing delays."""
        attempts = []
        for i in range(5):
            next_attempt = calculate_next_attempt(i)
            attempts.append(next_attempt)
        
        # Each attempt should be after the previous
        for i in range(1, len(attempts)):
            assert attempts[i] > attempts[i-1]
    
    def test_calculate_next_attempt_capped(self):
        """Test that backoff is capped at 300 seconds (5 minutes)."""
        # Large attempt number should hit cap
        next_attempt = calculate_next_attempt(20)  # 2^20 would be huge
        
        time_diff = (next_attempt - datetime.now(timezone.utc)).total_seconds()
        # Should be capped around 300 seconds
        assert 295 <= time_diff <= 305


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def setup_method(self):
        """Reset circuit breakers before each test."""
        from app.worker.loop import _circuit_breakers
        _circuit_breakers.clear()
    
    def test_circuit_breaker_initial_status(self):
        """Test initial circuit breaker status."""
        status = get_circuit_breaker_status()
        assert status == {}  # Should be empty initially
    
    def test_circuit_breaker_manual_reset(self):
        """Test manual circuit breaker reset."""
        # First, need to simulate some failures to create a circuit breaker
        from app.worker.loop import _circuit_breakers
        _circuit_breakers["test_job"] = {"failures": 3, "last_failure": datetime.now(timezone.utc)}
        
        # Reset the circuit breaker
        result = reset_circuit_breaker("test_job")
        assert result is True
        
        # Verify it was reset
        assert _circuit_breakers["test_job"]["failures"] == 0
    
    def test_circuit_breaker_reset_nonexistent(self):
        """Test resetting non-existent circuit breaker."""
        result = reset_circuit_breaker("nonexistent_job")
        assert result is False
    
    def test_get_worker_stats(self):
        """Test getting worker statistics."""
        stats = get_worker_stats()
        
        assert "circuit_breakers" in stats
        assert "active_handlers" in stats
        assert "circuit_breaker_threshold" in stats
        assert "circuit_breaker_reset_timeout" in stats
        
        assert stats["circuit_breaker_threshold"] == CIRCUIT_BREAKER_THRESHOLD
        assert stats["circuit_breaker_reset_timeout"] == CIRCUIT_BREAKER_RESET_TIMEOUT
        assert "send_email" in stats["active_handlers"]
        assert "generate_report" in stats["active_handlers"]


class TestWorkerLoopIntegration:
    """Integration tests for worker loop (mocked database)."""
    
    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        mock_session = AsyncMock()
        mock_session_factory = AsyncMock(return_value=mock_session)
        return mock_session_factory
    
    async def test_run_worker_cycle_no_jobs(self, mock_session_factory):
        """Test worker cycle when no jobs are available."""
        mock_session = mock_session_factory.return_value
        
        # Mock no jobs returned
        mock_result = AsyncMock()
        mock_result.mappings.return_value.one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        # Run worker cycle
        claimed = await run_worker_cycle(mock_session_factory)
        
        # Should return False (no job claimed)
        assert claimed is False
        
        # Should have called UPDATE_HEARTBEAT
        assert mock_session.execute.call_count >= 1
        mock_session.commit.assert_called()
    
    async def test_run_worker_cycle_with_job_success(self, mock_session_factory):
        """Test worker cycle with successful job execution."""
        mock_session = mock_session_factory.return_value
        
        # Mock a job
        mock_result = AsyncMock()
        mock_job = {
            "id": "test-job-id",
            "type": "send_email",
            "payload": {"to": "test@example.com"},
            "attempts": 0,
            "max_retries": 3,
        }
        mock_result.mappings.return_value.one_or_none.return_value = mock_job
        mock_session.execute.return_value = mock_result
        
        # Patch the handler to avoid actual sleep
        with patch("app.worker.loop.HANDLERS", {"send_email": AsyncMock()}):
            # Run worker cycle
            claimed = await run_worker_cycle(mock_session_factory)
            
            # Should return True (job claimed)
            assert claimed is True
            
            # Handler should have been called
            app.worker.loop.HANDLERS["send_email"].assert_called_once_with(
                {"to": "test@example.com"}
            )
    
    async def test_run_worker_cycle_with_job_failure(self, mock_session_factory):
        """Test worker cycle with job failure."""
        mock_session = mock_session_factory.return_value
        
        # Mock a job
        mock_result = AsyncMock()
        mock_job = {
            "id": "test-job-id",
            "type": "send_email",
            "payload": {"to": "test@example.com"},
            "attempts": 0,
            "max_retries": 3,
        }
        mock_result.mappings.return_value.one_or_none.return_value = mock_job
        mock_session.execute.return_value = mock_result
        
        # Patch handler to raise exception
        mock_handler = AsyncMock(side_effect=ValueError("Test error"))
        with patch("app.worker.loop.HANDLERS", {"send_email": mock_handler}):
            # Run worker cycle
            claimed = await run_worker_cycle(mock_session_factory)
            
            # Should return True (job was claimed)
            assert claimed is True
            
            # Should have executed failure handling SQL
            assert mock_session.execute.call_count >= 2


class TestDeadLetterQueueIntegration:
    """Test dead letter queue integration (requires actual schema)."""
    
    @pytest.mark.skip(reason="Requires actual database with dead_letter_queue table")
    async def test_dead_letter_queue_archival(self):
        """Test that failed jobs are archived to dead letter queue.
        
        Note: This test requires the dead_letter_queue table to exist in the database.
        It should be run in an integration test environment with a real database.
        """
        # This would test the database trigger functionality
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])