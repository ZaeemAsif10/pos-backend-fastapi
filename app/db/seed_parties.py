import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import Tenant
from app.modules.parties.models import DeliveryArea, Customer, Supplier


SUPPLIERS_DATA = [
    {
        "code": "SUP-NES",
        "company_name": "Nestlé Pakistan Limited",
        "contact_person": "Muhammad Usman (Distribution Head)",
        "phone": "042-35988000",
        "email": "orders@nestle.pk",
        "ntn": "0814441-7",
        "strn": "03008144417",
        "payment_terms_days": 30,
        "current_balance": 185000.0,
        "opening_balance": 150000.0,
        "bank_name": "Habib Bank Limited (HBL)",
        "bank_account_number": "00427901234503",
        "bank_iban": "PK36HABB0000427901234503",
        "city": "Lahore",
        "address": "308-Upper Mall, Anand Road, Lahore",
    },
    {
        "code": "SUP-NAT",
        "company_name": "National Foods Limited",
        "contact_person": "Tariq Jameel",
        "phone": "021-38148000",
        "email": "supplychain@nfoods.com",
        "ntn": "0710123-4",
        "strn": "02007101234",
        "payment_terms_days": 21,
        "current_balance": 94000.0,
        "opening_balance": 80000.0,
        "bank_name": "Meezan Bank Limited",
        "bank_account_number": "01020100456789",
        "bank_iban": "PK19MEZN0001020100456789",
        "city": "Karachi",
        "address": "F-133, S.I.T.E., Karachi",
    },
    {
        "code": "SUP-SHN",
        "company_name": "Shan Foods (Pvt) Ltd",
        "contact_person": "Asif Siddiqui (Area Manager)",
        "phone": "021-35076161",
        "email": "sales@shanfoods.com",
        "ntn": "1428901-5",
        "strn": "02011428901",
        "payment_terms_days": 15,
        "current_balance": 62000.0,
        "opening_balance": 50000.0,
        "bank_name": "Bank Alfalah Limited",
        "bank_account_number": "55015000234123",
        "bank_iban": "PK45ALFH0055015000234123",
        "city": "Karachi",
        "address": "29-Sector 23, Korangi Industrial Area, Karachi",
    },
    {
        "code": "SUP-DLD",
        "company_name": "Dalda Foods Limited",
        "contact_person": "Rehan Sheikh",
        "phone": "021-35610072",
        "email": "orders@daldafoods.com",
        "ntn": "0698124-9",
        "strn": "02000698124",
        "payment_terms_days": 30,
        "current_balance": 140000.0,
        "opening_balance": 120000.0,
        "bank_name": "MCB Bank Limited",
        "bank_account_number": "00234509876123",
        "bank_iban": "PK89MUCB0000234509876123",
        "city": "Karachi",
        "address": "7-A, Muhammad Ali Housing Society, Karachi",
    },
    {
        "code": "SUP-ENG",
        "company_name": "FrieslandCampina Engro Pakistan",
        "contact_person": "Kamran Hafeez",
        "phone": "042-35787600",
        "email": "distributors@engrofoods.com",
        "ntn": "2689123-1",
        "strn": "03002689123",
        "payment_terms_days": 15,
        "current_balance": 88000.0,
        "opening_balance": 75000.0,
        "bank_name": "Standard Chartered Bank",
        "bank_account_number": "01034567890123",
        "bank_iban": "PK22SCBL0001034567890123",
        "city": "Lahore",
        "address": "5th Floor, The Harbor Front, Clifton, Karachi",
    },
    {
        "code": "SUP-UNI",
        "company_name": "Unilever Pakistan Limited",
        "contact_person": "Bilal Munir",
        "phone": "021-35660062",
        "email": "custservice@unilever.com",
        "ntn": "0712398-3",
        "strn": "02000712398",
        "payment_terms_days": 30,
        "current_balance": 210000.0,
        "opening_balance": 190000.0,
        "bank_name": "United Bank Limited (UBL)",
        "bank_account_number": "00123456789012",
        "bank_iban": "PK55UNIL0000012345678901",
        "city": "Karachi",
        "address": "Avari Plaza, Fatima Jinnah Road, Karachi",
    },
]

AREAS_DATA = [
    {
        "code": "ROUTE-LHR-01",
        "name": "DHA Phase 1-6 & Main Boulevard",
        "city": "Lahore",
        "delivery_days": "Monday, Thursday",
        "description": "Premium retail marts and express counters in DHA Lahore",
    },
    {
        "code": "ROUTE-LHR-02",
        "name": "Gulberg & Jail Road Market",
        "city": "Lahore",
        "delivery_days": "Tuesday, Friday",
        "description": "High volume wholesale market and commercial supermarkets",
    },
    {
        "code": "ROUTE-LHR-03",
        "name": "Model Town & Faisal Town Beat",
        "city": "Lahore",
        "delivery_days": "Wednesday, Saturday",
        "description": "Residential stores, mini marts, and local groceries",
    },
    {
        "code": "ROUTE-KHI-01",
        "name": "Gulshan-e-Iqbal & Rashid Minhas",
        "city": "Karachi",
        "delivery_days": "Monday, Wednesday",
        "description": "High density retail market route",
    },
]

