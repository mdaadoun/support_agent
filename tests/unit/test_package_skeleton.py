"""Unit tests verifying Step 1.3 package skeleton and mock ERP seed data."""

import importlib
import json
import re
from pathlib import Path

import pytest

from clients.erp_client import MockERPClient
from core.exceptions import AppBaseError, OrderNotFoundError
from models.enums import OrderStatusEnum

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PACKAGES = (
    "src/api",
    "src/agent",
    "src/domain",
    "src/models",
    "src/security",
    "src/tools",
    "src/clients",
    "src/persistence",
    "src/observability",
    "src/core",
)
REQUIRED_TEST_DIRS = (
    "tests/unit",
    "tests/integration",
    "tests/agent",
    "tests/fixtures",
)


def test_modular_directory_tree_exists() -> None:
    """Validate all required package and test directories exist in repository."""
    for pkg in REQUIRED_PACKAGES:
        pkg_path = PROJECT_ROOT / pkg
        assert pkg_path.is_dir(), f"Required package directory missing: {pkg}"
        init_file = pkg_path / "__init__.py"
        assert init_file.is_file(), f"Missing __init__.py in package: {pkg}"

    for test_dir in REQUIRED_TEST_DIRS:
        test_path = PROJECT_ROOT / test_dir
        assert test_path.is_dir(), f"Required test directory missing: {test_dir}"


def test_package_modules_importable() -> None:
    """Validate all core packages can be dynamically imported without syntax/runtime error."""
    modules_to_import = [
        "api",
        "agent",
        "domain",
        "models",
        "security",
        "tools",
        "clients",
        "persistence",
        "observability",
        "core",
    ]
    for module_name in modules_to_import:
        mod = importlib.import_module(module_name)
        assert mod is not None, f"Failed to import module '{module_name}'"


def test_mock_orders_seed_data_validation() -> None:
    """Validate data/mock_orders.json conforms to schema and scenario coverage."""
    orders_path = PROJECT_ROOT / "data" / "mock_orders.json"
    assert orders_path.is_file(), "data/mock_orders.json must exist"

    with orders_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert "orders" in data, "Root key 'orders' must be present in mock_orders.json"
    orders = data["orders"]
    assert len(orders) >= 6, "Mock data must contain at least 6 representative orders"

    order_id_regex = re.compile(r"^CMD-[0-9]{5,8}$")
    statuses_present: set[str] = set()

    for order in orders:
        # Schema checks
        assert order_id_regex.match(
            order["order_id"]
        ), f"Invalid order_id format: {order['order_id']}"
        assert (
            "@" in order["customer_email"]
        ), f"Invalid email: {order['customer_email']}"
        assert order["carrier"], "Carrier must not be empty"
        assert order["status"] in {
            e.value for e in OrderStatusEnum
        }, f"Invalid status: {order['status']}"
        statuses_present.add(order["status"])

        # Financial & date fields
        assert order["items_total_ttc_cents"] >= 0
        assert order["shipping_fee_ttc_cents"] >= 0
        assert isinstance(order["is_express"], bool)
        assert (
            order.get("tenant_id") == "default_tenant"
        ), "Tenant ID must be present for multi-tenancy"

        # Items breakdown
        assert len(order["items"]) >= 1, f"Order {order['order_id']} must have items"
        for item in order["items"]:
            assert item["sku"].startswith("SKU-")
            assert item["name"]
            assert item["quantity"] >= 1
            assert item["price_cents"] >= 0

    # Required scenario coverage: delivered, delayed, cancelled, returned, in_transit
    assert "DELIVERED" in statuses_present, "Must contain DELIVERED scenario"
    assert "DELAYED" in statuses_present, "Must contain DELAYED scenario"
    assert "CANCELLED" in statuses_present, "Must contain CANCELLED scenario"
    assert "RETURNED" in statuses_present, "Must contain RETURNED scenario"
    assert "IN_TRANSIT" in statuses_present, "Must contain IN_TRANSIT scenario"


def test_mock_erp_client_seed_queries() -> None:
    """Validate MockERPClient queries against mock_orders.json."""
    client = MockERPClient(data_path=PROJECT_ROOT / "data" / "mock_orders.json")

    # Nominal delivered order lookup
    delivered_order = client.get_order_by_id("CMD-10001")
    assert delivered_order["order_id"] == "CMD-10001"
    assert delivered_order["status"] == "DELIVERED"
    assert delivered_order["customer_email"] == "alice@example.com"

    # Delayed order lookup
    delayed_order = client.get_order_by_id("CMD-10002")
    assert delayed_order["order_id"] == "CMD-10002"
    assert delayed_order["status"] == "DELAYED"

    # Unknown order lookup raises shielded exception
    with pytest.raises(OrderNotFoundError) as exc_info:
        client.get_order_by_id("CMD-99999")
    assert issubclass(OrderNotFoundError, AppBaseError)
    assert exc_info.value.error_code == "ORDER_NOT_FOUND"


def test_layer_isolation_guardrail() -> None:
    """Validate Core Domain and Models do not import from Infrastructure or Presentation."""
    prohibited_modules = (
        "api",
        "cli",
        "tools",
        "clients",
        "persistence",
        "observability",
    )
    domain_and_models = list((PROJECT_ROOT / "src" / "domain").glob("*.py")) + list(
        (PROJECT_ROOT / "src" / "models").glob("*.py")
    )

    for py_file in domain_and_models:
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            line_str = line.strip()
            for prohibited in prohibited_modules:
                pattern = rf"^(?:from|import)\s+{prohibited}(?:\.|\s|$)"
                assert not re.match(
                    pattern, line_str
                ), f"Layer isolation violation in {py_file.name}: imports from '{prohibited}' ({line_str})"


def test_file_loc_limits_guardrail() -> None:
    """Validate every source file in src/ adheres to the Max 250 LOC limit."""
    src_files = list((PROJECT_ROOT / "src").rglob("*.py"))
    assert len(src_files) > 0

    for py_file in src_files:
        lines = py_file.read_text(encoding="utf-8").splitlines()
        loc_count = len(lines)
        assert (
            loc_count <= 250
        ), f"File '{py_file.relative_to(PROJECT_ROOT)}' exceeds 250 LOC limit: {loc_count} lines"
