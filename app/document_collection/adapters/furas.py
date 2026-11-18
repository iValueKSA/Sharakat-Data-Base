from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from ..contracts import DocumentObservation, PageCapture, SourceOpportunityContext


_PROVIDER_PATH = re.compile(r"/opportunity/([^/?#]+)", re.I)
_ATTACHMENT_PATH = re.compile(r"/opportunity/attachment/([^/]+)/([^/]+)", re.I)
_AMOUNT = re.compile(r"(?<!\d)(\d[\d,]*(?:\.\d{1,2})?)(?!\d)")


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _walk_values(value, key: str):
    if isinstance(value, dict):
        for name, item in value.items():
            if name.casefold() == key.casefold():
                yield item
            yield from _walk_values(item, key)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item, key)


class FurasDocumentAdapter:
    """Parser for an exact Furas opportunity detail page, never the national listing."""
    source_key = "furas"
    parser_version = "furas-docs-1.0.0"
    capabilities = {
        "booklet": True, "draft_contract": True, "application_form": True,
        "additional_attachments": True, "purchase_requirement": True,
        "page_fallback": True, "gis_price_evidence": True, "lifecycle_evidence": True,
    }
    allowed_hosts = ("furas.momah.gov.sa", "momah.gov.sa", "gisapps.balady.gov.sa")

    @staticmethod
    def _category(text: str, href: str = "") -> tuple[str, str, bool]:
        combined = f"{text} {href}".casefold()
        if re.search(r"كراسة|الشروط|المواصفات|booklet|tender.?spec", combined):
            return "TERMS_AND_CONDITIONS_BOOKLET", "TERMS_AND_SPECIFICATIONS_BOOKLET", True
        if re.search(r"مسودة.?العقد|مشروع.?العقد|draft.?contract", combined):
            return "DRAFT_CONTRACT", "DRAFT_CONTRACT", True
        if re.search(r"نموذج.?التقديم|نموذج.?طلب|application.?form", combined):
            return "GENERAL_ATTACHMENT", "APPLICATION_FORM", True
        if re.search(r"مخطط|رسم|drawing|site.?plan", combined):
            return "SITE_MAP", "OFFICIAL_DRAWINGS_OR_SITE_PLAN", True
        if re.search(r"مواصفات.?فنية|technical.?spec", combined):
            return "TECHNICAL_ATTACHMENT", "TECHNICAL_SPECIFICATIONS", True
        if re.search(r"دليل.?المستثمر|investment.?guide|investor.?guide", combined):
            return "INVESTMENT_BROCHURE", "INVESTMENT_GUIDE", False
        if re.search(r"دليل.?المستخدم|user.?guide|help.?guide", combined):
            return "GENERAL_ATTACHMENT", "OTHER_OFFICIAL_ATTACHMENT", False
        if re.search(r"مرفق|attachment", text, re.I):
            return "GENERAL_ATTACHMENT", "OTHER_OFFICIAL_ATTACHMENT", True
        return "UNKNOWN_DOCUMENT_TYPE", "UNKNOWN_DOCUMENT_TYPE", False

    @staticmethod
    def _source_price(context: SourceOpportunityContext, page_text: str) -> tuple[Decimal | None, Decimal | None, str | None, dict]:
        values = [v for v in _walk_values(context.raw_data, "RFPPRICE")]
        if not values:
            return None, None, None, {"raw_amount": None, "verification": "NO_RFPPRICE_FIELD"}
        raw = _decimal(values[0])
        evidence = {"raw_field": "RFPPRICE", "raw_value": str(values[0]), "field_count": len(values)}
        if raw is None:
            return None, None, None, {**evidence, "verification": "INVALID_OR_NEGATIVE_AMOUNT"}
        label_match = re.search(r"سعر\s+الكراسة", page_text)
        if not label_match:
            return raw, None, None, {**evidence, "verification": "LABEL_NOT_CONFIRMED"}
        nearby = page_text[label_match.start():label_match.start() + 180]
        page_amount = next((_decimal(m.group(1)) for m in _AMOUNT.finditer(nearby)), None)
        if page_amount is None or page_amount != raw:
            return raw, None, None, {**evidence, "verification": "PAGE_LABEL_AMOUNT_MISMATCH", "page_excerpt": nearby[:180]}
        currency_match = re.search(r"\b(SAR|ر\.س|ريال(?:\s+سعودي)?)\b", nearby, re.I)
        currency = "SAR" if currency_match and currency_match.group(1).upper() == "SAR" else None
        return raw, page_amount, currency, {
            **evidence, "verification": "FIELD_MATCHED_TO_BOOKLET_PRICE_LABEL",
            "page_label": "سعر الكراسة", "page_amount": str(page_amount),
            "currency_evidence": currency_match.group(0) if currency_match else None,
        }

    def discover(self, context: SourceOpportunityContext, page: PageCapture) -> list[DocumentObservation]:
        if context.source_key != self.source_key:
            raise ValueError("Furas adapter cannot process a different source namespace")
        if context.master_opportunity_id is None or context.master_merged:
            raise ValueError("Document association requires an existing non-merged Master")
        parsed_url = urlsplit(page.final_url)
        path_match = _PROVIDER_PATH.search(unquote(parsed_url.path))
        path_provider_id = path_match.group(1) if path_match else None
        if path_provider_id != context.provider_opportunity_id:
            raise ValueError("Official page does not identify the exact SourceOpportunity provider ID")
        soup = BeautifulSoup(page.body, "html.parser")
        root = soup.select_one("main") or soup.select_one("[role=main]") or soup.body or soup
        page_text = _normalized_text(root.get_text(" ", strip=True))
        if context.provider_opportunity_id not in page_text:
            raise ValueError("Official page body does not corroborate the exact provider ID")

        raw_amount, verified_amount, verified_currency, price_evidence = self._source_price(context, page_text)
        purchase_anchor = next((a for a in root.select("a[href]")
                                if re.search(r"شراء\s+الكراسة", _normalized_text(a.get_text(" ", strip=True)))), None)
        purchase_required = bool(purchase_anchor or re.search(r"شراء\s+الكراسة", page_text))
        purchase_url = urljoin(page.final_url, purchase_anchor.get("href", "")) if purchase_anchor else None
        lifecycle_match = re.search(r"(\d+\s*(?:days?|يوم|ساعة|hours?|minutes?|دقيقة)[^،.]{0,80})", page_text, re.I)
        raw_lifecycle = {key: list(_walk_values(context.raw_data, key))[:3]
                         for key in ("OPPORTUNITYACTIVESTATUS", "LASTRFPSELLDATE", "LASTBIDATE", "ENDDATE")}
        page_hash = hashlib.sha256(page.body).hexdigest()
        observations: list[DocumentObservation] = []
        seen_identity: set[str] = set()

        anchors = []
        for anchor in root.select("a[href]"):
            label = _normalized_text(anchor.get_text(" ", strip=True))
            href = urljoin(page.final_url, anchor.get("href", ""))
            category, original_type, opportunity_specific = self._category(label, href)
            attachment_match = _ATTACHMENT_PATH.search(unquote(urlsplit(href).path))
            if attachment_match and attachment_match.group(1) != context.provider_opportunity_id:
                raise ValueError("Cross-opportunity attachment does not belong to the exact SourceOpportunity")
            if attachment_match and category == "UNKNOWN_DOCUMENT_TYPE":
                # The provider route proves the exact opportunity association, but
                # a generic action label such as "تحميل" is not category evidence.
                opportunity_specific = True
            if re.search(r"شراء\s+الكراسة", label) and not attachment_match:
                continue
            if not opportunity_specific and not attachment_match:
                continue
            # Global nav/footer links and generic guides are evidence only; they are not
            # automatically attached to an investment opportunity.
            if original_type == "INVESTMENT_GUIDE" and not attachment_match:
                continue
            block = anchor
            for _ in range(4):
                parent = getattr(block, "parent", None)
                if not parent or parent is root:
                    break
                block = parent
                block_text = _normalized_text(block.get_text(" ", strip=True))
                if re.search(r"كراسة|عقد|نموذج|مخطط|مرفق|attachment", block_text, re.I):
                    break
            block_text = _normalized_text(block.get_text(" ", strip=True))[:700]
            if not label:
                label = _normalized_text((block.select_one("h1,h2,h3,h4,strong") or block).get_text(" ", strip=True))
            label = label or original_type
            source_doc_id = attachment_match.group(2) if attachment_match else None
            if source_doc_id is None:
                # A URL is a stable source-scoped identity when the provider supplies no ID.
                source_doc_id = hashlib.sha256(href.encode("utf-8")).hexdigest()
            if source_doc_id in seen_identity:
                continue
            seen_identity.add(source_doc_id)
            observations.append(DocumentObservation(
                source_document_id=source_doc_id, original_title=label[:500],
                document_type=original_type, document_category=category,
                document_scope="OPPORTUNITY" if opportunity_specific else "SOURCE",
                document_url=href, official_purchase_url=None, purchase_url_verified=None,
                access_status="UNKNOWN", rights_status="UNVERIFIED",
                participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION" if purchase_required else "UNKNOWN",
                raw_amount=raw_amount if category == "TERMS_AND_CONDITIONS_BOOKLET" else None,
                verified_amount=verified_amount if category == "TERMS_AND_CONDITIONS_BOOKLET" else None,
                verified_currency=verified_currency if category == "TERMS_AND_CONDITIONS_BOOKLET" else None,
                evidence={"page_sha256": page_hash, "page_excerpt": block_text,
                          "purchase_action_observed": purchase_required,
                          "purchase_action_url": purchase_url, "price": price_evidence,
                          "source_raw_status": context.raw_status,"raw_lifecycle_fields": raw_lifecycle,
                          "page_lifecycle_countdown_excerpt": lifecycle_match.group(1) if lifecycle_match else None},
                provenance={"source_key": "furas", "provider_opportunity_id": context.provider_opportunity_id,
                            "official_opportunity_page": page.final_url, "source_document_href": href,
                            "parser_version": self.parser_version},
                missing_evidence=["DOCUMENT_ACCESS_NOT_VERIFIED"],
                identity_verified=True, verification_status="IDENTITY_VERIFIED"))

        booklet_present = bool(re.search(r"كراسة\s+(?:الشروط|المواصفات)", page_text, re.I))
        if booklet_present and not any(x.document_category == "TERMS_AND_CONDITIONS_BOOKLET" for x in observations):
            source_doc_id = "furas-booklet:" + context.provider_opportunity_id
            observations.append(DocumentObservation(
                source_document_id=source_doc_id,
                original_title="كراسة الشروط والمواصفات",
                document_type="TERMS_AND_SPECIFICATIONS_BOOKLET",
                document_category="TERMS_AND_CONDITIONS_BOOKLET", document_scope="OPPORTUNITY",
                document_url=None, official_purchase_url=None, purchase_url_verified=None,
                access_status="PUBLIC_SOURCE_PAGE", rights_status="SOURCE_PAGE_LINK_ONLY",
                participation_requirement="PURCHASE_REQUIRED_FOR_PARTICIPATION" if purchase_required else "UNKNOWN",
                authentication_required=False, payment_required_for_document=None,
                link_verification_status="VERIFIED_SOURCE_PAGE",
                raw_amount=raw_amount, verified_amount=verified_amount, verified_currency=verified_currency,
                evidence={"page_sha256": page_hash, "booklet_section_observed": True,
                          "purchase_action_observed": purchase_required,
                          "purchase_action_url": purchase_url, "price": price_evidence,
                          "lifecycle_countdown_excerpt": lifecycle_match.group(1) if lifecycle_match else None,
                          "source_raw_status": context.raw_status,"raw_lifecycle_fields": raw_lifecycle},
                provenance={"source_key": "furas", "provider_opportunity_id": context.provider_opportunity_id,
                            "official_opportunity_page": page.final_url, "page_fallback": True,
                            "parser_version": self.parser_version},
                missing_evidence=["DIRECT_DOWNLOAD_UNAVAILABLE_OR_NOT_LINKED"],
                identity_verified=True, verification_status="ACCESS_VERIFIED"))

        if not observations:
            return []
        return observations

