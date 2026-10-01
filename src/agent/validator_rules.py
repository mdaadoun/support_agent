"""Pattern rules and feature extraction for Zero LLM Authority validation."""

import re
from collections.abc import Sequence

from models.tools import ToolCallTrace

__all__ = [
    "MUTATION_RE",
    "check_refund_tool_authorization",
    "check_voucher_tool_authorization",
    "detect_approval_claims",
    "extract_certified_amounts",
    "extract_monetary_amounts",
]

CURRENCY_PREFIX_RE = re.compile(r"(?:€|\$|£)\s*([0-9]+(?:[.,][0-9]{1,2})?)(?!\s*%)")
CURRENCY_SUFFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_])([0-9]+(?:[.,][0-9]{1,2})?)\s*(?:€|\$|£|EUR|eur|euros?|USD|usd|dollars?|GBP|gbp|cents?)\b"
)
CONTEXTUAL_MONEY_RE = re.compile(
    r"\b(?:refund|voucher|compensation|credit|reimbursement|remboursement)\s+(?:of\s+)?(?:€|\$|£)?\s*([0-9]+(?:[.,][0-9]{1,2})?)\b",
    re.IGNORECASE,
)
NEGATION_WORDS = {
    "not",
    "cannot",
    "can't",
    "unable",
    "won't",
    "will not",
    "neither",
    "never",
    "refused",
    "denied",
    "ineligible",
    "expired",
    "pas",
    "ne",
    "non",
    "aucun",
    "impossible",
    "sans",
}
REFUND_APPROVAL_RE = re.compile(
    r"\b(?:refund|return|reimbursement|remboursement)\b[^\.\n;]*\b(?:approved|processed|issued|granted|accepted|approuvé|validé|accordé)\b",
    re.IGNORECASE,
)
REFUND_PROMISE_RE = re.compile(
    r"\b(?:we have refunded|we will refund|we are refunding|i have refunded|i will refund)\b",
    re.IGNORECASE,
)
VOUCHER_APPROVAL_RE = re.compile(
    r"\b(?:voucher|compensation|bon d'achat)\b[^\.\n;]*\b(?:approved|issued|granted|credited|accordé|crédité)\b",
    re.IGNORECASE,
)
VOUCHER_PROMISE_RE = re.compile(
    r"\b(?:we have granted|we have credited|we will credit|we have issued a voucher)\b",
    re.IGNORECASE,
)
MUTATION_RE = re.compile(
    r"\b(?:we have cancelled your order|order has been cancelled by us|we have updated your address|delivery address has been updated)\b",
    re.IGNORECASE,
)


def _parse_to_cents(amount_str: str, is_cents: bool = False) -> int:
    val = float(amount_str.replace(",", "."))
    return round(val) if is_cents else round(val * 100)


def extract_monetary_amounts(text: str) -> list[tuple[str, int]]:
    """Extract all currency and monetary figures from text mapped to integer cents."""
    results: list[tuple[str, int]] = []
    seen: set[str] = set()

    for m in CURRENCY_PREFIX_RE.finditer(text):
        raw = m.group(0)
        if raw not in seen:
            seen.add(raw)
            results.append((raw, _parse_to_cents(m.group(1))))

    for m in CURRENCY_SUFFIX_RE.finditer(text):
        raw = m.group(0)
        if raw not in seen:
            seen.add(raw)
            results.append((raw, _parse_to_cents(m.group(1), "cent" in raw.lower())))

    for m in CONTEXTUAL_MONEY_RE.finditer(text):
        raw = m.group(0)
        if raw not in seen:
            seen.add(raw)
            results.append((raw, _parse_to_cents(m.group(1))))

    return results


def extract_certified_amounts(traces: Sequence[ToolCallTrace]) -> set[int]:
    """Extract deterministically certified amounts (in cents) from successful tool traces."""
    certified: set[int] = {0}
    for trace in traces:
        if not trace.result.success or not trace.result.data:
            continue
        data = trace.result.data
        for k in (
            "refundable_items_total_cents",
            "delay_compensation_voucher_cents",
            "items_total_ttc_cents",
            "shipping_fee_ttc_cents",
        ):
            val = data.get(k)
            if isinstance(val, int):
                certified.add(val)

        items = data.get("items_total_ttc_cents")
        shipping = data.get("shipping_fee_ttc_cents")
        if isinstance(items, int) and isinstance(shipping, int):
            certified.add(items + shipping)

        refund_items = data.get("refundable_items_total_cents")
        voucher = data.get("delay_compensation_voucher_cents")
        if isinstance(refund_items, int) and isinstance(voucher, int):
            certified.add(refund_items + voucher)

        for k, v in data.items():
            if isinstance(v, int) and "cents" in k.lower():
                certified.add(v)
    return certified


def detect_approval_claims(text: str) -> list[str]:
    """Detect unnegated approval claims in response text."""
    claims: list[str] = []
    for s in re.split(r"[\n.!?]+", text):
        clean = s.strip()
        if not clean:
            continue
        words = set(re.findall(r"\b[a-zA-Z']+\b", clean.lower()))
        if words & NEGATION_WORDS:
            continue
        if any(p.search(clean) for p in (REFUND_APPROVAL_RE, REFUND_PROMISE_RE)):
            claims.append("refund_approval")
        if any(p.search(clean) for p in (VOUCHER_APPROVAL_RE, VOUCHER_PROMISE_RE)):
            claims.append("voucher_approval")
    return list(dict.fromkeys(claims))


def check_refund_tool_authorization(traces: Sequence[ToolCallTrace]) -> bool:
    """Verify if tool execution deterministically authorized a refund."""
    return any(
        t.result.success
        and t.result.data
        and (
            t.result.data.get("is_eligible_for_return") is True
            or t.result.data.get("refundable_items_total_cents", 0) > 0
        )
        for t in traces
    )


def check_voucher_tool_authorization(traces: Sequence[ToolCallTrace]) -> bool:
    """Verify if tool execution deterministically authorized compensation or voucher."""
    return any(
        t.result.success
        and t.result.data
        and (
            t.result.data.get("delay_compensation_voucher_cents", 0) > 0
            or t.result.data.get("voucher_granted") is True
            or (
                t.result.data.get("delay_days", 0) > 5
                and t.result.data.get("is_delayed") is True
            )
        )
        for t in traces
    )
