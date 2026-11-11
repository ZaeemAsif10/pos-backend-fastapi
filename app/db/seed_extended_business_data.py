import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.modules.products.models import Product, Category, Brand, BranchStock, ProductUOMConversion
from app.modules.branches.models import Branch
from app.modules.parties.models import Customer, Supplier, DeliveryArea
from app.modules.sales.models import SalesInvoice, SalesInvoiceItem, SalesPayment, POSShift
from app.modules.inventory.models import StockMovement
from app.integrations.fbr.client import FBRClient


BUSINESS_1_NEW_PRODUCTS = [
    {
        "name": "Dawn Plain Bread Large",
        "sku": "DWN-BRD-LRG",
        "barcode": "8961012001019",
        "category_name": "Bakery & Sweets",
        "brand_name": "Dawn Foods",
        "base_unit": "Piece",
        "cost_price": 140.0,
        "retail_price": 170.0,
        "wholesale_price": 155.0,
        "tax_rate": 0.0,
        "stock": 85.0,
        "carton_pack": 10,
        "carton_price": 1550.0,
    },
    {
        "name": "Peek Freans Sooper Biscuit Family Pack",
        "sku": "SOOP-FAM-112",
        "barcode": "8961013001124",
        "category_name": "Snacks, Biscuits & Confectionery",
        "brand_name": "English Biscuit Manufacturers",
        "base_unit": "Piece",
        "cost_price": 85.0,
        "retail_price": 110.0,
        "wholesale_price": 95.0,
        "tax_rate": 18.0,
        "stock": 240.0,
        "carton_pack": 24,
        "carton_price": 2280.0,
    },
    {
        "name": "Olpers Full Cream Milk 1 Litre",
        "sku": "OLP-MILK-1L",
        "barcode": "8961015001009",
        "category_name": "Dairy, Milk & Cream",
        "brand_name": "Engro Foods",
        "base_unit": "Piece",
        "cost_price": 265.0,
        "retail_price": 310.0,
        "wholesale_price": 285.0,
        "tax_rate": 18.0,
        "stock": 160.0,
        "carton_pack": 12,
        "carton_price": 3420.0,
    },
    {
        "name": "Hamdard Rooh Afza Syrup 800ml",
        "sku": "RHF-BOT-800",
        "barcode": "8961016008003",
        "category_name": "Beverages & Drinks",
        "brand_name": "Hamdard Laboratories",
        "base_unit": "Piece",
        "cost_price": 380.0,
        "retail_price": 450.0,
        "wholesale_price": 410.0,
        "tax_rate": 18.0,
        "stock": 90.0,
        "carton_pack": 12,
        "carton_price": 4920.0,
    },
    {
        "name": "Surf Excel Quick Wash Detergent 1kg",
        "sku": "SRF-EXC-1KG",
        "barcode": "8961017001005",
        "category_name": "Household & Cleaning",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 540.0,
        "retail_price": 630.0,
        "wholesale_price": 580.0,
        "tax_rate": 18.0,
        "stock": 75.0,
        "carton_pack": 12,
        "carton_price": 6960.0,
    },
    {
        "name": "Lifebuoy Total Bar Soap 115g",
        "sku": "LFB-TOT-115",
        "barcode": "8961018001158",
        "category_name": "Personal Care & Soap",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 85.0,
        "retail_price": 110.0,
        "wholesale_price": 95.0,
        "tax_rate": 18.0,
        "stock": 300.0,
        "carton_pack": 48,
        "carton_price": 4560.0,
    },
    {
        "name": "Mitchell's Golden Apple & Mango Jam 450g",
        "sku": "MTC-JAM-450",
        "barcode": "8961019004503",
        "category_name": "Bakery & Sweets",
        "brand_name": "Mitchell's Fruit Farms",
        "base_unit": "Piece",
        "cost_price": 310.0,
        "retail_price": 375.0,
        "wholesale_price": 340.0,
        "tax_rate": 18.0,
        "stock": 65.0,
        "carton_pack": 12,
        "carton_price": 4080.0,
    },
    {
        "name": "Mezan Canola Cooking Oil 5 Litre Can",
        "sku": "MZN-OIL-5L",
        "barcode": "8961020005004",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Mezan Beverages",
        "base_unit": "Piece",
        "cost_price": 2680.0,
        "retail_price": 2920.0,
        "wholesale_price": 2780.0,
        "tax_rate": 18.0,
        "stock": 40.0,
        "carton_pack": 4,
        "carton_price": 11120.0,
    },
    {
        "name": "Shezan All-Natural Mango Nectar 250ml",
        "sku": "SHZ-MNG-250",
        "barcode": "8961021002507",
        "category_name": "Beverages & Drinks",
        "brand_name": "Shezan International",
        "base_unit": "Piece",
        "cost_price": 45.0,
        "retail_price": 60.0,
        "wholesale_price": 50.0,
        "tax_rate": 18.0,
        "stock": 350.0,
        "carton_pack": 24,
        "carton_price": 1200.0,
    },
    {
        "name": "National Tomato Ketchup Squeezy 800g",
        "sku": "NAT-KET-800",
        "barcode": "8961022008003",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "National Foods",
        "base_unit": "Piece",
        "cost_price": 390.0,
        "retail_price": 460.0,
        "wholesale_price": 420.0,
        "tax_rate": 18.0,
        "stock": 110.0,
        "carton_pack": 12,
        "carton_price": 5040.0,
    },
]

