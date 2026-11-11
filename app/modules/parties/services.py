from typing import Optional, List, Dict, Any
from datetime import datetime, date, timezone, timedelta
from fastapi import HTTPException, status
from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.parties.models import DeliveryArea, Customer, Supplier, CustomerPayment, SupplierPayment
from app.modules.auth.models import User
from app.modules.branches.models import Branch
from app.modules.sales.models import SalesInvoice
from app.modules.inventory.models import Purchase
from app.modules.parties.schemas import (
    DeliveryAreaCreate,
    DeliveryAreaUpdate,
    DeliveryAreaResponse,
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerStatsResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    SupplierStatsResponse,
    CustomerPaymentCreate,
    CustomerPaymentResponse,
    PaginatedCustomerPaymentsResponse,
    CustomerLedgerEntry,
    CustomerLedgerSummary,
    CustomerLedgerResponse,
    SupplierPaymentCreate,
    SupplierPaymentResponse,
    PaginatedSupplierPaymentsResponse,
    SupplierLedgerEntry,
    SupplierLedgerSummary,
    SupplierLedgerResponse,
    AgingBucketBreakdown,
    CustomerAgingItem,
    CustomerAgingSummaryKPI,
    CustomerAgingReportResponse,
    SupplierAgingItem,
    SupplierAgingSummaryKPI,
    SupplierAgingReportResponse,
)





# ==========================================
# DELIVERY AREA SERVICE
# ==========================================
class DeliveryAreaService:
    @staticmethod
    async def list_delivery_areas(db: AsyncSession, tenant_id: int) -> List[DeliveryAreaResponse]:
        """List all delivery areas for a tenant with customer counts and salesman info."""
        # Subquery or outerjoin for customer count
        stmt = (
            select(
                DeliveryArea,
                func.count(Customer.id).label("customer_count"),
            )
            .outerjoin(Customer, Customer.area_id == DeliveryArea.id)
            .options(joinedload(DeliveryArea.assigned_salesman))
            .where(DeliveryArea.tenant_id == tenant_id)
            .group_by(DeliveryArea.id)
            .order_by(DeliveryArea.name.asc())
        )
        res = await db.execute(stmt)
        results = []
        for area, count in res.unique().all():
            resp = DeliveryAreaResponse.model_validate(area)
            resp.customer_count = count
            resp.assigned_salesman_name = (
                area.assigned_salesman.full_name
                if area.assigned_salesman
                else None
            )
            results.append(resp)
        return results

    @staticmethod
    async def get_delivery_area(db: AsyncSession, tenant_id: int, area_id: int) -> DeliveryArea:
        stmt = select(DeliveryArea).where(
            DeliveryArea.tenant_id == tenant_id, DeliveryArea.id == area_id
        ).options(joinedload(DeliveryArea.assigned_salesman))
        res = await db.execute(stmt)
        area = res.scalar_one_or_none()
        if not area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Delivery Area with ID {area_id} was not found.",
            )
        return area

    @staticmethod
    async def create_delivery_area(
        db: AsyncSession, tenant_id: int, payload: DeliveryAreaCreate
    ) -> DeliveryAreaResponse:
        # Check duplicate code or name
        dup_stmt = select(DeliveryArea).where(
            DeliveryArea.tenant_id == tenant_id,
            or_(
                func.lower(DeliveryArea.code) == payload.code.strip().lower(),
                func.lower(DeliveryArea.name) == payload.name.strip().lower(),
            ),
        )
        res = await db.execute(dup_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A delivery area with this code or name already exists.",
            )

        area = DeliveryArea(
            tenant_id=tenant_id,
            code=payload.code.strip().upper(),
            name=payload.name.strip(),
            city=payload.city.strip(),
            description=payload.description.strip() if payload.description else None,
            delivery_days=payload.delivery_days.strip() if payload.delivery_days else None,
            assigned_salesman_id=payload.assigned_salesman_id,
            is_active=payload.is_active,
        )
        db.add(area)
        await db.commit()
        await db.refresh(area)

        # Load salesman name if assigned
        salesman_name = None
        if area.assigned_salesman_id:
            salesman_res = await db.execute(
                select(User).where(User.id == area.assigned_salesman_id)
            )
            u = salesman_res.scalar_one_or_none()
            if u:
                salesman_name = u.full_name

        resp = DeliveryAreaResponse.model_validate(area)
        resp.assigned_salesman_name = salesman_name
        resp.customer_count = 0
        return resp

    @staticmethod
    async def update_delivery_area(
        db: AsyncSession, tenant_id: int, area_id: int, payload: DeliveryAreaUpdate
    ) -> DeliveryAreaResponse:
        area = await DeliveryAreaService.get_delivery_area(db, tenant_id, area_id)

        # Check duplicate code/name if changed
        if payload.code or payload.name:
            code_check = payload.code.strip().lower() if payload.code else None
            name_check = payload.name.strip().lower() if payload.name else None
            conds = []
            if code_check:
                conds.append(func.lower(DeliveryArea.code) == code_check)
            if name_check:
                conds.append(func.lower(DeliveryArea.name) == name_check)

            dup_stmt = select(DeliveryArea).where(
                DeliveryArea.tenant_id == tenant_id,
                DeliveryArea.id != area_id,
                or_(*conds),
            )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Another delivery area already has this code or name.",
                )

        if payload.code is not None:
            area.code = payload.code.strip().upper()
        if payload.name is not None:
            area.name = payload.name.strip()
        if payload.city is not None:
            area.city = payload.city.strip()
        if payload.description is not None:
            area.description = payload.description.strip() if payload.description else None
        if payload.delivery_days is not None:
            area.delivery_days = payload.delivery_days.strip() if payload.delivery_days else None
        if payload.assigned_salesman_id is not None:
            area.assigned_salesman_id = (
                payload.assigned_salesman_id if payload.assigned_salesman_id > 0 else None
            )
        if payload.is_active is not None:
            area.is_active = payload.is_active

        area.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(area)

        # Get customer count
        cnt_res = await db.execute(
            select(func.count(Customer.id)).where(Customer.area_id == area_id)
        )
        c_count = cnt_res.scalar() or 0

        salesman_name = None
        if area.assigned_salesman_id:
            salesman_res = await db.execute(
                select(User).where(User.id == area.assigned_salesman_id)
            )
            u = salesman_res.scalar_one_or_none()
            if u:
                salesman_name = u.full_name

        resp = DeliveryAreaResponse.model_validate(area)
        resp.assigned_salesman_name = salesman_name
        resp.customer_count = c_count
        return resp

    @staticmethod
    async def delete_delivery_area(db: AsyncSession, tenant_id: int, area_id: int) -> Dict[str, Any]:
        area = await DeliveryAreaService.get_delivery_area(db, tenant_id, area_id)

        # Check if any customers are assigned to this route
        cust_cnt = await db.execute(
            select(func.count(Customer.id)).where(Customer.area_id == area_id)
        )
        assigned_count = cust_cnt.scalar() or 0
        if assigned_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete delivery area '{area.name}'. {assigned_count} customers are assigned to it. Please reassign them first.",
            )

        area_name = area.name
        await db.delete(area)
        await db.commit()
        return {"message": f"Delivery area '{area_name}' deleted successfully."}


