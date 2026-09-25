"""Pre-extraction intent classification and threat detection engine."""

import re
from typing import Final

from core.exceptions import BusinessRuleViolationError
from models.email import InboundEmailMessage
from models.enums import IntentEnum
from models.extraction import ExtractedDemand
from observability.logger import get_logger
from security.access_control import AccessControlGuard
from security.sanitizer import (
    extract_all_order_ids,
    extract_order_id,
    scrub_control_characters,
)

__all__ = [
    "PreExtractionClassifier",
    "classify_inbound_demand",
    "detect_intents",
    "detect_legal_threat_or_hostility",
    "detect_out_of_scope",
    "extract_sub_queries",
]

logger = get_logger(__name__)

LEGAL_THREAT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:lawyer|attorney|solicitor|litigation|lawsuit|court|tribunal|prosecut\w*|"
    r"sue\s+you|suing|legal\s+action|legal\s+counsel|legal\s+proceedings|small\s+claims|"
    r"police|fraud|scam\w*|thief|thieves|chargeback|bank\s+dispute|gdpr\s+fine|"
    r"consumer\s+protection|dgccrf|trading\s+standards|better\s+business\s+bureau|"
    r"avocat|plainte|escroc\w*|arnaque\w*|poursuites?\s+judiciaires?|"
    r"fuck\w*|sh[i*]t\w*|bastard\w*|moron\w*|idiot\w*|criminal\w*)\b",
    re.IGNORECASE,
)

OUT_OF_SCOPE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:job\s+application|resume|curriculum\s+vitae|\bcv\b|internship|hiring|recruitment|"
    r"candidature|work\s+for\s+you|weather\s+in|météo|recipe\s+for|capital\s+of|write\s+(?:a\s+)?code|"
    r"python\s+script|windows\s+update|fix\s+my\s+pc|seo\s+services|guest\s+post|"
    r"backlink|b2b\s+collaboration|partnership\s+proposal)\b",
    re.IGNORECASE,
)

REFUND_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:refund\w*|money\s+back|return\w*|send\s+back|cancel(?:lation)?|"
    r"cancel\s+my\s+order|exchange|cooling[\s-]off|remboursement|retour\w*|annul\w*|rétractation)\b",
    re.IGNORECASE,
)

DELAY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:delay\w*|late|overdue|delivery\s+delay|shipping\s+delay|package\s+late|"
    r"not\s+arrived\s+yet|still\s+waiting|has\s+not\s+arrived|retard\w*|en\s+retard|non\s+reçu|pas\s+reçu)\b",
    re.IGNORECASE,
)

STATUS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:where\s+is\s+(?:my\s+)?(?:order|package|parcel|shipment|colis|commande|it|cmd-[0-9]{5,8})|"
    r"track(?:ing)?\b|order\s+status\b|shipping\s+status\b|delivery\s+status\b|"
    r"when\s+will\s+(?:it|my\s+(?:order|package|parcel|shipment))\s+arrive\b|"
    r"has\s+(?:it|my\s+(?:order|package))?\s*shipped\b|suivi\b|statut\b|"
    r"où\s+est\s+(?:mon\s+(?:colis|paquet)|ma\s+commande))\b",
    re.IGNORECASE,
)

INFO_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:invoice|receipt|bill|billing|facture|warranty|guarantee|garantie|manual|"
    r"user\s+guide|specifications|certificate)\b",
    re.IGNORECASE,
)


def detect_legal_threat_or_hostility(text: str) -> bool:
    """Identify presence of hostile litigation threats, attorney notices, or profanity."""
    return bool(LEGAL_THREAT_PATTERN.search(text))


def detect_out_of_scope(text: str) -> bool:
    """Identify non-ecommerce inquiries such as recruitment or general assistance."""
    return bool(OUT_OF_SCOPE_PATTERN.search(text))


def detect_intents(text: str) -> list[IntentEnum]:
    """Detect matching order-related intent categories from inquiry text."""
    detected: list[IntentEnum] = []
    if REFUND_PATTERN.search(text):
        detected.append(IntentEnum.REFUND_REQUEST)
    if DELAY_PATTERN.search(text):
        detected.append(IntentEnum.DELIVERY_DELAY)
    if STATUS_PATTERN.search(text):
        detected.append(IntentEnum.ORDER_STATUS)
    if INFO_PATTERN.search(text):
        detected.append(IntentEnum.ORDER_INFORMATION)
    return detected