BUSINESS_2_NEW_PRODUCTS = [
    {
        "name": "Habib Canola Cooking Oil 16 Litre Tin",
        "sku": "HBB-OIL-16L",
        "barcode": "8962001016001",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Habib Oil Mills",
        "base_unit": "Piece",
        "cost_price": 8900.0,
        "retail_price": 9650.0,
        "wholesale_price": 9200.0,
        "tax_rate": 18.0,
        "stock": 35.0,
        "carton_pack": 1,
        "carton_price": 9200.0,
    },
    {
        "name": "Daal Chana Special Desi 50kg Jute Bag",
        "sku": "PUL-CHN-50KG",
        "barcode": "8962002050002",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Wholesale Agro Traders",
        "base_unit": "Piece",
        "cost_price": 12500.0,
        "retail_price": 13900.0,
        "wholesale_price": 13200.0,
        "tax_rate": 0.0,
        "stock": 60.0,
        "carton_pack": 1,
        "carton_price": 13200.0,
    },
    {
        "name": "Daal Moong Washed Premium 25kg Bag",
        "sku": "PUL-MNG-25KG",
        "barcode": "8962003025003",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Wholesale Agro Traders",
        "base_unit": "Piece",
        "cost_price": 7200.0,
        "retail_price": 8100.0,
        "wholesale_price": 7600.0,
        "tax_rate": 0.0,
        "stock": 45.0,
        "carton_pack": 1,
        "carton_price": 7600.0,
    },
    {
        "name": "Sunridge Chakki Fortified Atta 20kg Bag",
        "sku": "FLR-CHK-20KG",
        "barcode": "8962004020004",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Sunridge Mills",
        "base_unit": "Piece",
        "cost_price": 2400.0,
        "retail_price": 2750.0,
        "wholesale_price": 2550.0,
        "tax_rate": 0.0,
        "stock": 90.0,
        "carton_pack": 1,
        "carton_price": 2550.0,
    },
    {
        "name": "Vital Premium Gold Black Tea 950g",
        "sku": "VTL-TEA-950",
        "barcode": "8962005009505",
        "category_name": "Tea, Coffee & Whitener",
        "brand_name": "Vital Tea Pakistan",
        "base_unit": "Piece",
        "cost_price": 1450.0,
        "retail_price": 1680.0,
        "wholesale_price": 1550.0,
        "tax_rate": 18.0,
        "stock": 70.0,
        "carton_pack": 12,
        "carton_price": 18600.0,
    },
    {
        "name": "Candyland Chilli Milli Dispenser Box 24s",
        "sku": "CDL-CHL-24S",
        "barcode": "8962006002406",
        "category_name": "Snacks, Biscuits & Confectionery",
        "brand_name": "Ismail Industries",
        "base_unit": "Piece",
        "cost_price": 380.0,
        "retail_price": 480.0,
        "wholesale_price": 420.0,
        "tax_rate": 18.0,
        "stock": 140.0,
        "carton_pack": 12,
        "carton_price": 5040.0,
    },
    {
        "name": "Rafhan Custard Powder Vanilla 1kg Box",
        "sku": "RFH-CST-1KG",
        "barcode": "8962007001007",
        "category_name": "Bakery & Sweets",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 490.0,
        "retail_price": 570.0,
        "wholesale_price": 525.0,
        "tax_rate": 18.0,
        "stock": 80.0,
        "carton_pack": 12,
        "carton_price": 6300.0,
    },
    {
        "name": "Shezan Pure Natural Honey 1kg Glass Jar",
        "sku": "SHZ-HNY-1KG",
        "barcode": "8962008001008",
        "category_name": "Bakery & Sweets",
        "brand_name": "Shezan International",
        "base_unit": "Piece",
        "cost_price": 920.0,
        "retail_price": 1150.0,
        "wholesale_price": 1020.0,
        "tax_rate": 18.0,
        "stock": 55.0,
        "carton_pack": 6,
        "carton_price": 6120.0,
    },
    {
        "name": "Mehran Biryani Masala 1kg Catering Pack",
        "sku": "MHR-BIR-1KG",
        "barcode": "8962009001009",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "Mehran Spices",
        "base_unit": "Piece",
        "cost_price": 1100.0,
        "retail_price": 1350.0,
        "wholesale_price": 1200.0,
        "tax_rate": 18.0,
        "stock": 65.0,
        "carton_pack": 10,
        "carton_price": 12000.0,
    },
    {
        "name": "Fauji Corn Flakes Large 500g Box",
        "sku": "FAJ-CRN-500",
        "barcode": "8962010005000",
        "category_name": "Snacks, Biscuits & Confectionery",
        "brand_name": "Fauji Cereals",
        "base_unit": "Piece",
        "cost_price": 420.0,
        "retail_price": 510.0,
        "wholesale_price": 460.0,
        "tax_rate": 18.0,
        "stock": 75.0,
        "carton_pack": 12,
        "carton_price": 5520.0,
    },
]


