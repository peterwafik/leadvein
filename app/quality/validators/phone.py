from __future__ import annotations
import phonenumbers

_TYPE = {phonenumbers.PhoneNumberType.MOBILE: "mobile",
         phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
         phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile"}


def validate_phone(phone: str, *, region: str = "GB") -> dict:
    phone = (phone or "").strip()
    if not phone:
        return {"present": False, "validated": False, "line_type": "unknown"}
    try:
        num = phonenumbers.parse(phone, region)
        valid = phonenumbers.is_valid_number(num)
        line = _TYPE.get(phonenumbers.number_type(num), "unknown")
    except Exception:
        valid, line = False, "unknown"
    # line_type is numbering-plan metadata, NOT a liveness claim.
    return {"present": True, "validated": bool(valid), "line_type": line}
