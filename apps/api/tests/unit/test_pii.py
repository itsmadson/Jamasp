import pytest

from jamasp.models.entity import PIIClass
from jamasp.safety.pii import classify_column, mask_value


@pytest.mark.parametrize(
    "name,samples,expected",
    [
        ("national_id", ["0079542619"], PIIClass.HIGH),
        ("کدملی", ["0079542619"], PIIClass.HIGH),
        ("salary", [12000000], PIIClass.HIGH),
        ("حقوق", [12000000], PIIClass.HIGH),
        ("mobile", ["09121234567"], PIIClass.LOW),
        ("شماره_موبایل", ["09121234567"], PIIClass.LOW),
        ("email", ["ali@example.com"], PIIClass.LOW),
        ("iban", ["IR062960000000100324200001"], PIIClass.HIGH),
        ("status", [1, 2, 3], PIIClass.NONE),
        ("created_at", ["2026-07-28"], PIIClass.NONE),
    ],
)
def test_classify_column(name, samples, expected):
    assert classify_column(name, "text", samples) is expected


def test_classify_detects_pii_by_value_shape_despite_opaque_name():
    assert classify_column("fld_003", "text", ["09121234567", "09354445566"]) is PIIClass.LOW


def test_high_class_values_are_dropped_entirely():
    assert mask_value("0079542619", PIIClass.HIGH) is None


def test_low_class_mobile_is_partially_masked():
    masked = mask_value("09121234567", PIIClass.LOW)
    assert masked == "0912***4567"


def test_low_class_email_keeps_domain_only():
    assert mask_value("ali@example.com", PIIClass.LOW) == "a***@example.com"


def test_none_class_passes_through():
    assert mask_value(3, PIIClass.NONE) == 3
