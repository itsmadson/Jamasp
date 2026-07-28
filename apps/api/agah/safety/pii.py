"""PII classification and masking.

Runs server-side before any prompt is assembled. The Describer's only input is the
Profiler's output, so a HIGH-class value has no path to an external LLM provider.
Patterns cover Persian and English column names, since target databases mix both.
"""

import re

from agah.models.entity import PIIClass

HIGH_NAME_PATTERNS = [
    r"national_?id", r"کدملی", r"کد_?ملی", r"ssn", r"passport", r"شماره_?گذرنامه",
    r"salary", r"حقوق", r"دستمزد", r"iban", r"شبا", r"card_?number", r"شماره_?کارت",
    r"account_?number", r"شماره_?حساب", r"password", r"secret", r"token",
]
LOW_NAME_PATTERNS = [
    r"mobile", r"phone", r"tel", r"موبایل", r"تلفن", r"همراه",
    r"email", r"ایمیل", r"address", r"آدرس", r"نشانی",
    r"birth", r"تولد", r"first_?name", r"last_?name", r"full_?name", r"نام",
]

IRAN_MOBILE = re.compile(r"^09\d{9}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
IRAN_IBAN = re.compile(r"^IR\d{24}$")
CARD = re.compile(r"^\d{16}$")
NATIONAL_ID = re.compile(r"^\d{10}$")


def _matches(patterns: list[str], name: str) -> bool:
    lowered = name.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def _valid_iranian_national_id(value: str) -> bool:
    if not NATIONAL_ID.match(value) or len(set(value)) == 1:
        return False
    checksum = sum(int(value[index]) * (10 - index) for index in range(9)) % 11
    control = int(value[9])
    return control == checksum if checksum < 2 else control == 11 - checksum


def classify_column(name: str, data_type: str, samples: list[object]) -> PIIClass:
    if _matches(HIGH_NAME_PATTERNS, name):
        return PIIClass.HIGH
    if _matches(LOW_NAME_PATTERNS, name):
        return PIIClass.LOW

    strings = [str(sample) for sample in samples if sample is not None]
    if strings:
        if all(IRAN_IBAN.match(s) or CARD.match(s) for s in strings):
            return PIIClass.HIGH
        if all(_valid_iranian_national_id(s) for s in strings):
            return PIIClass.HIGH
        if all(IRAN_MOBILE.match(s) or EMAIL.match(s) for s in strings):
            return PIIClass.LOW
    return PIIClass.NONE


def mask_value(value: object, pii_class: PIIClass) -> object | None:
    if pii_class is PIIClass.HIGH:
        return None
    if pii_class is PIIClass.NONE or value is None:
        return value

    text = str(value)
    if EMAIL.match(text):
        local, _, domain = text.partition("@")
        return f"{local[0]}***@{domain}"
    if IRAN_MOBILE.match(text):
        return f"{text[:4]}***{text[-4:]}"
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"
