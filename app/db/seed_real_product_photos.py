import os
import asyncio
import urllib.request
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.modules.products.models import Product
from app.modules.attachments.models import Attachment

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploads/products"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# High quality authentic product photos
PRODUCT_PHOTO_URLS = {
    "COK-15L": (
        "cok_15l.jpg",
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/27/Coca_Cola_Flasche_-_Original_Taste.jpg/500px-Coca_Cola_Flasche_-_Original_Taste.jpg"
    ),
    "SPR-15L": (
        "spr_15l.jpg",
        "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?auto=format&fit=crop&w=500&q=80"
    ),
    "RHF-BOT-800": (
        "rhf_bot_800.jpg",
        "https://thumb.wikimedia.org/wikipedia/en/thumb/6/63/Rooh_Afza_bottle.jpg/500px-Rooh_Afza_bottle.jpg"
    ),
    "RCE-BSM-5KG": (
        "rce_bsm_5kg.jpg",
        "https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=500&q=80"
    ),
    "GRD-RCE-10KG": (
        "grd_rce_10kg.jpg",
        "https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?auto=format&fit=crop&w=500&q=80"
    ),
    "DWN-BRD-LRG": (
        "dwn_brd_lrg.jpg",
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=500&q=80"
    ),
    "SHZ-HNY-1KG": (
        "shz_hny_1kg.jpg",
        "https://images.unsplash.com/photo-1587049352846-4a222e784d38?auto=format&fit=crop&w=500&q=80"
    ),
    "NAT-KET-800": (
        "nat_ket_800.jpg",
        "https://images.unsplash.com/photo-1598514983318-2f64f8f4796c?auto=format&fit=crop&w=500&q=80"
    ),
    "NAT-CGS-800G": (
        "nat_cgs_800g.jpg",
        "https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?auto=format&fit=crop&w=500&q=80"
    ),
    "MPK-1L": (
        "mpk_1l.jpg",
        "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=500&q=80"
    ),
    "OLP-MILK-1L": (
        "olp_milk_1l.jpg",
        "https://images.unsplash.com/photo-1563636619-e9143da7973b?auto=format&fit=crop&w=500&q=80"
    ),
    "NES-BNY-260G": (
        "nes_bny_260g.jpg",
        "https://images.unsplash.com/photo-1628088062854-d1870b4553da?auto=format&fit=crop&w=500&q=80"
    ),
    "NES-EVR-375": (
        "nes_evr_375.jpg",
        "https://images.unsplash.com/photo-1579954115545-a95591f28bfc?auto=format&fit=crop&w=500&q=80"
    ),
    "NES-CER-WHT": (
        "nes_cer_wht.jpg",
        "https://images.unsplash.com/photo-1574316071802-0d684efa7cd5?auto=format&fit=crop&w=500&q=80"
    ),
    "LAY-SLT-65G": (
        "lay_slt_65g.jpg",
        "https://images.unsplash.com/photo-1566478989037-eec170784d0b?auto=format&fit=crop&w=500&q=80"
    ),
    "SOOP-FAM-112": (
        "soop_fam_112.jpg",
        "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=500&q=80"
    ),
    "CDL-CHL-24S": (
        "cdl_chl_24s.jpg",
        "https://images.unsplash.com/photo-1582058091505-f87a2e55a40f?auto=format&fit=crop&w=500&q=80"
    ),
    "DLD-OIL-5L": (
        "dld_oil_5l.jpg",
        "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=500&q=80"
    ),
    "MZN-OIL-5L": (
        "mzn_oil_5l.jpg",
        "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=500&q=80"
    ),
    "HBB-OIL-16L": (
        "hbb_oil_16l.jpg",
        "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=500&q=80"
    ),
    "DLD-GHE-1KG": (
        "dld_ghe_1kg.jpg",
        "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?auto=format&fit=crop&w=500&q=80"
    ),
    "LIP-YL-380": (
        "lip_yl_380.jpg",
        "https://images.unsplash.com/photo-1576092768241-dec231879fc3?auto=format&fit=crop&w=500&q=80"
    ),
    "TPL-DAN-430": (
        "tpl_dan_430.jpg",
        "https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=500&q=80"
    ),
    "TPL-TEZ-450": (
        "tpl_tez_450.jpg",
        "https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=500&q=80"
    ),
    "VTL-TEA-950": (
        "vtl_tea_950.jpg",
        "https://images.unsplash.com/photo-1564890369478-c89ca6d9cde9?auto=format&fit=crop&w=500&q=80"
    ),
    "SHN-BIR-50G": (
        "shn_bir_50g.jpg",
        "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=500&q=80"
    ),
    "SHN-CHK-50G": (
        "shn_chk_50g.jpg",
        "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?auto=format&fit=crop&w=500&q=80"
    ),
    "SHN-KOR-50G": (
        "shn_kor_50g.jpg",
        "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=500&q=80"
    ),
    "MHR-BIR-1KG": (
        "mhr_bir_1kg.jpg",
        "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=500&q=80"
    ),
    "NAT-PCK-1KG": (
        "nat_pck_1kg.jpg",
        "https://images.unsplash.com/photo-1589135233689-d49fa2a8b98b?auto=format&fit=crop&w=500&q=80"
    ),
    "MTC-JAM-450": (
        "mtc_jam_450.jpg",
        "https://images.unsplash.com/photo-1568651310168-9f17045cfa82?auto=format&fit=crop&w=500&q=80"
    ),
    "SHZ-MNG-250": (
        "shz_mng_250.jpg",
        "https://images.unsplash.com/photo-1546173159-315724a31696?auto=format&fit=crop&w=500&q=80"
    ),
    "LFB-TOT-115": (
        "lfb_tot_115.jpg",
        "https://images.unsplash.com/photo-1607006310486-53c898c63eb6?auto=format&fit=crop&w=500&q=80"
    ),
    "SRF-EXC-1KG": (
        "srf_exc_1kg.jpg",
        "https://images.unsplash.com/photo-1610557892470-55d9e80c0bce?auto=format&fit=crop&w=500&q=80"
    ),
    "KNR-NDL-66G": (
        "knr_ndl_66g.jpg",
        "https://images.unsplash.com/photo-1612927601601-6638404737ce?auto=format&fit=crop&w=500&q=80"
    ),
    "KNR-CUB-24S": (
        "knr_cub_24s.jpg",
        "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=500&q=80"
    ),
    "PUL-CHN-50KG": (
        "pul_chn_50kg.jpg",
        "https://images.unsplash.com/photo-1585994192701-f1a505c817ea?auto=format&fit=crop&w=500&q=80"
    ),
    "PUL-MNG-25KG": (
        "pul_mng_25kg.jpg",
        "https://images.unsplash.com/photo-1585994192701-f1a505c817ea?auto=format&fit=crop&w=500&q=80"
    ),
    "FLR-CHK-20KG": (
        "flr_chk_20kg.jpg",
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=500&q=80"
    ),
    "FAJ-CRN-500": (
        "faj_crn_500.jpg",
        "https://images.unsplash.com/photo-1582401656496-9d75f95f9018?auto=format&fit=crop&w=500&q=80"
    ),
    "RFH-CST-1KG": (
        "rfh_cst_1kg.jpg",
        "https://images.unsplash.com/photo-1551024709-8f23befc6f87?auto=format&fit=crop&w=500&q=80"
    ),
}

