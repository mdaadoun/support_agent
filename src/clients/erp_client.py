"""Mock ERP client loading and querying order records with retry shielding."""

import json
from pathlib import Path
from typing import Any

from core.config import get_settings
from core.exceptions import (
    CircuitBreakerError,
    ConfigurationError,
    OrderNotFoundError,
)
from core.retry import retry_async_call, retry_sync_call
from observability.logger import get_logger

logger = get_logger(__name__)

__all__ = ["MockERPClient"]


class MockERPClient:
    """Adapter reading and querying mock order records from local JSON storage with retries."""

    def __init__(
        self,
        data_path: Path | None = None,
        max_attempts: int = 2,
    ) -> None:
        settings = get_settings()
        self.data_path = data_path or settings.erp_data_path
        self.max_attempts = max_attempts
        self._transient_failures_remaining: int = 0

    def simulate_transient_network_failure(self, failure_count: int = 1) -> None:
        """Configure transient network failure simulation for testing retry behavior."""
        self._transient_failures_remaining = max(0, failure_count)

    def _read_orders_raw(self) -> dict[str, dict[str, Any]]:
        """Read and index orders by order_id from JSON file with simulated network resilience."""
        if self._transient_failures_remaining > 0:
            self._transient_failures_remaining -= 1
            logger.warning(
                "simulating_erp_network_failure",
                remaining=self._transient_failures_remaining,
            )
            raise ConnectionError("Simulated ERP network connection failure")

        if not self.data_path.exists():
            logger.error("erp_data_file_missing", path=str(self.data_path))
            return {}

        try:
            with open(self.data_path, encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "erp_data_file_read_error",
                path=str(self.data_path),
                error=str(exc),
            )
            raise ConfigurationError(f"Failed to read ERP data store: {exc}") from exc

        if not isinstance(payload, dict) or "orders" not in payload:
            return {}

        orders_list = payload.get("orders", [])
        return {
            item["order_id"]: item
            for item in orders_list
            if isinstance(item, dict) and "order_id" in item
        }

    def _fetch_order_direct(self, order_id: str) -> dict[str, Any]:
        """Internal worker fetching order from raw dataset without retry handling."""
        all_orders = self._read_orders_raw()
        if order_id not in all_orders:
            raise OrderNotFoundError(order_id=order_id)
        return all_orders[order_id]

    def get_order_by_id(self, order_id: str) -> dict[str, Any]:
        """Query order by ID with Tenacity exponential retry policy (max 2 attempts).

        Args:
            order_id: Standardized order identifier (e.g. 'CMD-10001').

        Returns:
            Dictionary containing order metadata and line items.

        Raises:
            OrderNotFoundError: If order does not exist in storage (not retried).
            CircuitBreakerError: If upstream network failure persists across all retry attempts.
        """
        try:
            return retry_sync_call(
                self._fetch_order_direct,
                order_id,
                max_attempts=self.max_attempts,
            )
        except (ConnectionError, TimeoutError) as exc:
            logger.error(
                "erp_network_retries_exhausted", order_id=order_id, error=str(exc)
            )
            raise CircuitBreakerError(
                f"Upstream ERP service temporarily unavailable for order '{order_id}': {exc}"
            ) from exc

    async def get_order_by_id_async(self, order_id: str) -> dict[str, Any]:
        """Asynchronously query order by ID with Tenacity retry policy.

        Args:
            order_id: Standardized order identifier.

        Returns:
            Dictionary containing order record.

        Raises:
            OrderNotFoundError: If order does not exist.
            CircuitBreakerError: If network retries are exhausted.
        """

        async def _async_fetch() -> dict[str, Any]:
            return self._fetch_order_direct(order_id)

        try:
            return await retry_async_call(
                _async_fetch,
                max_attempts=self.max_attempts,
            )
        except (ConnectionError, TimeoutError) as exc:
            logger.error(
                "erp_async_retries_exhausted", order_id=order_id, error=str(exc)
            )
            raise CircuitBreakerError(
                f"Upstream ERP service temporarily unavailable for order '{order_id}': {exc}"
            ) from exc

    def list_orders(self) -> list[dict[str, Any]]:
        """Retrieve list of all active orders from storage.

        Returns:
            List of order dictionary records.
        """
        raw_map = self._read_orders_raw()
        return list(raw_map.values())
