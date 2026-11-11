import os
import asyncio
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.modules.products.models import Product, Category, Brand
from app.modules.attachments.models import Attachment

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploads/products"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Visual themes per category
THEMES = {
    "dairy, milk & cream": {
        "bg_from": "#0284c7",
        "bg_to": "#0369a1",
        "accent": "#38bdf8",
        "icon": "🥛",
        "tag": "FRESH DAIRY",
    },
    "tea, coffee & whitener": {
        "bg_from": "#b45309",
        "bg_to": "#78350f",
        "accent": "#f59e0b",
        "icon": "☕",
        "tag": "PREMIUM TEA",
    },
    "spices, recipe mixes & salt": {
        "bg_from": "#b91c1c",
        "bg_to": "#7f1d1d",
        "accent": "#f87171",
        "icon": "🌶️",
        "tag": "PURE SPICE",
    },
    "grains, flour & rice": {
        "bg_from": "#ca8a04",
        "bg_to": "#854d0e",
        "accent": "#facc15",
        "icon": "🌾",
        "tag": "FINE GRAIN",
    },
    "beverages & drinks": {
        "bg_from": "#be123c",
        "bg_to": "#881337",
        "accent": "#fb7185",
        "icon": "🥤",
        "tag": "CHILLED DRINK",
    },
    "snacks, biscuits & confectionery": {
        "bg_from": "#ea580c",
        "bg_to": "#9a3412",
        "accent": "#fb923c",
        "icon": "🍪",
        "tag": "CRISPY SNACK",
    },
    "bakery & sweets": {
        "bg_from": "#d97706",
        "bg_to": "#92400e",
        "accent": "#fcd34d",
        "icon": "🍞",
        "tag": "FRESH BAKERY",
    },
    "personal care & soap": {
        "bg_from": "#0d9488",
        "bg_to": "#115e59",
        "accent": "#2dd4bf",
        "icon": "🧼",
        "tag": "CARE & HYGIENE",
    },
    "household & cleaning": {
        "bg_from": "#2563eb",
        "bg_to": "#1e40af",
        "accent": "#60a5fa",
        "icon": "✨",
        "tag": "HOME CARE",
    },
}

DEFAULT_THEME = {
    "bg_from": "#475569",
    "bg_to": "#1e293b",
    "accent": "#94a3b8",
    "icon": "📦",
    "tag": "PRODUCT PACK",
}


def generate_product_svg(name: str, brand: str, category: str, sku: str, price: float) -> str:
    theme = THEMES.get(category.lower().strip(), DEFAULT_THEME)

    # Clean display name (max 2 lines)
    words = name.split()
    line1 = " ".join(words[:3])
    line2 = " ".join(words[3:6]) if len(words) > 3 else ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{theme['bg_from']}" />
      <stop offset="100%" stop-color="{theme['bg_to']}" />
    </linearGradient>
    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" flood-opacity="0.35"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="400" height="300" rx="20" fill="url(#bgGrad)" />

  <!-- Subtle Pattern Circles -->
  <circle cx="360" cy="40" r="120" fill="white" opacity="0.04" />
  <circle cx="40" cy="260" r="90" fill="white" opacity="0.04" />

  <!-- Top Badge / Brand -->
  <rect x="24" y="24" width="160" height="26" rx="6" fill="black" opacity="0.25" />
  <text x="34" y="42" fill="{theme['accent']}" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-weight="700" letter-spacing="1">{brand.upper()[:20]}</text>

  <!-- Category Tag -->
  <rect x="280" y="24" width="96" height="24" rx="12" fill="white" opacity="0.18" />
  <text x="328" y="40" text-anchor="middle" fill="#ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="9" font-weight="800" letter-spacing="0.5">{theme['tag']}</text>

  <!-- Main Product Icon Card -->
  <g filter="url(#shadow)">
    <rect x="145" y="70" width="110" height="110" rx="22" fill="#ffffff" opacity="0.95" />
    <text x="200" y="145" text-anchor="middle" font-size="54">{theme['icon']}</text>
  </g>

  <!-- Product Title -->
  <text x="200" y="215" text-anchor="middle" fill="#ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="16" font-weight="800">
    {line1}
  </text>
  {f'<text x="200" y="235" text-anchor="middle" fill="#f1f5f9" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="600">{line2}</text>' if line2 else ''}

  <!-- Bottom Footer Pill -->
  <rect x="24" y="254" width="352" height="30" rx="8" fill="black" opacity="0.3" />
  <text x="36" y="274" fill="#cbd5e1" font-family="ui-monospace, monospace" font-size="11" font-weight="600">SKU: {sku}</text>
  <text x="364" y="274" text-anchor="end" fill="#ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="900">Rs {int(price):,}</text>
</svg>"""
    return svg


async def main():
    async with AsyncSessionLocal() as db:
        # Fetch all products across all tenants
        prods_res = await db.execute(
            select(Product, Category.name, Brand.name)
            .join(Category, Product.category_id == Category.id)
            .outerjoin(Brand, Product.brand_id == Brand.id)
        )
        products_data = prods_res.all()

        print(f"Found {len(products_data)} products to attach polymorphic images to...")

        for prod, cat_name, brand_name in products_data:
            sku_slug = "".join(c if c.isalnum() else "_" for c in prod.sku.lower())
            filename = f"{sku_slug}.svg"
            filepath = f"/uploads/products/{filename}"
            full_local_path = os.path.join(UPLOAD_DIR, filename)

            # Generate and write SVG asset
            svg_content = generate_product_svg(
                name=prod.name,
                brand=brand_name or "Official",
                category=cat_name,
                sku=prod.sku,
                price=float(prod.retail_price or 0.0),
            )

            with open(full_local_path, "w", encoding="utf-8") as f:
                f.write(svg_content)

            file_size = len(svg_content.encode("utf-8"))

            # Check if attachment already exists in polymorphic attachments table
            existing_att = (
                await db.execute(
                    select(Attachment).where(
                        Attachment.tenant_id == prod.tenant_id,
                        Attachment.attachable_type == "Product",
                        Attachment.attachable_id == prod.id,
                    )
                )
            ).scalars().first()

            if existing_att:
                existing_att.file_name = filename
                existing_att.file_path = filepath
                existing_att.file_type = "image/svg+xml"
                existing_att.file_size = file_size
                existing_att.is_primary = True
                existing_att.title = prod.name
            else:
                att = Attachment(
                    tenant_id=prod.tenant_id,
                    attachable_type="Product",
                    attachable_id=prod.id,
                    file_name=filename,
                    file_path=filepath,
                    file_type="image/svg+xml",
                    file_size=file_size,
                    is_primary=True,
                    title=prod.name,
                )
                db.add(att)

            # Keep Product.image_url in sync with primary attachment
            prod.image_url = filepath

            print(f"  + Attached: {prod.name} -> {filepath} (Tenant {prod.tenant_id})")

        await db.commit()
        print("\n✅ Successfully generated and saved polymorphic attachments for ALL products!")


if __name__ == "__main__":
    asyncio.run(main())