async def ensure_categories_and_brands(db, tenant_id: int):
    # Required categories
    cat_names = [
        ("Bakery & Sweets", "BAK"),
        ("Beverages & Drinks", "BEV"),
        ("Dairy, Milk & Cream", "DRY"),
        ("Grains, Flour & Rice", "GRN"),
        ("Snacks, Biscuits & Confectionery", "SNK"),
        ("Spices, Recipe Mixes & Salt", "SPC"),
        ("Tea, Coffee & Whitener", "TEA"),
        ("Personal Care & Soap", "PCS"),
        ("Household & Cleaning", "HCL"),
    ]
    for name, code in cat_names:
        c = (
            await db.execute(
                select(Category).where(
                    Category.tenant_id == tenant_id,
                    Category.name == name,
                )
            )
        ).scalars().first()
        if not c:
            db.add(
                Category(
                    tenant_id=tenant_id,
                    name=name,
                    code=f"{code}-{tenant_id}",
                    is_active=True,
                )
            )

    # Required brands
    brand_names = [
        ("Dawn Foods", "DWN"),
        ("English Biscuit Manufacturers", "EBM"),
        ("Engro Foods", "ENG"),
        ("Hamdard Laboratories", "HMD"),
        ("Unilever Pakistan", "UNI"),
        ("Mitchell's Fruit Farms", "MTC"),
        ("Mezan Beverages", "MZN"),
        ("National Foods", "NAT"),
        ("Habib Oil Mills", "HOM"),
        ("Wholesale Agro Traders", "AGR"),
        ("Sunridge Mills", "SRM"),
        ("Vital Tea Pakistan", "VTL"),
        ("Ismail Industries", "ISM"),
        ("Mehran Spices", "MHR"),
        ("Fauji Cereals", "FAJ"),
        ("Nestle Pakistan", "NES"),
        ("Shan Foods", "SHN"),
        ("Dalda Foods", "DLD"),
    ]
    for b_name, b_code in brand_names:
        b = (
            await db.execute(
                select(Brand).where(
                    Brand.tenant_id == tenant_id,
                    Brand.name == b_name,
                )
            )
        ).scalars().first()
        if not b:
            db.add(
                Brand(
                    tenant_id=tenant_id,
                    name=b_name,
                    code=f"{b_code}-{tenant_id}",
                    origin="Pakistan",
                    is_active=True,
                )
            )
    await db.commit()