# ==========================================
# CUSTOMER SERVICE
# ==========================================
class CustomerService:
    @staticmethod
    async def get_customer_stats(db: AsyncSession, tenant_id: int) -> CustomerStatsResponse:
        """Calculate KPI statistics for customers."""
        total_stmt = select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
        total_res = await db.execute(total_stmt)
        total_customers = total_res.scalar() or 0

        recv_stmt = select(func.coalesce(func.sum(Customer.current_balance), 0)).where(
            Customer.tenant_id == tenant_id, Customer.current_balance > 0
        )
        recv_res = await db.execute(recv_stmt)
        total_receivables = float(recv_res.scalar() or 0.0)

        overdue_stmt = select(func.count(Customer.id)).where(
            Customer.tenant_id == tenant_id, Customer.current_balance > Customer.credit_limit, Customer.credit_limit > 0
        )
        overdue_res = await db.execute(overdue_stmt)
        overdue_accounts = overdue_res.scalar() or 0

        blocked_stmt = select(func.count(Customer.id)).where(
            Customer.tenant_id == tenant_id, Customer.is_credit_blocked.is_(True)
        )
        blocked_res = await db.execute(blocked_stmt)
        blocked_count = blocked_res.scalar() or 0

        return CustomerStatsResponse(
            total_customers=total_customers,
            total_receivables=total_receivables,
            overdue_accounts=overdue_accounts,
            credit_blocked_count=blocked_count,
        )

    @staticmethod
    async def list_customers(
        db: AsyncSession,
        tenant_id: int,
        search: Optional[str] = None,
        area_id: Optional[int] = None,
        customer_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: Optional[int] = None,
        size: Optional[int] = None,
    ):
        """List customers with optional filters and server pagination."""
        stmt = (
            select(Customer)
            .options(
                joinedload(Customer.area),
                joinedload(Customer.branch),
            )
            .where(Customer.tenant_id == tenant_id)
        )

        if area_id:
            stmt = stmt.where(Customer.area_id == area_id)
        if customer_type:
            stmt = stmt.where(Customer.customer_type == customer_type)
        if is_active is not None:
            stmt = stmt.where(Customer.is_active == is_active)
        if search:
            s = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Customer.business_name).ilike(s),
                    func.lower(Customer.owner_name).ilike(s),
                    func.lower(Customer.code).ilike(s),
                    Customer.phone.ilike(s),
                    Customer.city.ilike(s),
                )
            )

        if page is not None or size is not None:
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total_res = await db.execute(count_stmt)
            total = total_res.scalar_one_or_none() or 0

            p = page or 1
            s = size or 10
            if s > 100:
                s = 100
            paginated_stmt = stmt.order_by(Customer.business_name.asc()).offset((p - 1) * s).limit(s)
            res = await db.execute(paginated_stmt)
            customers = res.unique().scalars().all()

            results = []
            for c in customers:
                resp = CustomerResponse.model_validate(c)
                resp.area_name = c.area.name if c.area else None
                resp.branch_name = c.branch.name if c.branch else None
                results.append(resp)

            total_pages = (total + s - 1) // s if total > 0 else 1
            return results, total, p, s, total_pages

        stmt = stmt.order_by(Customer.business_name.asc())
        res = await db.execute(stmt)
        customers = res.unique().scalars().all()

        results = []
        for c in customers:
            resp = CustomerResponse.model_validate(c)
            resp.area_name = c.area.name if c.area else None
            resp.branch_name = c.branch.name if c.branch else None
            results.append(resp)
        return results

    @staticmethod
    async def get_customer(db: AsyncSession, tenant_id: int, customer_id: int) -> Customer:
        stmt = (
            select(Customer)
            .options(
                joinedload(Customer.area),
                joinedload(Customer.branch),
            )
            .where(Customer.tenant_id == tenant_id, Customer.id == customer_id)
        )
        res = await db.execute(stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer with ID {customer_id} was not found.",
            )
        return customer

    @staticmethod
    async def create_customer(
        db: AsyncSession, tenant_id: int, payload: CustomerCreate
    ) -> CustomerResponse:
        # Check duplicate code
        dup_stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            func.lower(Customer.code) == payload.code.strip().lower(),
        )
        res = await db.execute(dup_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Customer code '{payload.code}' is already in use.",
            )

        customer = Customer(
            tenant_id=tenant_id,
            code=payload.code.strip().upper(),
            business_name=payload.business_name.strip(),
            owner_name=payload.owner_name.strip() if payload.owner_name else None,
            phone=payload.phone.strip(),
            whatsapp_number=payload.whatsapp_number.strip() if payload.whatsapp_number else None,
            email=payload.email.strip().lower() if payload.email else None,
            cnic=payload.cnic.strip() if payload.cnic else None,
            ntn=payload.ntn.strip() if payload.ntn else None,
            strn=payload.strn.strip() if payload.strn else None,
            customer_type=payload.customer_type,
            credit_limit=payload.credit_limit,
            credit_days=payload.credit_days,
            opening_balance=payload.opening_balance,
            current_balance=payload.opening_balance,  # Starting balance equals opening balance
            is_credit_blocked=False,
            area_id=payload.area_id,
            branch_id=payload.branch_id,
            city=payload.city.strip(),
            address=payload.address.strip() if payload.address else None,
            kyc_status=payload.kyc_status,
            is_active=payload.is_active,
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)

        area_name = None
        if customer.area_id:
            a_res = await db.execute(select(DeliveryArea).where(DeliveryArea.id == customer.area_id))
            a = a_res.scalar_one_or_none()
            if a:
                area_name = a.name

        branch_name = None
        if customer.branch_id:
            b_res = await db.execute(select(Branch).where(Branch.id == customer.branch_id))
            b = b_res.scalar_one_or_none()
            if b:
                branch_name = b.name

        resp = CustomerResponse.model_validate(customer)
        resp.area_name = area_name
        resp.branch_name = branch_name
        return resp

    @staticmethod
    async def update_customer(
        db: AsyncSession, tenant_id: int, customer_id: int, payload: CustomerUpdate
    ) -> CustomerResponse:
        customer = await CustomerService.get_customer(db, tenant_id, customer_id)

        if payload.code:
            dup_stmt = select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.id != customer_id,
                func.lower(Customer.code) == payload.code.strip().lower(),
            )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Customer code '{payload.code}' is already used by another customer.",
                )
            customer.code = payload.code.strip().upper()

        if payload.business_name is not None:
            customer.business_name = payload.business_name.strip()
        if payload.owner_name is not None:
            customer.owner_name = payload.owner_name.strip() if payload.owner_name else None
        if payload.phone is not None:
            customer.phone = payload.phone.strip()
        if payload.whatsapp_number is not None:
            customer.whatsapp_number = payload.whatsapp_number.strip() if payload.whatsapp_number else None
        if payload.email is not None:
            customer.email = payload.email.strip().lower() if payload.email else None
        if payload.cnic is not None:
            customer.cnic = payload.cnic.strip() if payload.cnic else None
        if payload.ntn is not None:
            customer.ntn = payload.ntn.strip() if payload.ntn else None
        if payload.strn is not None:
            customer.strn = payload.strn.strip() if payload.strn else None
        if payload.customer_type is not None:
            customer.customer_type = payload.customer_type
        if payload.credit_limit is not None:
            customer.credit_limit = payload.credit_limit
        if payload.credit_days is not None:
            customer.credit_days = payload.credit_days
        if payload.opening_balance is not None:
            diff = payload.opening_balance - float(customer.opening_balance)
            customer.opening_balance = payload.opening_balance
            customer.current_balance = float(customer.current_balance) + diff
        if payload.is_credit_blocked is not None:
            customer.is_credit_blocked = payload.is_credit_blocked
        if payload.area_id is not None:
            customer.area_id = payload.area_id if payload.area_id > 0 else None
        if payload.branch_id is not None:
            customer.branch_id = payload.branch_id if payload.branch_id > 0 else None
        if payload.city is not None:
            customer.city = payload.city.strip()
        if payload.address is not None:
            customer.address = payload.address.strip() if payload.address else None
        if payload.kyc_status is not None:
            customer.kyc_status = payload.kyc_status
        if payload.is_active is not None:
            customer.is_active = payload.is_active

        customer.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)

        area_name = customer.area.name if customer.area else None
        branch_name = customer.branch.name if customer.branch else None

        resp = CustomerResponse.model_validate(customer)
        resp.area_name = area_name
        resp.branch_name = branch_name
        return resp

    @staticmethod
    async def delete_customer(db: AsyncSession, tenant_id: int, customer_id: int) -> Dict[str, Any]:
        customer = await CustomerService.get_customer(db, tenant_id, customer_id)

        if float(customer.current_balance) != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete customer '{customer.business_name}'. Account has an outstanding balance of PKR {customer.current_balance:,.2f}. Please settle balance first.",
            )

        name = customer.business_name
        await db.delete(customer)
        await db.commit()
        return {"message": f"Customer '{name}' deleted successfully."}

    @staticmethod
    async def get_customer_ledger(
        db: AsyncSession,
        tenant_id: int,
        customer_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> CustomerLedgerResponse:
        customer = await CustomerService.get_customer(db, tenant_id, customer_id)

        # 1. Fetch sales invoices for this customer
        inv_stmt = (
            select(SalesInvoice)
            .where(
                SalesInvoice.tenant_id == tenant_id,
                SalesInvoice.customer_id == customer_id,
                SalesInvoice.status != "cancelled",
            )
            .order_by(SalesInvoice.invoice_date.asc())
        )
        inv_res = await db.execute(inv_stmt)
        invoices = inv_res.scalars().all()

        # 2. Fetch customer recovery payments
        pmt_stmt = (
            select(CustomerPayment)
            .where(
                CustomerPayment.tenant_id == tenant_id,
                CustomerPayment.customer_id == customer_id,
            )
            .order_by(CustomerPayment.created_at.asc())
        )
        pmt_res = await db.execute(pmt_stmt)
        payments = pmt_res.scalars().all()

        # 3. Interleave events
        raw_events = []
        for inv in invoices:
            dt = inv.invoice_date or inv.created_at
            if inv.sale_type == "return_credit_note":
                raw_events.append({
                    "id": inv.id,
                    "type": "credit_note",
                    "date": dt,
                    "ref": inv.invoice_number,
                    "desc": "Sales Return / Credit Note",
                    "debit": float(inv.paid_amount),
                    "credit": float(inv.total_amount),
                    "method": inv.payment_method,
                    "notes": inv.notes,
                })
            else:
                raw_events.append({
                    "id": inv.id,
                    "type": "invoice",
                    "date": dt,
                    "ref": inv.invoice_number,
                    "desc": f"Sales Invoice ({inv.sale_type.replace('_', ' ').title()})" + (" [Refunded]" if inv.status == "refunded" else ""),
                    "debit": float(inv.total_amount),
                    "credit": float(inv.paid_amount),
                    "method": inv.payment_method,
                    "notes": inv.notes,
                })
                if inv.status == "refunded":
                    ref_dt = inv.updated_at or dt
                    raw_events.append({
                        "id": inv.id,
                        "type": "credit_note",
                        "date": ref_dt,
                        "ref": f"CN-{inv.invoice_number}",
                        "desc": f"Credit Note / Return against {inv.invoice_number}",
                        "debit": float(inv.paid_amount),
                        "credit": float(inv.total_amount),
                        "method": inv.payment_method,
                        "notes": inv.notes or "Sales Return / Refund",
                    })

        for pmt in payments:
            raw_events.append({
                "id": pmt.id,
                "type": "payment",
                "date": pmt.created_at,
                "ref": pmt.voucher_number,
                "desc": f"Cash Receipt Voucher ({pmt.payment_method.title()})",
                "debit": 0.0,
                "credit": float(pmt.amount),
                "method": pmt.payment_method,
                "notes": pmt.notes or pmt.reference_number,
            })

        raw_events.sort(key=lambda x: x["date"])

        # 4. Calculate running balance
        running = float(customer.opening_balance)
        period_opening = float(customer.opening_balance)
        entries: List[CustomerLedgerEntry] = []
        total_debit = 0.0
        total_credit = 0.0

        for ev in raw_events:
            ev_date = ev["date"]
            net_change = ev["debit"] - ev["credit"]
            running = round(running + net_change, 2)

            if from_date and ev_date < from_date:
                period_opening = running
                continue

            if to_date and ev_date > to_date:
                continue

            total_debit += ev["debit"]
            total_credit += ev["credit"]

            entries.append(
                CustomerLedgerEntry(
                    id=ev["id"],
                    entry_type=ev["type"],
                    date=ev_date,
                    reference=ev["ref"],
                    description=ev["desc"],
                    debit=round(ev["debit"], 2),
                    credit=round(ev["credit"], 2),
                    balance=round(running, 2),
                    payment_method=ev["method"],
                    notes=ev["notes"],
                )
            )

        summary = CustomerLedgerSummary(
            opening_balance=round(period_opening, 2),
            total_debit=round(total_debit, 2),
            total_credit=round(total_credit, 2),
            closing_balance=round(running, 2),
            credit_limit=float(customer.credit_limit),
            is_credit_blocked=customer.is_credit_blocked,
        )

        return CustomerLedgerResponse(
            customer_id=customer.id,
            customer_name=customer.business_name,
            customer_code=customer.code,
            customer_phone=customer.phone,
            from_date=from_date,
            to_date=to_date,
            summary=summary,
            entries=entries,
        )

    @staticmethod
    async def toggle_credit_block(
        db: AsyncSession,
        tenant_id: int,
        customer_id: int,
    ) -> CustomerResponse:
        """Freeze or unfreeze customer credit."""
        stmt = select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        res = await db.execute(stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found.")

        customer.is_credit_blocked = not customer.is_credit_blocked
        customer.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        return CustomerResponse.model_validate(customer)

    @staticmethod
    async def get_receivables_aging(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        search: Optional[str] = None,
        filter_type: Optional[str] = None,  # "all", "overdue", "high_risk"
    ) -> CustomerAgingReportResponse:
        """
        Compute standard 5-bucket accounts receivable aging analysis per customer.
        Buckets: Current (0-30d), 31-60d, 61-90d, 91-120d, >120d.
        """
        today = as_of_date or datetime.now(timezone.utc).date()

        # 1. Fetch all active customers for tenant
        cust_stmt = (
            select(Customer)
            .options(joinedload(Customer.area))
            .where(Customer.tenant_id == tenant_id, Customer.is_active == True)
        )
        if branch_id:
            cust_stmt = cust_stmt.where(or_(Customer.branch_id == branch_id, Customer.branch_id.is_(None)))
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            cust_stmt = cust_stmt.where(
                or_(
                    func.lower(Customer.business_name).like(s),
                    func.lower(Customer.owner_name).like(s),
                    Customer.phone.like(s),
                    func.lower(Customer.code).like(s),
                )
            )
        cust_res = await db.execute(cust_stmt)
        customers = cust_res.scalars().all()
        if not customers:
            return CustomerAgingReportResponse(
                as_of_date=today,
                branch_id=branch_id,
                summary=CustomerAgingSummaryKPI(),
                customers=[],
            )

        customer_ids = [c.id for c in customers]

        # 2. Fetch all unpaid/partially paid sales invoices
        inv_stmt = (
            select(SalesInvoice)
            .where(
                SalesInvoice.tenant_id == tenant_id,
                SalesInvoice.customer_id.in_(customer_ids),
                SalesInvoice.status.notin_(["cancelled", "refunded"]),
                SalesInvoice.balance_due > 0,
            )
            .order_by(SalesInvoice.invoice_date.asc())
        )
        if branch_id:
            inv_stmt = inv_stmt.where(SalesInvoice.branch_id == branch_id)
        inv_res = await db.execute(inv_stmt)
        invoices = inv_res.scalars().all()

        invoices_by_customer: Dict[int, List[SalesInvoice]] = {}
        for inv in invoices:
            if inv.customer_id:
                invoices_by_customer.setdefault(inv.customer_id, []).append(inv)

        # 3. Fetch last payment for each customer
        last_pay_subq = (
            select(
                CustomerPayment.customer_id,
                func.max(CustomerPayment.created_at).label("max_date")
            )
            .where(CustomerPayment.tenant_id == tenant_id, CustomerPayment.customer_id.in_(customer_ids))
            .group_by(CustomerPayment.customer_id)
            .subquery()
        )
        last_pay_stmt = (
            select(CustomerPayment)
            .join(
                last_pay_subq,
                and_(
                    CustomerPayment.customer_id == last_pay_subq.c.customer_id,
                    CustomerPayment.created_at == last_pay_subq.c.max_date,
                ),
            )
        )
        last_pay_res = await db.execute(last_pay_stmt)
        last_payments = {p.customer_id: p for p in last_pay_res.scalars().all()}

        # 4. Compute aging buckets per customer
        aging_items: List[CustomerAgingItem] = []
        tot_receivables = 0.0
        tot_current = 0.0
        tot_overdue = 0.0
        tot_30_plus = 0.0
        tot_60_plus = 0.0
        tot_90_plus = 0.0
        overdue_cust_count = 0
        high_risk_cust_count = 0

        for c in customers:
            c_invoices = invoices_by_customer.get(c.id, [])
            c_balance = float(c.current_balance or 0.0)

            b_current = 0.0
            b_31_60 = 0.0
            b_61_90 = 0.0
            b_91_120 = 0.0
            b_over_120 = 0.0
            oldest_days = 0

            invoices_sum = sum(float(inv.balance_due) for inv in c_invoices)

            for inv in c_invoices:
                inv_date = inv.invoice_date.date() if isinstance(inv.invoice_date, datetime) else inv.invoice_date
                days_old = max(0, (today - inv_date).days)
                oldest_days = max(oldest_days, days_old)
                amt = float(inv.balance_due)

                if days_old <= 30:
                    b_current += amt
                elif days_old <= 60:
                    b_31_60 += amt
                elif days_old <= 90:
                    b_61_90 += amt
                elif days_old <= 120:
                    b_91_120 += amt
                else:
                    b_over_120 += amt

            residual = c_balance - invoices_sum
            if residual > 0.01:
                days_acct = max(0, (today - c.created_at.date()).days)
                oldest_days = max(oldest_days, days_acct)
                if days_acct <= 30:
                    b_current += residual
                elif days_acct <= 60:
                    b_31_60 += residual
                elif days_acct <= 90:
                    b_61_90 += residual
                elif days_acct <= 120:
                    b_91_120 += residual
                else:
                    b_over_120 += residual

            c_total = round(b_current + b_31_60 + b_61_90 + b_91_120 + b_over_120, 2)
            c_overdue = round(b_31_60 + b_61_90 + b_91_120 + b_over_120, 2)

            if c_total <= 0 and c_balance <= 0:
                continue

            if filter_type == "overdue" and c_overdue <= 0:
                continue
            if filter_type == "high_risk" and (b_91_120 + b_over_120 <= 0 and oldest_days <= 90):
                continue

            last_p = last_payments.get(c.id)

            item = CustomerAgingItem(
                customer_id=c.id,
                code=c.code,
                business_name=c.business_name,
                owner_name=c.owner_name,
                phone=c.phone,
                whatsapp_number=c.whatsapp_number or c.phone,
                area_name=c.area.name if c.area else None,
                credit_limit=float(c.credit_limit or 0.0),
                credit_days=int(c.credit_days or 0),
                is_credit_blocked=bool(c.is_credit_blocked),
                current_balance=round(c_balance, 2),
                total_receivable=c_total,
                aging=AgingBucketBreakdown(
                    current=round(b_current, 2),
                    days_31_60=round(b_31_60, 2),
                    days_61_90=round(b_61_90, 2),
                    days_91_120=round(b_91_120, 2),
                    over_120=round(b_over_120, 2),
                    total=c_total,
                ),
                overdue_amount=c_overdue,
                oldest_unpaid_days=oldest_days,
                last_payment_date=last_p.created_at if last_p else None,
                last_payment_amount=float(last_p.amount) if last_p else None,
            )
            aging_items.append(item)

            tot_receivables += c_total
            tot_current += b_current
            tot_overdue += c_overdue
            tot_30_plus += b_31_60
            tot_60_plus += b_61_90
            tot_90_plus += (b_91_120 + b_over_120)
            if c_overdue > 0:
                overdue_cust_count += 1
            if (b_91_120 + b_over_120) > 0 or oldest_days > 90:
                high_risk_cust_count += 1

        # 5. Days Sales Outstanding (DSO)
        ninety_days_ago = today - timedelta(days=90)
        sales_stmt = select(func.sum(SalesInvoice.total_amount)).where(
            SalesInvoice.tenant_id == tenant_id,
            SalesInvoice.status.notin_(["cancelled", "refunded"]),
            func.date(SalesInvoice.invoice_date) >= ninety_days_ago,
        )
        if branch_id:
            sales_stmt = sales_stmt.where(SalesInvoice.branch_id == branch_id)
        sales_res = await db.execute(sales_stmt)
        total_sales_90 = float(sales_res.scalar() or 0.0)

        dso = round((tot_receivables / total_sales_90) * 90, 1) if total_sales_90 > 0 else 0.0

        aging_items.sort(key=lambda x: (x.overdue_amount, x.total_receivable), reverse=True)

        return CustomerAgingReportResponse(
            as_of_date=today,
            branch_id=branch_id,
            summary=CustomerAgingSummaryKPI(
                total_receivables=round(tot_receivables, 2),
                total_current=round(tot_current, 2),
                total_overdue=round(tot_overdue, 2),
                total_overdue_30_plus=round(tot_30_plus, 2),
                total_overdue_60_plus=round(tot_60_plus, 2),
                total_overdue_90_plus=round(tot_90_plus, 2),
                days_sales_outstanding=dso,
                total_customers_count=len(aging_items),
                overdue_customers_count=overdue_cust_count,
                high_risk_customers_count=high_risk_cust_count,
            ),
            customers=aging_items,
        )



# ==========================================
# SUPPLIER SERVICE
# ==========================================
class SupplierService:
    @staticmethod
    async def get_supplier_stats(db: AsyncSession, tenant_id: int) -> SupplierStatsResponse:
        """Calculate KPI statistics for suppliers."""
        total_stmt = select(func.count(Supplier.id)).where(Supplier.tenant_id == tenant_id)
        total_res = await db.execute(total_stmt)
        total_suppliers = total_res.scalar() or 0

        pay_stmt = select(func.coalesce(func.sum(Supplier.current_balance), 0)).where(
            Supplier.tenant_id == tenant_id, Supplier.current_balance > 0
        )
        pay_res = await db.execute(pay_stmt)
        total_payables = float(pay_res.scalar() or 0.0)

        active_stmt = select(func.count(Supplier.id)).where(
            Supplier.tenant_id == tenant_id, Supplier.is_active.is_(True)
        )
        active_res = await db.execute(active_stmt)
        active_mills = active_res.scalar() or 0

        bank_stmt = select(func.count(Supplier.id)).where(
            Supplier.tenant_id == tenant_id,
            Supplier.bank_account_number.isnot(None),
            Supplier.bank_account_number != "",
        )
        bank_res = await db.execute(bank_stmt)
        bank_count = bank_res.scalar() or 0

        return SupplierStatsResponse(
            total_suppliers=total_suppliers,
            total_payables=total_payables,
            active_mills=active_mills,
            bank_accounts_count=bank_count,
        )

    @staticmethod
    async def list_suppliers(
        db: AsyncSession,
        tenant_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: Optional[int] = None,
        size: Optional[int] = None,
    ):
        """List suppliers with optional filters and server pagination."""
        stmt = select(Supplier).where(Supplier.tenant_id == tenant_id)

        if is_active is not None:
            stmt = stmt.where(Supplier.is_active == is_active)
        if search:
            s = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Supplier.company_name).ilike(s),
                    func.lower(Supplier.contact_person).ilike(s),
                    func.lower(Supplier.code).ilike(s),
                    Supplier.phone.ilike(s),
                    Supplier.city.ilike(s),
                )
            )

        if page is not None or size is not None:
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total_res = await db.execute(count_stmt)
            total = total_res.scalar_one_or_none() or 0

            p = page or 1
            s = size or 10
            if s > 100:
                s = 100
            paginated_stmt = stmt.order_by(Supplier.company_name.asc()).offset((p - 1) * s).limit(s)
            res = await db.execute(paginated_stmt)
            suppliers = res.scalars().all()
            total_pages = (total + s - 1) // s if total > 0 else 1
            return [SupplierResponse.model_validate(s) for s in suppliers], total, p, s, total_pages

        stmt = stmt.order_by(Supplier.company_name.asc())
        res = await db.execute(stmt)
        suppliers = res.scalars().all()
        return [SupplierResponse.model_validate(s) for s in suppliers]

    @staticmethod
    async def get_supplier(db: AsyncSession, tenant_id: int, supplier_id: int) -> Supplier:
        stmt = select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.id == supplier_id)
        res = await db.execute(stmt)
        supplier = res.scalar_one_or_none()
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supplier with ID {supplier_id} was not found.",
            )
        return supplier

    @staticmethod
    async def create_supplier(
        db: AsyncSession, tenant_id: int, payload: SupplierCreate
    ) -> SupplierResponse:
        # Check duplicate code
        dup_stmt = select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            func.lower(Supplier.code) == payload.code.strip().lower(),
        )
        res = await db.execute(dup_stmt)
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Supplier code '{payload.code}' is already in use.",
            )

        supplier = Supplier(
            tenant_id=tenant_id,
            code=payload.code.strip().upper(),
            company_name=payload.company_name.strip(),
            contact_person=payload.contact_person.strip() if payload.contact_person else None,
            phone=payload.phone.strip(),
            email=payload.email.strip().lower() if payload.email else None,
            ntn=payload.ntn.strip() if payload.ntn else None,
            strn=payload.strn.strip() if payload.strn else None,
            payment_terms_days=payload.payment_terms_days,
            opening_balance=payload.opening_balance,
            current_balance=payload.opening_balance,  # Opening balance is initial payable
            bank_name=payload.bank_name.strip() if payload.bank_name else None,
            bank_account_number=payload.bank_account_number.strip() if payload.bank_account_number else None,
            bank_iban=payload.bank_iban.strip() if payload.bank_iban else None,
            bank_branch=payload.bank_branch.strip() if payload.bank_branch else None,
            city=payload.city.strip(),
            address=payload.address.strip() if payload.address else None,
            is_active=payload.is_active,
        )
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)
        return SupplierResponse.model_validate(supplier)

    @staticmethod
    async def update_supplier(
        db: AsyncSession, tenant_id: int, supplier_id: int, payload: SupplierUpdate
    ) -> SupplierResponse:
        supplier = await SupplierService.get_supplier(db, tenant_id, supplier_id)

        if payload.code:
            dup_stmt = select(Supplier).where(
                Supplier.tenant_id == tenant_id,
                Supplier.id != supplier_id,
                func.lower(Supplier.code) == payload.code.strip().lower(),
            )
            dup_res = await db.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Supplier code '{payload.code}' is already used by another supplier.",
                )
            supplier.code = payload.code.strip().upper()

        if payload.company_name is not None:
            supplier.company_name = payload.company_name.strip()
        if payload.contact_person is not None:
            supplier.contact_person = payload.contact_person.strip() if payload.contact_person else None
        if payload.phone is not None:
            supplier.phone = payload.phone.strip()
        if payload.email is not None:
            supplier.email = payload.email.strip().lower() if payload.email else None
        if payload.ntn is not None:
            supplier.ntn = payload.ntn.strip() if payload.ntn else None
        if payload.strn is not None:
            supplier.strn = payload.strn.strip() if payload.strn else None
        if payload.payment_terms_days is not None:
            supplier.payment_terms_days = payload.payment_terms_days
        if payload.opening_balance is not None:
            diff = payload.opening_balance - float(supplier.opening_balance)
            supplier.opening_balance = payload.opening_balance
            supplier.current_balance = float(supplier.current_balance) + diff
        if payload.bank_name is not None:
            supplier.bank_name = payload.bank_name.strip() if payload.bank_name else None
        if payload.bank_account_number is not None:
            supplier.bank_account_number = payload.bank_account_number.strip() if payload.bank_account_number else None
        if payload.bank_iban is not None:
            supplier.bank_iban = payload.bank_iban.strip() if payload.bank_iban else None
        if payload.bank_branch is not None:
            supplier.bank_branch = payload.bank_branch.strip() if payload.bank_branch else None
        if payload.city is not None:
            supplier.city = payload.city.strip()
        if payload.address is not None:
            supplier.address = payload.address.strip() if payload.address else None
        if payload.is_active is not None:
            supplier.is_active = payload.is_active

        supplier.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(supplier)
        return SupplierResponse.model_validate(supplier)

    @staticmethod
    async def delete_supplier(db: AsyncSession, tenant_id: int, supplier_id: int) -> Dict[str, Any]:
        supplier = await SupplierService.get_supplier(db, tenant_id, supplier_id)

        if float(supplier.current_balance) != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete supplier '{supplier.company_name}'. Outstanding payable balance of PKR {supplier.current_balance:,.2f} exists. Settle dues first.",
            )

        name = supplier.company_name
        await db.delete(supplier)
        await db.commit()
        return {"message": f"Supplier '{name}' deleted successfully."}

    @staticmethod
    async def get_supplier_ledger(
        db: AsyncSession,
        tenant_id: int,
        supplier_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> SupplierLedgerResponse:
        supplier = await SupplierService.get_supplier(db, tenant_id, supplier_id)

        # 1. Fetch purchases
        purch_stmt = (
            select(Purchase)
            .where(
                Purchase.tenant_id == tenant_id,
                Purchase.supplier_id == supplier_id,
                Purchase.status != "cancelled",
            )
            .order_by(Purchase.created_at.asc())
        )
        purch_res = await db.execute(purch_stmt)
        purchases = purch_res.scalars().all()

        # 2. Fetch payments
        pmt_stmt = (
            select(SupplierPayment)
            .where(
                SupplierPayment.tenant_id == tenant_id,
                SupplierPayment.supplier_id == supplier_id,
            )
            .order_by(SupplierPayment.created_at.asc())
        )
        pmt_res = await db.execute(pmt_stmt)
        payments = pmt_res.scalars().all()

        # 3. Interleave events
        raw_events = []
        for p in purchases:
            raw_events.append({
                "id": p.id,
                "type": "purchase",
                "date": p.created_at,
                "ref": p.invoice_number + (f" ({p.supplier_bill_no})" if p.supplier_bill_no else ""),
                "desc": f"Goods Received Purchase ({p.payment_status.title()})" + (" [Returned]" if p.status == "returned" else ""),
                "debit": float(p.paid_amount),     # Paid at purchase time (reduces payable)
                "credit": float(p.total_amount),   # Total bill (increases payable)
                "method": "purchase_bill",
                "notes": p.notes,
            })
            if p.status == "returned":
                ref_dt = p.updated_at or p.created_at
                raw_events.append({
                    "id": p.id,
                    "type": "debit_note",
                    "date": ref_dt,
                    "ref": f"DN-{p.invoice_number}",
                    "desc": f"Purchase Return / Debit Note ({p.invoice_number})",
                    "debit": float(p.total_amount),  # Debit reduces supplier payable
                    "credit": float(p.paid_amount), # Credit balances refunded paid amount
                    "method": "debit_note",
                    "notes": p.notes or "Goods Returned to Supplier",
                })

        for pmt in payments:
            raw_events.append({
                "id": pmt.id,
                "type": "payment",
                "date": pmt.created_at,
                "ref": pmt.voucher_number,
                "desc": f"Payment Voucher ({pmt.payment_method.title()})",
                "debit": float(pmt.amount),       # Paid to supplier (reduces payable)
                "credit": 0.0,
                "method": pmt.payment_method,
                "notes": pmt.notes or pmt.reference_number,
            })

        raw_events.sort(key=lambda x: x["date"])

        # 4. Running payable balance
        running = float(supplier.opening_balance)
        period_opening = float(supplier.opening_balance)
        entries: List[SupplierLedgerEntry] = []
        total_purchases = 0.0
        total_paid = 0.0

        for ev in raw_events:
            ev_date = ev["date"]
            net_change = ev["credit"] - ev["debit"]
            running = round(running + net_change, 2)

            if from_date and ev_date < from_date:
                period_opening = running
                continue

            if to_date and ev_date > to_date:
                continue

            total_purchases += ev["credit"]
            total_paid += ev["debit"]

            entries.append(
                SupplierLedgerEntry(
                    id=ev["id"],
                    entry_type=ev["type"],
                    date=ev_date,
                    reference=ev["ref"],
                    description=ev["desc"],
                    debit=round(ev["debit"], 2),
                    credit=round(ev["credit"], 2),
                    balance=round(running, 2),
                    payment_method=ev["method"],
                    notes=ev["notes"],
                )
            )

        summary = SupplierLedgerSummary(
            opening_balance=round(period_opening, 2),
            total_purchases=round(total_purchases, 2),
            total_paid=round(total_paid, 2),
            closing_balance=round(running, 2),
            payment_terms_days=supplier.payment_terms_days,
        )

        return SupplierLedgerResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.company_name,
            supplier_code=supplier.code,
            supplier_phone=supplier.phone,
            from_date=from_date,
            to_date=to_date,
            summary=summary,
            entries=entries,
        )

    @staticmethod
    async def get_payables_aging(
        db: AsyncSession,
        tenant_id: int,
        branch_id: Optional[int] = None,
        as_of_date: Optional[date] = None,
        search: Optional[str] = None,
        filter_type: Optional[str] = None,  # "all", "overdue"
    ) -> SupplierAgingReportResponse:
        """
        Compute standard 5-bucket accounts payable aging analysis per supplier.
        Buckets: Current (0-30d), 31-60d, 61-90d, 91-120d, >120d.
        """
        today = as_of_date or datetime.now(timezone.utc).date()

        # 1. Fetch all active suppliers for tenant
        sup_stmt = select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.is_active == True)
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            sup_stmt = sup_stmt.where(
                or_(
                    func.lower(Supplier.company_name).like(s),
                    func.lower(Supplier.contact_person).like(s),
                    Supplier.phone.like(s),
                    func.lower(Supplier.code).like(s),
                )
            )
        sup_res = await db.execute(sup_stmt)
        suppliers = sup_res.scalars().all()
        if not suppliers:
            return SupplierAgingReportResponse(
                as_of_date=today,
                branch_id=branch_id,
                summary=SupplierAgingSummaryKPI(),
                suppliers=[],
            )

        supplier_ids = [s.id for s in suppliers]

        # 2. Fetch unpaid/partially paid purchases
        purch_stmt = (
            select(Purchase)
            .where(
                Purchase.tenant_id == tenant_id,
                Purchase.supplier_id.in_(supplier_ids),
                Purchase.status.notin_(["cancelled", "returned"]),
                Purchase.balance_due > 0,
            )
            .order_by(Purchase.purchase_date.asc())
        )
        if branch_id:
            purch_stmt = purch_stmt.where(Purchase.branch_id == branch_id)
        purch_res = await db.execute(purch_stmt)
        purchases = purch_res.scalars().all()

        purchases_by_supplier: Dict[int, List[Purchase]] = {}
        for p in purchases:
            purchases_by_supplier.setdefault(p.supplier_id, []).append(p)

        # 3. Fetch last payment made to each supplier
        last_pay_subq = (
            select(
                SupplierPayment.supplier_id,
                func.max(SupplierPayment.created_at).label("max_date")
            )
            .where(SupplierPayment.tenant_id == tenant_id, SupplierPayment.supplier_id.in_(supplier_ids))
            .group_by(SupplierPayment.supplier_id)
            .subquery()
        )
        last_pay_stmt = (
            select(SupplierPayment)
            .join(
                last_pay_subq,
                and_(
                    SupplierPayment.supplier_id == last_pay_subq.c.supplier_id,
                    SupplierPayment.created_at == last_pay_subq.c.max_date,
                ),
            )
        )
        last_pay_res = await db.execute(last_pay_stmt)
        last_payments = {p.supplier_id: p for p in last_pay_res.scalars().all()}

        # 4. Compute aging buckets
        aging_items: List[SupplierAgingItem] = []
        tot_payables = 0.0
        tot_current = 0.0
        tot_overdue = 0.0
        overdue_sup_count = 0

        for s in suppliers:
            s_purchases = purchases_by_supplier.get(s.id, [])
            s_balance = float(s.current_balance or 0.0)

            b_current = 0.0
            b_31_60 = 0.0
            b_61_90 = 0.0
            b_91_120 = 0.0
            b_over_120 = 0.0
            oldest_days = 0

            purch_sum = sum(float(p.balance_due) for p in s_purchases)

            for p in s_purchases:
                p_date = p.purchase_date
                days_old = max(0, (today - p_date).days)
                oldest_days = max(oldest_days, days_old)
                amt = float(p.balance_due)

                if days_old <= 30:
                    b_current += amt
                elif days_old <= 60:
                    b_31_60 += amt
                elif days_old <= 90:
                    b_61_90 += amt
                elif days_old <= 120:
                    b_91_120 += amt
                else:
                    b_over_120 += amt

            residual = s_balance - purch_sum
            if residual > 0.01:
                days_acct = max(0, (today - s.created_at.date()).days)
                oldest_days = max(oldest_days, days_acct)
                if days_acct <= 30:
                    b_current += residual
                elif days_acct <= 60:
                    b_31_60 += residual
                elif days_acct <= 90:
                    b_61_90 += residual
                elif days_acct <= 120:
                    b_91_120 += residual
                else:
                    b_over_120 += residual

            s_total = round(b_current + b_31_60 + b_61_90 + b_91_120 + b_over_120, 2)
            s_overdue = round(b_31_60 + b_61_90 + b_91_120 + b_over_120, 2)

            if s_total <= 0 and s_balance <= 0:
                continue

            if filter_type == "overdue" and s_overdue <= 0:
                continue

            last_p = last_payments.get(s.id)

            item = SupplierAgingItem(
                supplier_id=s.id,
                code=s.code,
                company_name=s.company_name,
                contact_person=s.contact_person,
                phone=s.phone,
                payment_terms_days=int(s.payment_terms_days or 30),
                current_balance=round(s_balance, 2),
                total_payable=s_total,
                aging=AgingBucketBreakdown(
                    current=round(b_current, 2),
                    days_31_60=round(b_31_60, 2),
                    days_61_90=round(b_61_90, 2),
                    days_91_120=round(b_91_120, 2),
                    over_120=round(b_over_120, 2),
                    total=s_total,
                ),
                overdue_amount=s_overdue,
                oldest_unpaid_days=oldest_days,
                last_payment_date=last_p.created_at if last_p else None,
                last_payment_amount=float(last_p.amount) if last_p else None,
            )
            aging_items.append(item)

            tot_payables += s_total
            tot_current += b_current
            tot_overdue += s_overdue
            if s_overdue > 0:
                overdue_sup_count += 1

        # 5. Days Payable Outstanding (DPO) calculation
        ninety_days_ago = today - timedelta(days=90)
        cogs_purch_stmt = select(func.sum(Purchase.total_amount)).where(
            Purchase.tenant_id == tenant_id,
            Purchase.status.notin_(["cancelled", "returned"]),
            Purchase.purchase_date >= ninety_days_ago,
        )
        if branch_id:
            cogs_purch_stmt = cogs_purch_stmt.where(Purchase.branch_id == branch_id)
        cogs_purch_res = await db.execute(cogs_purch_stmt)
        total_purch_90 = float(cogs_purch_res.scalar() or 0.0)

        dpo = round((tot_payables / total_purch_90) * 90, 1) if total_purch_90 > 0 else 0.0

        aging_items.sort(key=lambda x: (x.overdue_amount, x.total_payable), reverse=True)

        return SupplierAgingReportResponse(
            as_of_date=today,
            branch_id=branch_id,
            summary=SupplierAgingSummaryKPI(
                total_payables=round(tot_payables, 2),
                total_current=round(tot_current, 2),
                total_overdue=round(tot_overdue, 2),
                days_payable_outstanding=dpo,
                total_suppliers_count=len(aging_items),
                overdue_suppliers_count=overdue_sup_count,
            ),
            suppliers=aging_items,
        )



