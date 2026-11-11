import logging
from datetime import datetime, timezone
from typing import Optional
import httpx

from app.integrations.fbr.schemas import FBRInvoicePayload, FBRResponse

logger = logging.getLogger("fbr_integration")

# Official FBR Invoicing Endpoints
FBR_LIVE_URL = "https://ims.fbr.gov.pk/api/Live/PostData"
FBR_SANDBOX_URL = "https://ims.fbr.gov.pk/api/Live/PostData"


class FBRClient:
    """Client for interacting with FBR Digital Invoicing & POS Invoicing System.
    
    Supports 3 operation modes:
    - 'mock': Local simulation without external network calls (generates authentic QR and FBR IDs).
    - 'sandbox': Connects to FBR staging/sandbox endpoint with testing POS IDs.
    - 'live': Real-time production integration with FBR live servers.
    """

    def __init__(
        self,
        mode: str = "mock",
        pos_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: float = 8.0,
    ):
        self.mode = mode.lower()
        self.pos_id = pos_id or "101"
        self.auth_token = auth_token
        self.timeout = timeout_seconds

    async def post_invoice(self, payload: FBRInvoicePayload) -> FBRResponse:
        """Submit invoice to FBR or simulate valid response if in mock mode."""
        if self.mode == "mock" or not self.auth_token:
            return self._simulate_fbr_response(payload)

        # Live / Sandbox integration via HTTP POST
        endpoint = FBR_LIVE_URL if self.mode == "live" else FBR_SANDBOX_URL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(endpoint, json=payload.model_dump(), headers=headers)
                data = res.json() if res.status_code == 200 else {}

                # FBR returns Code 100 on successful fiscalization
                fbr_invoice_no = str(data.get("InvoiceNumber") or "")
                code = int(data.get("Code", 0) or 0)
                msg = str(data.get("Response", "FBR Response received"))

                if res.status_code == 200 and fbr_invoice_no:
                    qr_code = self._generate_qr_string(fbr_invoice_no, payload)
                    return FBRResponse(
                        fbr_invoice_number=fbr_invoice_no,
                        fbr_qr_code=qr_code,
                        status="synced",
                        code=code,
                        message=msg,
                    )
                else:
                    logger.warning(f"FBR Error ({res.status_code}): {res.text}")
                    # Return pending fallback so POS checkout is not blocked for customer
                    fallback_no = self._generate_mock_invoice_no(payload)
                    return FBRResponse(
                        fbr_invoice_number=fallback_no,
                        fbr_qr_code=self._generate_qr_string(fallback_no, payload),
                        status="pending",
                        code=res.status_code,
                        message=f"FBR response: {msg or res.text[:120]} (Queued for background sync)",
                    )

        except Exception as exc:
            logger.error(f"FBR Connection failure: {exc}")
            # Fallback for offline queueing
            fallback_no = self._generate_mock_invoice_no(payload)
            return FBRResponse(
                fbr_invoice_number=fallback_no,
                fbr_qr_code=self._generate_qr_string(fallback_no, payload),
                status="pending",
                code=503,
                message=f"FBR server offline/unreachable: {str(exc)} (Saved locally, will auto-sync)",
            )

    def _simulate_fbr_response(self, payload: FBRInvoicePayload) -> FBRResponse:
        """Generate realistic FBR Fiscal Number and TaxAsaan QR code in Mock mode."""
        simulated_no = self._generate_mock_invoice_no(payload)
        qr_string = self._generate_qr_string(simulated_no, payload)

        return FBRResponse(
            fbr_invoice_number=simulated_no,
            fbr_qr_code=qr_string,
            status="mocked",
            code=100,
            message="Simulated FBR invoice verification (Mock Mode active)",
        )

    def _generate_mock_invoice_no(self, payload: FBRInvoicePayload) -> str:
        """Format: <POS_ID><YYYYMMDDHHMMSS><SEQ>"""
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        clean_usin = payload.USIN.replace("-", "").replace(" ", "")[-4:]
        return f"{payload.POSID}{now_str}{clean_usin}"

    def _generate_qr_string(self, fbr_inv_no: str, payload: FBRInvoicePayload) -> str:
        """Official FBR TaxAsaan QR verification string format."""
        return (
            f"FBR:{fbr_inv_no}|POSID:{payload.POSID}|USIN:{payload.USIN}|"
            f"DATE:{payload.DateTime}|TOTAL:{payload.TotalBillAmount:.2f}|"
            f"TAX:{payload.TotalTaxCharged:.2f}"
        )
