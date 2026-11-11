import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.products.models import Product, Category, Brand, BranchStock, ProductUOMConversion
from app.modules.branches.models import Branch

# Distinct product catalogs for Business 1 (Tenant 5) and Business 2 (Tenant 8)
BUSINESS_1_PRODUCTS = [
    {
        "name": "Dalda Cooking Oil 5 Litre Can",
        "sku": "DLD-OIL-5L",
        "barcode": "8961014100512",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Dalda Foods",
        "base_unit": "Piece",
        "cost_price": 2750.0,
        "retail_price": 2980.0,
        "wholesale_price": 2850.0,
        "tax_rate": 18.0,
        "stock": 45.0,
        "carton_pack": 4,
        "carton_price": 11400.0,
    },
    {
        "name": "Shan Special Bombay Biryani 50g",
        "sku": "SHN-BIR-50G",
        "barcode": "788821001015",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "Shan Foods",
        "base_unit": "Piece",
        "cost_price": 95.0,
        "retail_price": 120.0,
        "wholesale_price": 105.0,
        "tax_rate": 18.0,
        "stock": 350.0,
        "carton_pack": 72,
        "carton_price": 7560.0,
    },
    {
        "name": "National Mixed Pickle 1kg Jar",
        "sku": "NAT-PCK-1KG",
        "barcode": "8961011120155",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "National Foods",
        "base_unit": "Piece",
        "cost_price": 480.0,
        "retail_price": 560.0,
        "wholesale_price": 510.0,
        "tax_rate": 18.0,
        "stock": 80.0,
        "carton_pack": 12,
        "carton_price": 6120.0,
    },
    {
        "name": "Tapal Danedar Tea 430g Poly Pack",
        "sku": "TPL-DAN-430",
        "barcode": "8964000100431",
        "category_name": "Tea, Coffee & Whitener",
        "brand_name": "Tapal Tea",
        "base_unit": "Piece",
        "cost_price": 670.0,
        "retail_price": 740.0,
        "wholesale_price": 700.0,
        "tax_rate": 18.0,
        "stock": 120.0,
        "carton_pack": 24,
        "carton_price": 16800.0,
    },
    {
        "name": "Lipton Yellow Label 380g Box",
        "sku": "LIP-YL-380",
        "barcode": "8961017003801",
        "category_name": "Tea, Coffee & Whitener",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 620.0,
        "retail_price": 690.0,
        "wholesale_price": 650.0,
        "tax_rate": 18.0,
        "stock": 95.0,
        "carton_pack": 24,
        "carton_price": 15600.0,
    },
    {
        "name": "Nestle Cerelac Wheat 350g Bib",
        "sku": "NES-CER-WHT",
        "barcode": "7613031201452",
        "category_name": "Dairy, Milk & Cream",
        "brand_name": "Nestle Pakistan",
        "base_unit": "Piece",
        "cost_price": 580.0,
        "retail_price": 650.0,
        "wholesale_price": 610.0,
        "tax_rate": 18.0,
        "stock": 60.0,
        "carton_pack": 24,
        "carton_price": 14640.0,
    },
    {
        "name": "Super Kernel Basmati Rice 5kg Bag",
        "sku": "RCE-BSM-5KG",
        "barcode": "8961019005012",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "National Foods",
        "base_unit": "Piece",
        "cost_price": 1800.0,
        "retail_price": 2100.0,
        "wholesale_price": 1950.0,
        "tax_rate": 0.0,
        "stock": 70.0,
        "carton_pack": 4,
        "carton_price": 7800.0,
    },
    {
        "name": "Lays Classic Salted Chips 65g",
        "sku": "LAY-SLT-65G",
        "barcode": "8964000300657",
        "category_name": "Snacks, Biscuits & Confectionery",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 80.0,
        "retail_price": 100.0,
        "wholesale_price": 88.0,
        "tax_rate": 18.0,
        "stock": 180.0,
        "carton_pack": 30,
        "carton_price": 2640.0,
    },
    {
        "name": "Coca-Cola 1.5 Litre Bottle",
        "sku": "COK-15L",
        "barcode": "8961001001502",
        "category_name": "Beverages & Drinks",
        "brand_name": "Nestle Pakistan",
        "base_unit": "Piece",
        "cost_price": 165.0,
        "retail_price": 190.0,
        "wholesale_price": 175.0,
        "tax_rate": 18.0,
        "stock": 150.0,
        "carton_pack": 6,
        "carton_price": 1050.0,
    },
    {
        "name": "Shan Chicken Masala 50g",
        "sku": "SHN-CHK-50G",
        "barcode": "788821002012",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "Shan Foods",
        "base_unit": "Piece",
        "cost_price": 95.0,
        "retail_price": 120.0,
        "wholesale_price": 105.0,
        "tax_rate": 18.0,
        "stock": 200.0,
        "carton_pack": 72,
        "carton_price": 7560.0,
    },
]