def extract_sub_queries(text: str) -> tuple[str, ...]:
    """Extract distinct question clauses or sentences for multi-intent decomposition."""
    segments = re.split(
        r"[?!;\n]+|(?<=[.a-zA-Z0-9])\.\s+|\s+(?:and\s+also|and\s+can\s+i|and\s+how\s+to)\s+",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = [s.strip() for s in segments if len(s.strip()) >= 4]
    return tuple(cleaned)


class PreExtractionClassifier:
    """Deterministic pre-extraction classifier evaluating intent, entities, and threats."""

    @classmethod
    def classify(cls, inbound: InboundEmailMessage) -> ExtractedDemand:
        """Classify inbound email message into validated ExtractedDemand."""
        if not isinstance(inbound, InboundEmailMessage):
            raise BusinessRuleViolationError(
                f"Expected InboundEmailMessage, got {type(inbound).__name__}",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        return cls.classify_text(
            text=inbound.body_text,
            sender_email=inbound.sender_email,
            subject=inbound.subject,
        )

    @classmethod
    def classify_text(
        cls,
        text: str,
        sender_email: str,
        subject: str = "",
    ) -> ExtractedDemand:
        """Evaluate raw email text, subject, and sender into validated ExtractedDemand."""
        if not isinstance(text, str) or not isinstance(subject, str):
            raise BusinessRuleViolationError(
                "Text and subject payloads must be strings.",
                error_code="INVALID_PAYLOAD_TYPE",
            )
        normalized_email = AccessControlGuard.normalize_email(sender_email)
        full_text = scrub_control_characters(f"{subject}\n{text}".strip())

        order_id = extract_order_id(full_text)
        all_order_ids = extract_all_order_ids(full_text)
        is_threat = detect_legal_threat_or_hostility(full_text)

        if is_threat:
            logger.warning(
                "security_hostile_or_legal_threat_detected", sender=normalized_email
            )
            return ExtractedDemand(
                intent=IntentEnum.OUT_OF_SCOPE,
                order_id=order_id,
                customer_email=normalized_email,
                is_legal_threat_or_aggressive=True,
                sub_queries=(),
            )

        intents = detect_intents(full_text)
        distinct_families = {
            "logistics": bool(
                {IntentEnum.ORDER_STATUS, IntentEnum.DELIVERY_DELAY} & set(intents)
            ),
            "refund": IntentEnum.REFUND_REQUEST in intents,
            "info": IntentEnum.ORDER_INFORMATION in intents,
        }
        active_families = sum(1 for v in distinct_families.values() if v)

        if active_families > 1 or len(all_order_ids) > 1:
            candidate_intent = IntentEnum.MIXED_QUERY
            sub_queries = extract_sub_queries(full_text)
        elif len(intents) == 1:
            candidate_intent = intents[0]
            sub_queries = ()
        elif len(intents) > 1:
            candidate_intent = (
                IntentEnum.DELIVERY_DELAY
                if IntentEnum.DELIVERY_DELAY in intents
                else IntentEnum.ORDER_STATUS
            )
            sub_queries = ()
        elif detect_out_of_scope(full_text):
            candidate_intent = IntentEnum.OUT_OF_SCOPE
            sub_queries = ()
        else:
            candidate_intent = IntentEnum.OUT_OF_SCOPE
            sub_queries = ()

        order_dependent_intents = {
            IntentEnum.ORDER_STATUS,
            IntentEnum.DELIVERY_DELAY,
            IntentEnum.REFUND_REQUEST,
            IntentEnum.ORDER_INFORMATION,
            IntentEnum.MIXED_QUERY,
        }
        if candidate_intent in order_dependent_intents and order_id is None:
            intent = IntentEnum.INFORMATION_MISSING
        else:
            intent = candidate_intent

        return ExtractedDemand(
            intent=intent,
            order_id=order_id,
            customer_email=normalized_email,
            is_legal_threat_or_aggressive=False,
            sub_queries=sub_queries,
        )


def classify_inbound_demand(inbound: InboundEmailMessage) -> ExtractedDemand:
    """Convenience functional wrapper for PreExtractionClassifier.classify."""
    return PreExtractionClassifier.classify(inbound)