async def seed_products(db, tenant_id: int, products_list: list):
    branch = (await db.execute(select(Branch).where(Branch.tenant_id == tenant_id))).scalars().first()
    if not branch:
        return

    cats = (await db.execute(select(Category).where(Category.tenant_id == tenant_id))).scalars().all()
    cat_map = {c.name.lower(): c.id for c in cats}

    brands = (await db.execute(select(Brand).where(Brand.tenant_id == tenant_id))).scalars().all()
    brand_map = {b.name.lower(): b.id for b in brands}

    for p in products_list:
        existing = (
            await db.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.sku == p["sku"],
                )
            )
        ).scalars().first()

        if existing:
            continue

        cat_id = cat_map.get(p["category_name"].lower()) or cats[0].id
        brand_id = brand_map.get(p["brand_name"].lower()) or (brands[0].id if brands else None)

        prod = Product(
            tenant_id=tenant_id,
            name=p["name"],
            sku=p["sku"],
            barcode=p["barcode"],
            category_id=cat_id,
            brand_id=brand_id,
            base_unit=p["base_unit"],
            cost_price=p["cost_price"],
            retail_price=p["retail_price"],
            wholesale_price=p["wholesale_price"],
            tax_rate=p["tax_rate"],
            is_fbr_third_schedule=False,
            is_active=True,
        )
        db.add(prod)
        await db.flush()

        b_stock = BranchStock(
            tenant_id=tenant_id,
            branch_id=branch.id,
            product_id=prod.id,
            quantity=p["stock"],
        )
        db.add(b_stock)

        uom = ProductUOMConversion(
            tenant_id=tenant_id,
            product_id=prod.id,
            unit_name="Carton",
            conversion_factor=p["carton_pack"],
            carton_barcode=f"CRT-{p['barcode']}",
            carton_wholesale_price=p["carton_price"],
            carton_retail_price=p["retail_price"] * p["carton_pack"],
        )
        db.add(uom)

        # Stock movement entry
        sm = StockMovement(
            tenant_id=tenant_id,
            branch_id=branch.id,
            product_id=prod.id,
            movement_type="PURCHASE",
            quantity=p["stock"],
            balance_after=p["stock"],
            unit_cost=p["cost_price"],
            reference_type="opening_stock",
            reference_id=prod.id,
            notes=f"Initial Opening Inventory Stock for {prod.name}",
        )
        db.add(sm)

    await db.commit()