# ==========================================
# CUSTOMER PAYMENT SERVICE (UDHAAR WASOOLI)
# ==========================================
class CustomerPaymentService:
    @staticmethod
    async def generate_voucher_number(db: AsyncSession, tenant_id: int) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"CRV-{today_str}-"
        stmt = select(func.count(CustomerPayment.id)).where(
            CustomerPayment.tenant_id == tenant_id,
            CustomerPayment.voucher_number.like(f"{prefix}%")
        )
        res = await db.execute(stmt)
        count = (res.scalar() or 0) + 1
        return f"{prefix}{count:04d}"

    @staticmethod
    async def record_payment(
        db: AsyncSession,
        tenant_id: int,
        customer_id: int,
        payload: CustomerPaymentCreate,
        user_id: Optional[int] = None,
    ) -> CustomerPaymentResponse:
        customer_stmt = select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.id == customer_id,
        )
        res = await db.execute(customer_stmt)
        customer = res.scalar_one_or_none()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found."
            )

        amount = round(float(payload.amount), 2)
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be greater than 0."
            )

        prev_balance = round(float(customer.current_balance), 2)
        new_balance = round(prev_balance - amount, 2)

        # Update customer balance
        customer.current_balance = new_balance

        # Auto unblock if balance is now <= credit_limit
        if customer.is_credit_blocked and new_balance <= float(customer.credit_limit):
            customer.is_credit_blocked = False

        customer.updated_at = datetime.now(timezone.utc)

        voucher_no = await CustomerPaymentService.generate_voucher_number(db, tenant_id)

        payment = CustomerPayment(
            tenant_id=tenant_id,
            customer_id=customer.id,
            branch_id=payload.branch_id or customer.branch_id,
            voucher_number=voucher_no,
            amount=amount,
            payment_method=payload.payment_method or "cash",
            reference_number=payload.reference_number.strip() if payload.reference_number else None,
            notes=payload.notes.strip() if payload.notes else None,
            previous_balance=prev_balance,
            new_balance=new_balance,
            received_by_id=user_id,
        )
        db.add(payment)
        await db.flush()

        # Double-entry General Ledger Auto-Posting
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.post_customer_payment(db, tenant_id, payment, user_id)
        except Exception as e:
            print(f"[ACCOUNTING POSTING ERROR] Customer payment {payment.voucher_number}: {e}")

        await db.commit()
        await db.refresh(payment)

        # Fetch user name if available
        user_name = None
        if user_id:
            u_res = await db.execute(select(User).where(User.id == user_id))
            u = u_res.scalar_one_or_none()
            if u:
                user_name = u.full_name

        resp = CustomerPaymentResponse.model_validate(payment)
        resp.received_by_name = user_name
        resp.customer_business_name = customer.business_name
        resp.customer_phone = customer.phone
        return resp

    @staticmethod
    async def list_payments(
        db: AsyncSession,
        tenant_id: int,
        customer_id: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedCustomerPaymentsResponse:
        query = select(CustomerPayment).where(CustomerPayment.tenant_id == tenant_id)
        if customer_id:
            query = query.where(CustomerPayment.customer_id == customer_id)

        count_query = select(func.count(CustomerPayment.id)).where(CustomerPayment.tenant_id == tenant_id)
        if customer_id:
            count_query = count_query.where(CustomerPayment.customer_id == customer_id)

        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        query = (
            query.options(
                joinedload(CustomerPayment.customer),
                joinedload(CustomerPayment.received_by),
            )
            .order_by(CustomerPayment.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        res = await db.execute(query)
        payments = res.scalars().all()

        items = []
        for p in payments:
            resp = CustomerPaymentResponse.model_validate(p)
            if p.customer:
                resp.customer_business_name = p.customer.business_name
                resp.customer_phone = p.customer.phone
            if p.received_by:
                resp.received_by_name = p.received_by.full_name
            items.append(resp)

        total_pages = (total + size - 1) // size if total > 0 else 1
        return PaginatedCustomerPaymentsResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            total_pages=total_pages,
        )


# ==========================================
# SUPPLIER PAYMENT SERVICE (CPV)
# ==========================================
class SupplierPaymentService:
    @staticmethod
    async def generate_voucher_number(db: AsyncSession, tenant_id: int) -> str:
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"CPV-{today_str}-"
        stmt = select(func.count(SupplierPayment.id)).where(
            SupplierPayment.tenant_id == tenant_id,
            SupplierPayment.voucher_number.like(f"{prefix}%")
        )
        res = await db.execute(stmt)
        count = (res.scalar() or 0) + 1
        return f"{prefix}{count:04d}"

    @staticmethod
    async def record_payment(
        db: AsyncSession,
        tenant_id: int,
        supplier_id: int,
        payload: SupplierPaymentCreate,
        user_id: Optional[int] = None,
    ) -> SupplierPaymentResponse:
        supplier = await SupplierService.get_supplier(db, tenant_id, supplier_id)

        amount = round(float(payload.amount), 2)
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be greater than 0."
            )

        prev_balance = round(float(supplier.current_balance), 2)
        new_balance = round(prev_balance - amount, 2)

        supplier.current_balance = new_balance
        supplier.updated_at = datetime.now(timezone.utc)

        voucher_no = await SupplierPaymentService.generate_voucher_number(db, tenant_id)

        payment = SupplierPayment(
            tenant_id=tenant_id,
            supplier_id=supplier.id,
            branch_id=payload.branch_id,
            voucher_number=voucher_no,
            amount=amount,
            payment_method=payload.payment_method or "cash",
            reference_number=payload.reference_number.strip() if payload.reference_number else None,
            notes=payload.notes.strip() if payload.notes else None,
            previous_balance=prev_balance,
            new_balance=new_balance,
            paid_by_id=user_id,
        )
        db.add(payment)
        await db.flush()

        # Double-entry General Ledger Auto-Posting
        try:
            from app.modules.accounting.posting import AccountingPostingEngine
            await AccountingPostingEngine.post_supplier_payment(db, tenant_id, payment, user_id)
        except Exception as e:
            print(f"[ACCOUNTING POSTING ERROR] Supplier payment {payment.voucher_number}: {e}")

        await db.commit()
        await db.refresh(payment)

        user_name = None
        if user_id:
            u_res = await db.execute(select(User).where(User.id == user_id))
            u = u_res.scalar_one_or_none()
            if u:
                user_name = u.full_name

        resp = SupplierPaymentResponse.model_validate(payment)
        resp.paid_by_name = user_name
        resp.supplier_company_name = supplier.company_name
        resp.supplier_phone = supplier.phone
        return resp

    @staticmethod
    async def list_payments(
        db: AsyncSession,
        tenant_id: int,
        supplier_id: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedSupplierPaymentsResponse:
        query = select(SupplierPayment).where(SupplierPayment.tenant_id == tenant_id)
        if supplier_id:
            query = query.where(SupplierPayment.supplier_id == supplier_id)

        count_query = select(func.count(SupplierPayment.id)).where(SupplierPayment.tenant_id == tenant_id)
        if supplier_id:
            count_query = count_query.where(SupplierPayment.supplier_id == supplier_id)

        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        query = (
            query.options(
                joinedload(SupplierPayment.supplier),
                joinedload(SupplierPayment.paid_by),
            )
            .order_by(SupplierPayment.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        res = await db.execute(query)
        payments = res.scalars().all()

        items = []
        for p in payments:
            resp = SupplierPaymentResponse.model_validate(p)
            if p.supplier:
                resp.supplier_company_name = p.supplier.company_name
                resp.supplier_phone = p.supplier.phone
            if p.paid_by:
                resp.paid_by_name = p.paid_by.full_name
            items.append(resp)

        total_pages = (total + size - 1) // size if total > 0 else 1
        return PaginatedSupplierPaymentsResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            total_pages=total_pages,
        )