BUSINESS_2_PRODUCTS = [
    {
        "name": "Nestle Bunyad Powder 260g Pouch",
        "sku": "NES-BNY-260G",
        "barcode": "7613035602604",
        "category_name": "Dairy, Milk & Cream",
        "brand_name": "Nestle Pakistan",
        "base_unit": "Piece",
        "cost_price": 340.0,
        "retail_price": 390.0,
        "wholesale_price": 360.0,
        "tax_rate": 18.0,
        "stock": 140.0,
        "carton_pack": 24,
        "carton_price": 8640.0,
    },
    {
        "name": "Dalda Banaspati Ghee 1kg Pouch",
        "sku": "DLD-GHE-1KG",
        "barcode": "8961014101014",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "Dalda Foods",
        "base_unit": "Piece",
        "cost_price": 560.0,
        "retail_price": 610.0,
        "wholesale_price": 580.0,
        "tax_rate": 18.0,
        "stock": 160.0,
        "carton_pack": 16,
        "carton_price": 9280.0,
    },
    {
        "name": "Shan Shahi Korma Recipe Mix 50g",
        "sku": "SHN-KOR-50G",
        "barcode": "788821003019",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "Shan Foods",
        "base_unit": "Piece",
        "cost_price": 95.0,
        "retail_price": 120.0,
        "wholesale_price": 105.0,
        "tax_rate": 18.0,
        "stock": 220.0,
        "carton_pack": 72,
        "carton_price": 7560.0,
    },
    {
        "name": "National Chilli Garlic Sauce 800g",
        "sku": "NAT-CGS-800G",
        "barcode": "8961011130802",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "National Foods",
        "base_unit": "Piece",
        "cost_price": 410.0,
        "retail_price": 470.0,
        "wholesale_price": 435.0,
        "tax_rate": 18.0,
        "stock": 90.0,
        "carton_pack": 12,
        "carton_price": 5220.0,
    },
    {
        "name": "Tapal Tezdum Tea 450g Pack",
        "sku": "TPL-TEZ-450",
        "barcode": "8964000100455",
        "category_name": "Tea, Coffee & Whitener",
        "brand_name": "Tapal Tea",
        "base_unit": "Piece",
        "cost_price": 630.0,
        "retail_price": 695.0,
        "wholesale_price": 660.0,
        "tax_rate": 18.0,
        "stock": 110.0,
        "carton_pack": 24,
        "carton_price": 15840.0,
    },
    {
        "name": "Knorr Chicken Noodles 66g Pack",
        "sku": "KNR-NDL-66G",
        "barcode": "8961017006604",
        "category_name": "Snacks, Biscuits & Confectionery",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 50.0,
        "retail_price": 65.0,
        "wholesale_price": 56.0,
        "tax_rate": 18.0,
        "stock": 400.0,
        "carton_pack": 48,
        "carton_price": 2688.0,
    },
    {
        "name": "Guard Supreme Basmati Rice 10kg Bag",
        "sku": "GRD-RCE-10KG",
        "barcode": "8961019010016",
        "category_name": "Grains, Flour & Rice",
        "brand_name": "National Foods",
        "base_unit": "Piece",
        "cost_price": 3500.0,
        "retail_price": 3950.0,
        "wholesale_price": 3700.0,
        "tax_rate": 0.0,
        "stock": 50.0,
        "carton_pack": 2,
        "carton_price": 7400.0,
    },
    {
        "name": "Knorr Chicken Cubes 24s Pack",
        "sku": "KNR-CUB-24S",
        "barcode": "8961017002408",
        "category_name": "Spices, Recipe Mixes & Salt",
        "brand_name": "Unilever Pakistan",
        "base_unit": "Piece",
        "cost_price": 320.0,
        "retail_price": 370.0,
        "wholesale_price": 340.0,
        "tax_rate": 18.0,
        "stock": 130.0,
        "carton_pack": 24,
        "carton_price": 8160.0,
    },
    {
        "name": "Sprite 1.5 Litre Pet Bottle",
        "sku": "SPR-15L",
        "barcode": "8961001001519",
        "category_name": "Beverages & Drinks",
        "brand_name": "Nestle Pakistan",
        "base_unit": "Piece",
        "cost_price": 165.0,
        "retail_price": 190.0,
        "wholesale_price": 175.0,
        "tax_rate": 18.0,
        "stock": 120.0,
        "carton_pack": 6,
        "carton_price": 1050.0,
    },
    {
        "name": "Nestle Everyday Tea Whitener 375g",
        "sku": "NES-EVR-375",
        "barcode": "7613035603755",
        "category_name": "Dairy, Milk & Cream",
        "brand_name": "Nestle Pakistan",
        "base_unit": "Piece",
        "cost_price": 480.0,
        "retail_price": 540.0,
        "wholesale_price": 505.0,
        "tax_rate": 18.0,
        "stock": 90.0,
        "carton_pack": 24,
        "carton_price": 12120.0,
    },
]


