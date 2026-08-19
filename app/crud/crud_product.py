from sqlalchemy.orm import Session
from typing import Optional
from app.models.product import Product, ProductVariant
from app.schemas.product import ProductCreate

def get_product(db: Session, product_id: int, business_id: Optional[int] = None):
    query = db.query(Product).filter(Product.id == product_id)
    if business_id is not None:
        query = query.filter(Product.business_id == business_id)
    return query.first()

def get_products(db: Session, skip: int = 0, limit: int = 100, business_id: Optional[int] = None):
    query = db.query(Product)
    if business_id is not None:
        query = query.filter(Product.business_id == business_id)
    return query.offset(skip).limit(limit).all()

def create_product(db: Session, product_in: ProductCreate, business_id: Optional[int] = None):
    db_product = Product(
        name=product_in.name,
        description=product_in.description,
        image_url=product_in.image_url,
        base_price=product_in.base_price,
        cost_price=product_in.cost_price,
        category_id=product_in.category_id,
        brand_id=product_in.brand_id,
        business_id=business_id
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Add variants
    for variant in product_in.variants:
        db_variant = ProductVariant(
            product_id=db_product.id,
            size=variant.size,
            color=variant.color,
            sku=variant.sku,
            barcode=variant.barcode,
            stock_quantity=variant.stock_quantity,
            price_adjustment=variant.price_adjustment
        )
        db.add(db_variant)
    
    db.commit()
    db.refresh(db_product)
    return db_product

def update_product(db: Session, db_product: Product, product_in: ProductCreate):
    db_product.name = product_in.name
    db_product.description = product_in.description
    db_product.image_url = product_in.image_url
    db_product.base_price = product_in.base_price
    db_product.cost_price = product_in.cost_price
    db_product.category_id = product_in.category_id
    db_product.brand_id = product_in.brand_id
    
    # Update first variant stock if provided
    if product_in.variants:
        variant_in = product_in.variants[0]
        db_variant = db.query(ProductVariant).filter(ProductVariant.product_id == db_product.id).first()
        if db_variant:
            db_variant.stock_quantity = variant_in.stock_quantity
        else:
            new_variant = ProductVariant(
                product_id=db_product.id,
                size=variant_in.size,
                color=variant_in.color,
                sku=variant_in.sku,
                stock_quantity=variant_in.stock_quantity
            )
            db.add(new_variant)
    db.commit()
    db.refresh(db_product)
    return db_product

def delete_product(db: Session, db_product: Product):
    db.delete(db_product)
    db.commit()
    return db_product
