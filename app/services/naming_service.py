"""
NamingService - สร้างชื่อ Campaign / AdGroup / Ad ตามมาตรฐานกลาง

=== Naming Pattern V2 (New - with Objective Code) ===
- Campaign: [Products]_<OBJ>_BOOSTX_<Date>
  เช่น: [J3]_VV_BOOSTX_2025-12-05

- AdGroup:  [Products]_<STRUCT>_<OBJ>_(<Targeting>)_<Style>#<Num>
  เช่น: [J3]_ABX_VV_(F_RETAIL_18_54)_SALE#01

- Ad:       [Products]_<STRUCT>_<OBJ>_(<Targeting>)_<ItemID>
  เช่น: [J3]_ABX_VV_(F_RETAIL_18_54)_7579992882990615826

=== Naming Pattern V1 (Legacy - VV Only) ===
- Campaign: [Products]_ACEBOOSTX_<Date>
  เช่น: [J3]_ACEBOOSTX_2025-12-05

- AdGroup ACE: [Products]_ACE_<Targeting>_<ItemId>
  เช่น: [J3]_ACE_<F_RETAIL_18_54>_7579992882990615826

- AdGroup ABX: [Products]_ABX_(<Targeting>)_<Style>#<Num>
  เช่น: [J3]_ABX_(F_RETAIL_18_54)_SALE#01

- Ad:       [Products]_<STRUCT>_<Targeting>_<ItemID>_<Date>
  เช่น: [J3]_ACE_<F_RETAIL_18_54>_7579992882990615826_2025-12-05

Objective Codes:
- VV = Video Views (หลัก)
- RCH = Reach
- TRF = Traffic
- CVN = Conversions

Structure Codes:
- ACE = 1 AdGroup : 1 Content
- ABX = 1 AdGroup : N Contents
"""

from datetime import date
from typing import List, Optional


def _format_product_codes(codes: List[str]) -> str:
    """แปลง ['A1','D1'] -> "[A1][D1]" โดยเรียงตามตัวอักษร"""
    if not codes:
        return ""
    normalized = [str(c).strip().upper() for c in codes if c]
    normalized = sorted(set(normalized))
    return "".join(f"[{c}]" for c in normalized)


def _today_date_code() -> str:
    """สร้าง date code จากวันนี้ เช่น 2025-12-05"""
    return date.today().isoformat()


def _today_period_code() -> str:
    """สร้าง period code แบบย่อจากวันที่วันนี้ เช่น 2024-03-15 -> 2403M"""
    today = date.today()
    return f"{str(today.year)[2:]}{today.month:02d}M"