async def seed_shifts_and_sales(db, tenant_id: int):
    branch = (await db.execute(select(Branch).where(Branch.tenant_id == tenant_id))).scalars().first()
    if not branch:
        return

    # Check or create shift
    open_shift = (
        await db.execute(
            select(POSShift).where(
                POSShift.tenant_id == tenant_id,
                POSShift.branch_id == branch.id,
                POSShift.status == "open",
            )
        )
    ).scalars().first()

    # Cashier user
    from app.modules.auth.models import User
    user = (await db.execute(select(User))).scalars().first()
    cashier_id = user.id if user else 1

    if not open_shift:
        open_shift = POSShift(
            tenant_id=tenant_id,
            branch_id=branch.id,
            cashier_id=cashier_id,
            opening_cash=5000.0,
            status="open",
            notes="Morning Counter Register Shift",
        )
        db.add(open_shift)
        await db.flush()

    # Fetch some customers
    customers = (await db.execute(select(Customer).where(Customer.tenant_id == tenant_id))).scalars().all()
    cust1 = customers[0] if customers else None
    cust2 = customers[1] if len(customers) > 1 else None

    # Fetch products
    prods = (await db.execute(select(Product).where(Product.tenant_id == tenant_id))).scalars().all()
    if len(prods) < 3:
        return

    # Seed 3 sample invoices if none or few exist
    existing_invoices = (
        await db.execute(
            select(func.count(SalesInvoice.id)).where(SalesInvoice.tenant_id == tenant_id)
        )
    ).scalar() or 0

    if existing_invoices < 3:
        fbr_client = FBRClient(mode="mock")

        sample_orders = [
            {
                "customer": cust1,
                "items": [
                    {"prod": prods[0], "qty": 2.0},
                    {"prod": prods[1], "qty": 1.0},
                ],
                "method": "cash",
                "days_ago": 1,
            },
            {
                "customer": cust2,
                "items": [
                    {"prod": prods[2], "qty": 3.0},
                    {"prod": prods[0], "qty": 1.0},
                ],
                "method": "card",
                "days_ago": 0,
            },
            {
                "customer": None,
                "items": [
                    {"prod": prods[1], "qty": 2.0},
                    {"prod": prods[2], "qty": 1.0},
                ],
                "method": "cash",
                "days_ago": 0,
            },
        ]

        from app.integrations.fbr.schemas import FBRInvoicePayload, FBRInvoiceItemPayload
        for i, order in enumerate(sample_orders):
            inv_date = datetime.now(timezone.utc) - timedelta(days=order["days_ago"], hours=i * 2 + 1)
            inv_number = f"POS-T{tenant_id}-{inv_date.strftime('%Y%m%d')}-{100 + i}"

            # Calculate amounts
            subtotal = sum(float(it["prod"].retail_price) * it["qty"] for it in order["items"])
            tax = sum((float(it["prod"].retail_price) * it["qty"]) * (float(it["prod"].tax_rate) / 100.0) for it in order["items"])
            total = subtotal + tax

            cust = order["customer"]
            c_name = cust.business_name if cust else "Walk-in Retail Buyer"
            c_phone = cust.phone if cust else "0300-1234567"
            c_ntn = cust.ntn or cust.cnic if cust else None

            # FBR simulation
            fbr_payload = FBRInvoicePayload(
                POSID=101 + tenant_id,
                USIN=inv_number,
                DateTime=inv_date.strftime("%Y-%m-%d %H:%M:%S"),
                BuyerNTN=c_ntn,
                BuyerName=c_name,
                BuyerPhoneNumber=c_phone,
                TotalSaleValue=subtotal,
                TotalQuantity=sum(it["qty"] for it in order["items"]),
                TotalTaxCharged=tax,
                TotalBillAmount=total,
                PaymentMode=1 if order["method"] == "cash" else 2,
                InvoiceType=1,
                Items=[
                    FBRInvoiceItemPayload(
                        ItemCode=it["prod"].sku,
                        ItemName=it["prod"].name,
                        PCTCode="1901.9090",
                        Quantity=it["qty"],
                        TaxRate=float(it["prod"].tax_rate),
                        SaleValue=float(it["prod"].retail_price) * it["qty"],
                        TaxCharged=(float(it["prod"].retail_price) * it["qty"]) * (float(it["prod"].tax_rate) / 100.0),
                        Discount=0.0,
                        FurtherTax=0.0,
                        TotalAmount=(float(it["prod"].retail_price) * it["qty"]) * (1.0 + float(it["prod"].tax_rate) / 100.0),
                    )
                    for it in order["items"]
                ],
            )
            fbr_resp = await fbr_client.post_invoice(fbr_payload)

            inv = SalesInvoice(
                tenant_id=tenant_id,
                branch_id=branch.id,
                customer_id=cust.id if cust else None,
                pos_shift_id=open_shift.id,
                customer_name=c_name,
                customer_phone=c_phone,
                customer_ntn_cnic=c_ntn,
                invoice_number=inv_number,
                sale_type="pos_retail",
                invoice_date=inv_date,
                payment_method=order["method"],
                payment_status="paid",
                subtotal=subtotal,
                discount_amount=0.0,
                tax_amount=tax,
                total_amount=total,
                paid_amount=total,
                change_amount=0.0,
                balance_due=0.0,
                fbr_pos_id=str(101 + tenant_id),
                fbr_invoice_number=fbr_resp.fbr_invoice_number,
                fbr_qr_code=fbr_resp.fbr_qr_code,
                fbr_status="mocked",
                fbr_response_message="Validated via FBR Digital Invoicing Mock Engine",
                fbr_synced_at=inv_date,
                created_by_id=cashier_id,
                status="completed",
                created_at=inv_date,
            )
            db.add(inv)
            await db.flush()

            # Items
            for it in order["items"]:
                p = it["prod"]
                line_sub = float(p.retail_price) * it["qty"]
                line_tax = line_sub * (float(p.tax_rate) / 100.0)
                inv_item = SalesInvoiceItem(
                    tenant_id=tenant_id,
                    sales_invoice_id=inv.id,
                    product_id=p.id,
                    uom_name=p.base_unit,
                    quantity=it["qty"],
                    unit_price=float(p.retail_price),
                    cost_price=float(p.cost_price),
                    discount_amount=0.0,
                    tax_rate=float(p.tax_rate),
                    tax_amount=line_tax,
                    pct_code="1901.9090",
                    total_amount=line_sub + line_tax,
                    created_at=inv_date,
                )
                db.add(inv_item)

            # Payment
            payment = SalesPayment(
                tenant_id=tenant_id,
                sales_invoice_id=inv.id,
                payment_method=order["method"],
                amount=total,
                payment_date=inv_date,
                received_by_id=cashier_id,
                created_at=inv_date,
            )
            db.add(payment)

        await db.commit()
        print(f"✅ Created sample sales invoices and shift for Tenant {tenant_id}")


async def main():
    async with AsyncSessionLocal() as db:
        print("--- Ensuring Categories and Brands ---")
        await ensure_categories_and_brands(db, tenant_id=5)
        await ensure_categories_and_brands(db, tenant_id=8)

        print("\n--- Seeding Extended Products for Business 1 (Tenant 5) ---")
        await seed_products(db, tenant_id=5, products_list=BUSINESS_1_NEW_PRODUCTS)

        print("\n--- Seeding Extended Products for Business 2 (Tenant 8) ---")
        await seed_products(db, tenant_id=8, products_list=BUSINESS_2_NEW_PRODUCTS)

        print("\n--- Seeding POS Shifts & Invoices ---")
        await seed_shifts_and_sales(db, tenant_id=5)
        await seed_shifts_and_sales(db, tenant_id=8)

        print("\n🎉 ALL SEED DATA POPULATED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