def download_image(url: str, dest_path: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            with open(dest_path, "wb") as f:
                f.write(content)
            return len(content)
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

async def main():
    print("Downloading authentic realistic product packshot photos...")
    for sku, (filename, url) in PRODUCT_PHOTO_URLS.items():
        file_path = os.path.join(UPLOAD_DIR, filename)
        if not os.path.exists(file_path) or os.path.getsize(file_path) < 1000:
            sz = download_image(url, file_path)
            print(f"[{sku}] -> {filename} ({sz} bytes)")
        else:
            print(f"[{sku}] -> {filename} (Already exists: {os.path.getsize(file_path)} bytes)")

    # Update database
    async with AsyncSessionLocal() as session:
        prods_res = await session.execute(select(Product))
        products = prods_res.scalars().all()
        updated_count = 0

        for p in products:
            if p.sku in PRODUCT_PHOTO_URLS:
                filename, _ = PRODUCT_PHOTO_URLS[p.sku]
                relative_path = f"/uploads/products/{filename}"
                p.image_url = relative_path
                updated_count += 1

                # Update or insert in attachments
                att_res = await session.execute(
                    select(Attachment).where(
                        Attachment.attachable_type == "Product",
                        Attachment.attachable_id == p.id,
                    )
                )
                att = att_res.scalars().first()
                if att:
                    att.file_name = filename
                    att.file_path = relative_path
                    att.file_type = "image/jpeg"
                else:
                    new_att = Attachment(
                        tenant_id=p.tenant_id,
                        attachable_type="Product",
                        attachable_id=p.id,
                        file_name=filename,
                        file_path=relative_path,
                        file_type="image/jpeg",
                        file_size=os.path.getsize(os.path.join(UPLOAD_DIR, filename)) if os.path.exists(os.path.join(UPLOAD_DIR, filename)) else 10000,
                        is_primary=True,
                        title=f"{p.name} Visual Packshot",
                    )
                    session.add(new_att)

        await session.commit()
        print(f"Successfully updated {updated_count} products with realistic product packshots!")

if __name__ == "__main__":
    asyncio.run(main())