CUSTOMERS_DATA = [
    {
        "code": "CUST-ALF",
        "business_name": "Al-Fatah Supermarket (Mall Road)",
        "owner_name": "Sheikh Nadeem Ahmed",
        "phone": "0300-4567891",
        "whatsapp_number": "0300-4567891",
        "email": "mallroad@alfatah.pk",
        "cnic": "35201-1234567-1",
        "ntn": "2345678-1",
        "customer_type": "key_account",
        "credit_limit": 500000.0,
        "credit_days": 15,
        "current_balance": 125000.0,
        "opening_balance": 100000.0,
        "city": "Lahore",
        "address": "Mall Road, Near Regal Chowk, Lahore",
    },
    {
        "code": "CUST-IMT",
        "business_name": "Imtiaz Super Market (Gulshan Branch)",
        "owner_name": "Farhan Imtiaz Abbasi",
        "phone": "0321-8234567",
        "whatsapp_number": "0321-8234567",
        "email": "purchasing@imtiaz.com.pk",
        "cnic": "42101-7654321-3",
        "ntn": "3456789-2",
        "customer_type": "key_account",
        "credit_limit": 1000000.0,
        "credit_days": 30,
        "current_balance": 450000.0,
        "opening_balance": 350000.0,
        "city": "Karachi",
        "address": "University Road, Gulshan-e-Iqbal Block 13, Karachi",
    },
    {
        "code": "CUST-SAV",
        "business_name": "Save Mart Cash & Carry",
        "owner_name": "Malik Arshad Mehmood",
        "phone": "0333-5123456",
        "whatsapp_number": "0333-5123456",
        "email": "savemart.ops@gmail.com",
        "cnic": "37405-9876543-5",
        "customer_type": "wholesaler",
        "credit_limit": 300000.0,
        "credit_days": 14,
        "current_balance": 82000.0,
        "opening_balance": 60000.0,
        "city": "Rawalpindi",
        "address": "Satellite Town, Commercial Market, Rawalpindi",
    },
    {
        "code": "CUST-MAD",
        "business_name": "Madina General Store & Departmental",
        "owner_name": "Haji Abdul Ghafoor",
        "phone": "0301-7654321",
        "whatsapp_number": "0301-7654321",
        "cnic": "35202-3456789-9",
        "customer_type": "retailer",
        "credit_limit": 100000.0,
        "credit_days": 7,
        "current_balance": 38500.0,
        "opening_balance": 25000.0,
        "city": "Lahore",
        "address": "Main Market Gulberg 2, Lahore",
    },
    {
        "code": "CUST-BIS",
        "business_name": "Bismillah Traders & Grocery",
        "owner_name": "Muhammad Bilal",
        "phone": "0345-9876543",
        "whatsapp_number": "0345-9876543",
        "cnic": "35201-5678901-7",
        "customer_type": "retailer",
        "credit_limit": 80000.0,
        "credit_days": 7,
        "current_balance": 18200.0,
        "opening_balance": 15000.0,
        "city": "Lahore",
        "address": "Sector Y, Phase 3, DHA Lahore",
    },
    {
        "code": "CUST-RAH",
        "business_name": "Rahman Karyana & Cold Corner",
        "owner_name": "M. Rehman Butt",
        "phone": "0312-3456789",
        "cnic": "34101-2345678-5",
        "customer_type": "retailer",
        "credit_limit": 50000.0,
        "credit_days": 7,
        "current_balance": 12400.0,
        "opening_balance": 10000.0,
        "city": "Gujranwala",
        "address": "G.T. Road, Near Model Town Chowk, Gujranwala",
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        print(f"Found {len(tenants)} businesses in system.")

        for t in tenants:
            print(f"\n--- Seeding Tenant {t.id}: {t.name} ---")

            # 1. Delivery Areas
            area_map = {}
            for a_data in AREAS_DATA:
                existing_a = (
                    await db.execute(
                        select(DeliveryArea).where(
                            DeliveryArea.tenant_id == t.id,
                            DeliveryArea.code == a_data["code"],
                        )
                    )
                ).scalars().first()

                if not existing_a:
                    area = DeliveryArea(tenant_id=t.id, **a_data)
                    db.add(area)
                    await db.flush()
                    area_map[area.code] = area.id
                    print(f"  + Added Area: {area.name}")
                else:
                    area_map[existing_a.code] = existing_a.id

            # 2. Suppliers
            for s_data in SUPPLIERS_DATA:
                existing_s = (
                    await db.execute(
                        select(Supplier).where(
                            Supplier.tenant_id == t.id,
                            Supplier.code == s_data["code"],
                        )
                    )
                ).scalars().first()

                if not existing_s:
                    sup = Supplier(tenant_id=t.id, **s_data)
                    db.add(sup)
                    print(f"  + Added Supplier: {sup.company_name}")

            # 3. Customers
            for idx, c_data in enumerate(CUSTOMERS_DATA):
                existing_c = (
                    await db.execute(
                        select(Customer).where(
                            Customer.tenant_id == t.id,
                            Customer.code == c_data["code"],
                        )
                    )
                ).scalars().first()

                if not existing_c:
                    assigned_area_code = list(area_map.keys())[idx % len(area_map)] if area_map else None
                    area_id = area_map.get(assigned_area_code) if assigned_area_code else None

                    cust = Customer(
                        tenant_id=t.id,
                        area_id=area_id,
                        **c_data,
                    )
                    db.add(cust)
                    print(f"  + Added Customer: {cust.business_name} (Area ID: {area_id})")

            await db.commit()
            print(f"✅ Tenant {t.id} Seeded Successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
