"""Mock ERP client loading and querying order records with retry shielding."""

import json
from pathlib import Path
from typing import Any

from core.config import get_settings
from core.exceptions import OrderNotFoundError
from core.retry import retry_sync_call
from observability.logger import get_logger

logger = get_logger(__name__)


class MockERPClient:
    """Adapter reading mock order records from local JSON storage."""

    def __init__(self, data_path: Path | None = None) -> None:
        settings = get_settings()
        self.data_path = data_path or settings.erp_data_path

    def _read_orders_raw(self) -> dict[str, dict[str, Any]]:
        """Read and index orders by order_id from JSON file."""
        if not self.data_path.exists():
            logger.error("erp_data_file_missing", path=str(self.data_path))
            return {}

        with open(self.data_path, encoding="utf-8") as file:
            payload = json.load(file)

        orders_list = payload.get("orders", [])
        return {item["order_id"]: item for item in orders_list}

    def get_order_by_id(self, order_id: str) -> dict[str, Any]:
        """Query order by ID with Tenacity retry policy.

        Raises:
            OrderNotFoundError: If order is not present in storage.
        """
        all_orders = retry_sync_call(self._read_orders_raw, max_attempts=2)
        if order_id not in all_orders:
            raise OrderNotFoundError(order_id=order_id)
        return all_orders[order_id]
