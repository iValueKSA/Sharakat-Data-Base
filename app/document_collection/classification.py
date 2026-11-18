"""Canonical collection semantics, mapped to the existing Documents MVP enums."""

ACCESS_CLASSIFICATIONS = {
    "PUBLIC_DIRECT_DOWNLOAD": {"access_status": "PUBLIC_DIRECT_DOWNLOAD", "rights_status": "DIRECT_LINK_APPROVED", "link_verification_status": "VERIFIED_PUBLIC"},
    "OFFICIAL_DOCUMENT_PAGE": {"access_status": "PUBLIC_SOURCE_PAGE", "rights_status": "SOURCE_PAGE_LINK_ONLY", "link_verification_status": "VERIFIED_SOURCE_PAGE"},
    "VERIFIED_BOOKLET_WITH_SOURCE_PAGE_FALLBACK": {"access_status": "PUBLIC_SOURCE_PAGE", "rights_status": "SOURCE_PAGE_LINK_ONLY", "link_verification_status": "VERIFIED_SOURCE_PAGE", "direct_download_status": "UNAVAILABLE"},
    "LOGIN_REQUIRED": {"access_status": "LOGIN_REQUIRED", "rights_status": "SOURCE_PAGE_LINK_ONLY"},
    "PAYMENT_REQUIRED_FOR_DOCUMENT": {"access_status": "PAYMENT_REQUIRED_FOR_DOCUMENT", "rights_status": "SOURCE_PAGE_LINK_ONLY"},
    "PURCHASE_REQUIRED_FOR_PARTICIPATION": {"participation_requirement": "PURCHASE_REQUIRED_FOR_PARTICIPATION"},
    "DIRECT_DOWNLOAD_UNAVAILABLE": {"access_status": "PUBLIC_SOURCE_PAGE", "rights_status": "SOURCE_PAGE_LINK_ONLY", "link_verification_status": "VERIFIED_SOURCE_PAGE", "direct_download_status": "UNAVAILABLE"},
    "RESTRICTED": {"access_status": "RESTRICTED", "rights_status": "RESTRICTED"},
    "ACCESS_UNVERIFIED": {"access_status": "UNKNOWN", "rights_status": "UNVERIFIED"},
    "TEMPORARILY_UNREACHABLE": {"freshness_status": "TEMPORARILY_UNREACHABLE", "retain_last_verified_values": True},
}

DOCUMENT_CATEGORY_LABELS_AR = {
    "TERMS_AND_CONDITIONS_BOOKLET": "كراسة الشروط والمواصفات",
    "DRAFT_CONTRACT": "مسودة العقد",
    "APPLICATION_FORM": "نموذج التقديم",
    "TECHNICAL_SPECIFICATIONS": "المواصفات الفنية",
    "INVESTMENT_GUIDE": "دليل المستثمر",
    "OFFICIAL_DRAWINGS": "الرسومات الرسمية",
    "SITE_PLAN": "مخطط الموقع",
    "OTHER_OFFICIAL_ATTACHMENT": "مرفق رسمي آخر",
    "UNKNOWN_DOCUMENT_TYPE": "نوع مستند غير مؤكد",
}

