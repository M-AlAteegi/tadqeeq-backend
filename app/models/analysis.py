from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    type: str
    has_arabic: bool
    word_count: int


class DocumentMetadata(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    page_count: int = 0
    char_count: int = 0
    summary: DocumentSummary | None = None
    has_compliance: bool = False
    has_brief: bool = False


class DocumentListItem(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    page_count: int = 0
    char_count: int = 0
    has_compliance: bool = False
    has_brief: bool = False


class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]


class ComplianceRequest(BaseModel):
    strictness: str = Field(default="standard", pattern="^(standard|critical_only)$")


class ComplianceLocalized(BaseModel):
    name: str
    regulation: str
    description: str
    detail: str


class ComplianceCheck(BaseModel):
    id: str
    status: str
    found_keywords: list[str]
    pass_reason: str
    name: str
    regulation: str
    description: str
    detail: str
    localized: dict[str, ComplianceLocalized]


class ComplianceSummary(BaseModel):
    compliant: int
    warnings: int
    missing: int


class ComplianceResult(BaseModel):
    filename: str
    timestamp: str
    doc_language: str
    score: int
    summary: ComplianceSummary
    checks: list[ComplianceCheck]


class BriefRequest(BaseModel):
    report_language: str = Field(default="auto", pattern="^(auto|en|ar|bilingual)$")


class BriefResult(BaseModel):
    report: str
    localized: dict[str, str]
    primary: str
    language: str