async def seed_tenant_products(db, tenant_id: int, product_list: list):
    # Fetch branch
    branch_stmt = select(Branch).where(Branch.tenant_id == tenant_id)
    branch = (await db.execute(branch_stmt)).scalars().first()
    if not branch:
        print(f"Error: No branch found for Tenant {tenant_id}")
        return

    # Load categories and brands mapping
    cats = (await db.execute(select(Category).where(Category.tenant_id == tenant_id))).scalars().all()
    cat_map = {c.name.lower(): c.id for c in cats}

    brands = (await db.execute(select(Brand).where(Brand.tenant_id == tenant_id))).scalars().all()
    brand_map = {b.name.lower(): b.id for b in brands}

    print(f"\n--- Seeding Products for Tenant {tenant_id} (Branch: {branch.name}) ---")

    for p_data in product_list:
        existing = (
            await db.execute(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.sku == p_data["sku"],
                )
            )
        ).scalars().first()

        if existing:
            print(f"  * Product exists: {existing.name} (SKU: {existing.sku})")
            continue

        cat_id = cat_map.get(p_data["category_name"].lower()) or (cats[0].id if cats else None)
        brand_id = brand_map.get(p_data["brand_name"].lower()) or (brands[0].id if brands else None)

        product = Product(
            tenant_id=tenant_id,
            name=p_data["name"],
            sku=p_data["sku"],
            barcode=p_data["barcode"],
            category_id=cat_id,
            brand_id=brand_id,
            base_unit=p_data["base_unit"],
            cost_price=p_data["cost_price"],
            retail_price=p_data["retail_price"],
            wholesale_price=p_data["wholesale_price"],
            tax_rate=p_data["tax_rate"],
            is_fbr_third_schedule=False,
            is_active=True,
        )
        db.add(product)
        await db.flush()

        # Seed Branch Stock
        b_stock = BranchStock(
            tenant_id=tenant_id,
            branch_id=branch.id,
            product_id=product.id,
            quantity=p_data["stock"],
        )
        db.add(b_stock)

        # Seed UOM conversion (Carton)
        uom = ProductUOMConversion(
            tenant_id=tenant_id,
            product_id=product.id,
            unit_name="Carton",
            conversion_factor=p_data["carton_pack"],
            carton_barcode=f"CRT-{p_data['barcode']}",
            carton_wholesale_price=p_data["carton_price"],
            carton_retail_price=p_data["retail_price"] * p_data["carton_pack"],
        )
        db.add(uom)

        print(f"  + Added: {product.name} (Stock: {p_data['stock']} {product.base_unit})")

    await db.commit()
    print(f"✅ Finished seeding for Tenant {tenant_id}!")


async def main():
    async with AsyncSessionLocal() as db:
        await seed_tenant_products(db, tenant_id=5, product_list=BUSINESS_1_PRODUCTS)
        await seed_tenant_products(db, tenant_id=8, product_list=BUSINESS_2_PRODUCTS)


if __name__ == "__main__":
    asyncio.run(main())