class NamingService:
    """Service for generating standardized names for Campaign/AdGroup/Ad"""
    
    @staticmethod
    def generate_campaign_name(
        product_codes: List[str],
        objective_code: str = "VV",
        date_code: Optional[str] = None,
    ) -> str:
        """
        สร้างชื่อ Campaign ตาม pattern:
            [Products]_<OBJ>_BOOSTX_<Date>

        ตัวอย่าง:
            [J3]_VV_BOOSTX_2025-12-05
            [A1][D1]_RCH_BOOSTX_2025-12-05

        Args:
            product_codes: รายการ SKU เช่น ["A1","D1","J7"]
            objective_code: VV, RCH, TRF, CVN
            date_code: วันที่ (ไม่ใส่จะใช้วันนี้)
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        obj = (objective_code or "VV").upper()
        
        if date_code is None:
            date_code = _today_date_code()

        return f"{group_part}_{obj}_BOOSTX_{date_code}"

    @staticmethod
    def generate_adgroup_name(
        product_codes: List[str],
        structure_code: str = "ACE",
        objective_code: str = "VV",
        targeting_code: Optional[str] = None,
        content_style_code: Optional[str] = None,
        index: int = 1,
    ) -> str:
        """
        สร้างชื่อ AdGroup ตาม pattern:
            [Products]_<STRUCT>_<OBJ>_(<Targeting>)_<Style>#<Num>

        ตัวอย่าง:
            [J3]_ABX_VV_(F_RETAIL_18_54)_SALE#01
            [J3]_ACE_VV_(MF_OILCONTROL_18_44)_ECOM#03

        Args:
            product_codes: รายการ SKU
            structure_code: ACE หรือ ABX
            objective_code: VV, RCH, TRF, CVN
            targeting_code: โค้ด TargetingTemplate เช่น "MF_ACNE_18_34"
            content_style_code: SALE / ECOM / REV / BR
            index: ลำดับ (default 1)
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        struct = (structure_code or "ACE").upper()
        obj = (objective_code or "VV").upper()

        base = f"{group_part}_{struct}_{obj}"

        if targeting_code:
            base += f"_({targeting_code})"

        if content_style_code:
            base += f"_{content_style_code.upper()}"

        base += f"#{index:02d}"

        return base

    @staticmethod
    def generate_ad_name(
        product_codes: List[str],
        structure_code: str = "ACE",
        objective_code: str = "VV",
        targeting_code: Optional[str] = None,
        content_code: Optional[str] = None,
    ) -> str:
        """
        สร้างชื่อ Ad ตาม pattern:
            [Products]_<STRUCT>_<OBJ>_(<Targeting>)_<ItemID>

        ตัวอย่าง:
            [J3]_ABX_VV_(F_RETAIL_18_54)_7579992882990615826

        Args:
            product_codes: รายการ SKU
            structure_code: ACE หรือ ABX
            objective_code: VV, RCH, TRF, CVN
            targeting_code: โค้ด TargetingTemplate
            content_code: item_id หรือ content code
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        struct = (structure_code or "ACE").upper()
        obj = (objective_code or "VV").upper()

        base = f"{group_part}_{struct}_{obj}"

        if targeting_code:
            base += f"_({targeting_code})"

        if content_code:
            base += f"_{content_code}"

        return base

    # ============================================
    # Legacy V1 Methods (for VV objective only)
    # Compatible with old WeBoostX system
    # ============================================
    
    @staticmethod
    def generate_campaign_name_v1(
        product_codes: List[str],
        date_code: Optional[str] = None,
    ) -> str:
        """
        Legacy V1 Campaign name format (VV only):
            [Products]_ACEBOOSTX_<Date>

        ตัวอย่าง:
            [J3]_ACEBOOSTX_2025-12-05
            [A1][D1]_ACEBOOSTX_2025-12-05
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        
        if date_code is None:
            date_code = _today_date_code()

        return f"{group_part}_ACEBOOSTX_{date_code}"

    @staticmethod
    def generate_adgroup_name_v1_ace(
        product_codes: List[str],
        targeting_code: str,
        item_id: str,
    ) -> str:
        """
        Legacy V1 AdGroup ACE name format:
            [Products]_ACE_<Targeting>_<ItemId>

        ตัวอย่าง:
            [J3]_ACE_<F_RETAIL_18_54>_7579992882990615826
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        return f"{group_part}_ACE_<{targeting_code}>_{item_id}"

    @staticmethod
    def generate_adgroup_name_v1_abx(
        product_codes: List[str],
        targeting_code: str,
        content_style_code: str,
        index: int = 1,
    ) -> str:
        """
        Legacy V1 AdGroup ABX name format:
            [Products]_ABX_(<Targeting>)_<Style>#<Num>

        ตัวอย่าง:
            [J3]_ABX_(F_RETAIL_18_54)_SALE#01
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        style = (content_style_code or "SALE").upper()
        return f"{group_part}_ABX_({targeting_code})_{style}#{index:02d}"

    @staticmethod
    def generate_ad_name_v1(
        product_codes: List[str],
        structure_code: str,
        targeting_code: str,
        item_id: str,
        date_code: Optional[str] = None,
    ) -> str:
        """
        Legacy V1 Ad name format:
            [Products]_<STRUCT>_<Targeting>_<ItemId>_<Date>

        ตัวอย่าง:
            [J3]_ACE_<F_RETAIL_18_54>_7579992882990615826_2025-12-05
        """
        group_part = _format_product_codes(product_codes) or "[UNKN]"
        struct = (structure_code or "ACE").upper()
        
        if date_code is None:
            date_code = _today_date_code()

        return f"{group_part}_{struct}_<{targeting_code}>_{item_id}_{date_code}"

    # ============================================
    # Unified Methods (auto-select V1 or V2)
    # ============================================
    
    @staticmethod
    def generate_names(
        product_codes: List[str],
        structure_code: str,
        objective_code: str,
        targeting_code: str,
        item_id: str,
        content_style_code: Optional[str] = None,
        index: int = 1,
        use_legacy: bool = False,
    ) -> dict:
        """
        Generate all names (Campaign, AdGroup, Ad) with auto-select format.
        
        Args:
            product_codes: รายการ SKU
            structure_code: ACE or ABX
            objective_code: VV, RCH, TRF, CVN
            targeting_code: Targeting code
            item_id: TikTok item ID
            content_style_code: SALE, ECOM, REV, BR
            index: Running number
            use_legacy: Force legacy format (only works with VV)
        
        Returns:
            {
                'campaign_name': str,
                'adgroup_name': str,
                'ad_name': str,
                'format_version': 'v1' or 'v2'
            }
        """
        obj = (objective_code or "VV").upper()
        struct = (structure_code or "ACE").upper()
        
        # Use legacy format only if:
        # 1. Explicitly requested AND objective is VV
        # 2. Or objective is VV and we want backward compatibility
        use_v1 = use_legacy and obj == "VV"
        
        if use_v1:
            # Legacy V1 Format
            campaign_name = NamingService.generate_campaign_name_v1(product_codes)
            
            if struct == "ACE":
                adgroup_name = NamingService.generate_adgroup_name_v1_ace(
                    product_codes, targeting_code, item_id
                )
            else:  # ABX
                adgroup_name = NamingService.generate_adgroup_name_v1_abx(
                    product_codes, targeting_code, content_style_code or "SALE", index
                )
            
            ad_name = NamingService.generate_ad_name_v1(
                product_codes, struct, targeting_code, item_id
            )
            
            return {
                'campaign_name': campaign_name,
                'adgroup_name': adgroup_name,
                'ad_name': ad_name,
                'format_version': 'v1'
            }
        else:
            # New V2 Format
            campaign_name = NamingService.generate_campaign_name(
                product_codes, obj
            )
            adgroup_name = NamingService.generate_adgroup_name(
                product_codes, struct, obj, targeting_code, content_style_code, index
            )
            ad_name = NamingService.generate_ad_name(
                product_codes, struct, obj, targeting_code, item_id
            )
            
            return {
                'campaign_name': campaign_name,
                'adgroup_name': adgroup_name,
                'ad_name': ad_name,
                'format_version': 'v2'
            }
    
    # ============================================
    # Name Parser (detect format from existing name)
    # ============================================
    
    @staticmethod
    def detect_format_version(name: str) -> str:
        """
        Detect naming format version from existing name.
        
        Returns: 'v1', 'v2', or 'unknown'
        """
        import re
        
        # V1 patterns
        if '_ACEBOOSTX_' in name:
            return 'v1'  # Legacy campaign
        if re.search(r'_ACE_<[^>]+>_', name):
            return 'v1'  # Legacy ACE adgroup/ad
        if re.search(r'_ABX_\([^)]+\)_[A-Z]+#\d+$', name):
            return 'v1'  # Legacy ABX adgroup (no objective code)
        
        # V2 patterns
        if re.search(r'_(VV|RCH|TRF|CVN|APP|LEAD|GMV|AWR|ENG|SAL)_BOOSTX_', name):
            return 'v2'  # V2 campaign
        if re.search(r'_(ACE|ABX)_(VV|RCH|TRF|CVN)_', name):
            return 'v2'  # V2 adgroup/ad
        
        return 'unknown'
    
    @staticmethod
    def is_legacy_format(name: str) -> bool:
        """Check if name uses legacy V1 format"""
        return NamingService.detect_format_version(name) == 'v1'
