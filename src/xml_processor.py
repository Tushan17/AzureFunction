"""
XML processing helpers for the processXml Azure Function endpoint.

The XSD schema is loaded once at module import time and reused for every
request, which avoids the overhead of re-parsing it on every invocation.
"""

import os
from pathlib import Path
from decimal import Decimal

from lxml import etree


# ---------------------------------------------------------------------------
# Schema – loaded once and stored in module-level state so it is shared
# across all warm invocations of the Function host.
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "order.xsd"

with _SCHEMA_PATH.open("rb") as _f:
    _XML_SCHEMA_DOC = etree.parse(_f)

STORED_SCHEMA: etree.XMLSchema = etree.XMLSchema(_XML_SCHEMA_DOC)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def validate_and_parse_order(xml_bytes: bytes) -> dict:
    """
    Validate *xml_bytes* against the stored Order XSD schema and return a
    plain Python dict representation of the order.

    Raises
    ------
    etree.XMLSyntaxError
        When the payload is not well-formed XML.
    ValueError
        When the XML is well-formed but does not conform to the schema.
    """
    try:
        tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        raise

    if not STORED_SCHEMA.validate(tree):
        errors = "; ".join(str(e) for e in STORED_SCHEMA.error_log)
        raise ValueError(f"XML does not conform to Order schema: {errors}")

    return _parse_order(tree)


def _parse_order(root: etree._Element) -> dict:
    """Convert the validated XML element tree into a Python dict."""

    def text(el: etree._Element, tag: str) -> str:
        child = el.find(tag)
        return child.text.strip() if child is not None and child.text else ""

    items = []
    items_el = root.find("Items")
    decimal_line_totals: list[Decimal] = []
    if items_el is not None:
        for item_el in items_el.findall("Item"):
            qty_text = text(item_el, "Quantity")
            price_text = text(item_el, "UnitPrice")
            quantity = int(qty_text) if qty_text else 0
            unit_price = Decimal(price_text) if price_text else Decimal(0)
            # Use Decimal arithmetic throughout to avoid floating-point drift
            line_total = round(Decimal(quantity) * unit_price, 2)
            decimal_line_totals.append(line_total)
            items.append(
                {
                    "productId": text(item_el, "ProductId"),
                    "productName": text(item_el, "ProductName"),
                    "quantity": quantity,
                    "unitPrice": float(unit_price),
                    "lineTotal": float(line_total),
                }
            )

    total = float(round(sum(decimal_line_totals, Decimal(0)), 2))

    return {
        "orderId": text(root, "OrderId"),
        "customerName": text(root, "CustomerName"),
        "orderDate": text(root, "OrderDate"),
        "items": items,
        "orderTotal": total,
    }
