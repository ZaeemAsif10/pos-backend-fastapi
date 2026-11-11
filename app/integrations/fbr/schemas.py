from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class FBRInvoiceItemPayload(BaseModel):
    """Line item in FBR official format."""
    ItemCode: str = Field(..., description="Product SKU or barcode")
    ItemName: str = Field(..., description="Product title/description")
    PCTCode: str = Field("0000.0000", description="Pakistan Customs Tariff HS Code")
    Quantity: float = Field(..., gt=0)
    TaxRate: float = Field(0.0)
    SaleValue: float = Field(..., description="Gross sale value excluding tax")
    TaxCharged: float = Field(0.0, description="Calculated sales tax")
    Discount: float = Field(0.0, description="Discount amount")
    FurtherTax: float = Field(0.0, description="Further tax for unregistered buyers")
    TotalAmount: float = Field(..., description="Net total payable for line")
    InvoiceType: int = Field(1, description="1: Normal, 2: Debit Note, 3: Credit Note")


class FBRInvoicePayload(BaseModel):
    """Full FBR Invoice Payload as specified by FBR IMS API."""
    InvoiceNumber: Optional[str] = None
    POSID: int = Field(..., description="FBR registered POS terminal ID")
    USIN: str = Field(..., description="Unique Sequential Invoice Number from ERP")
    DateTime: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    BuyerNTN: Optional[str] = None
    BuyerCNIC: Optional[str] = None
    BuyerName: Optional[str] = "Walk-in Retail Buyer"
    BuyerPhoneNumber: Optional[str] = None
    TotalSaleValue: float = Field(...)
    TotalQuantity: float = Field(...)
    TotalTaxCharged: float = Field(0.0)
    TotalBillAmount: float = Field(...)
    Discount: float = Field(0.0)
    PaymentMode: int = Field(1, description="1: Cash, 2: Card, 3: Cheque, 4: Credit, 5: Mixed")
    InvoiceType: int = Field(1, description="1: Retail Sale, 2: Wholesale B2B")
    Items: List[FBRInvoiceItemPayload] = Field(default_factory=list)


class FBRResponse(BaseModel):
    """Normalized response returned from FBR Client."""
    fbr_invoice_number: str
    fbr_qr_code: str
    status: str = "synced"  # mocked, synced, pending, failed
    code: int = 100
    message: str = "Invoice successfully integrated with FBR"
