import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ...core.errors import AppError


PROCEDURE_CODES = ("EXTRACTION", "ROOT_CANAL", "IMPLANT", "FILLING", "CLEANING")
SUPPORTED_LOCALES = ("vi", "en")


def _content_hash(template: dict) -> str:
    canonical = json.dumps(
        {
            "care_instructions": template["care_instructions"],
            "locale": template["locale"],
            "procedure_code": template["procedure_code"],
            "title": template["title"],
            "version": template["version"],
            "warning_signs": template["warning_signs"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_approved_templates() -> dict:
    fixture = Path(__file__).with_name("approved_aftercare_templates.v1.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    required_catalog_fields = ("catalog_version", "version", "approved_by", "approved_at")
    if not all(isinstance(data.get(field), str) and data[field].strip() for field in required_catalog_fields):
        raise RuntimeError("Approved aftercare catalog requires version and approval provenance")
    if data["version"] != data["catalog_version"]:
        raise RuntimeError("Approved aftercare catalog version aliases must match")
    try:
        date.fromisoformat(data["approved_at"])
    except ValueError as error:
        raise RuntimeError("Approved aftercare catalog approved_at must be an ISO date") from error

    templates = data.get("templates")
    if not isinstance(templates, list) or not templates:
        raise RuntimeError("Approved aftercare catalog must contain templates")

    seen_refs = set()
    seen_pairs = set()
    required_item_strings = (
        "template_ref",
        "procedure_code",
        "locale",
        "version",
        "title",
        "care_instructions",
        "approval_status",
        "approved_by",
        "approved_at",
        "source",
        "source_url",
    )
    for item in templates:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) and item[field].strip() for field in required_item_strings
        ):
            raise RuntimeError("Each approved aftercare template requires content and provenance")
        pair = (item["procedure_code"], item["locale"])
        if item["template_ref"] in seen_refs or pair in seen_pairs:
            raise RuntimeError("Approved aftercare template references and procedure/locale pairs must be unique")
        if item["procedure_code"] not in PROCEDURE_CODES or item["locale"] not in SUPPORTED_LOCALES:
            raise RuntimeError("Approved aftercare template procedure or locale is not allowlisted")
        if item["approval_status"] != "APPROVED" or item.get("active") is not True:
            raise RuntimeError("Only active, approved aftercare templates may be loaded")
        if not isinstance(item.get("content_version"), int) or item["content_version"] < 1:
            raise RuntimeError("Approved aftercare template content_version must be positive")
        if not isinstance(item.get("warning_signs"), list) or not item["warning_signs"] or not all(
            isinstance(warning, str) and warning.strip() for warning in item["warning_signs"]
        ):
            raise RuntimeError("Each approved aftercare template requires warning signs")
        if not item["template_ref"].startswith(f"{data['catalog_version']}#"):
            raise RuntimeError("Approved aftercare template_ref must be catalog-scoped")
        if not item["source_url"].startswith("https://"):
            raise RuntimeError("Approved aftercare template provenance URL must use HTTPS")
        try:
            date.fromisoformat(item["approved_at"])
        except ValueError as error:
            raise RuntimeError("Approved aftercare template approved_at must be an ISO date") from error
        seen_refs.add(item["template_ref"])
        seen_pairs.add(pair)

    expected_pairs = {(procedure, locale) for procedure in PROCEDURE_CODES for locale in SUPPORTED_LOCALES}
    if seen_pairs != expected_pairs:
        raise RuntimeError("Approved aftercare catalog requires one Vietnamese and English template per procedure")
    return data


APPROVED_TEMPLATES = _load_approved_templates()


class TemplateItem(BaseModel):
    template_ref: str
    catalog_version: str
    procedure_code: Literal["EXTRACTION", "ROOT_CANAL", "IMPLANT", "FILLING", "CLEANING"]
    locale: Literal["vi", "en"]
    version: str
    content_version: int
    title: str
    care_instructions: str
    warning_signs: list[str]
    approval_status: Literal["APPROVED"]
    active: bool
    approved_by: str
    approved_at: date
    source: str
    source_url: str
    content_hash: str


class TemplateCatalogResponse(BaseModel):
    catalog_version: str
    templates: list[TemplateItem]


def list_approved_templates(
    locale: str | None = None,
    procedure_code: str | None = None,
) -> TemplateCatalogResponse:
    if locale is not None and locale not in SUPPORTED_LOCALES:
        raise AppError("TEMPLATE_LOCALE_INVALID", "Template locale is not supported", {"locale": locale}, 422)
    if procedure_code is not None and procedure_code not in PROCEDURE_CODES:
        raise AppError(
            "TEMPLATE_PROCEDURE_INVALID",
            "Template procedure is not supported",
            {"procedure_code": procedure_code},
            422,
        )

    items = []
    for template in APPROVED_TEMPLATES["templates"]:
        if locale and template["locale"] != locale:
            continue
        if procedure_code and template["procedure_code"] != procedure_code:
            continue
        items.append(TemplateItem(
            catalog_version=APPROVED_TEMPLATES["catalog_version"],
            content_hash=_content_hash(template),
            **template,
        ))
    return TemplateCatalogResponse(
        catalog_version=APPROVED_TEMPLATES["catalog_version"],
        templates=items,
    )
