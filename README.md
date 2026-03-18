# C# vs Python – Azure Function for XML Processing

This repository contains two equivalent Azure Function implementations of an
HTTP API that **receives an XML document, validates it against a stored XSD
schema, and returns a JSON representation** with computed totals.

| | Python | C# |
|---|---|---|
| **Runtime** | Azure Functions v4 · Python 3.12 | Azure Functions v4 · .NET 8 (isolated worker) |
| **Entry point** | `function_app.py` | `csharp/Program.cs` |
| **Route handler** | `processXmlFunc` in `function_app.py` | `ProcessXmlFunction.cs` |
| **XML library** | `lxml` (XSD validation + parsing) | `System.Xml` + `System.Xml.Linq` |
| **Schema storage** | `schemas/order.xsd` (loaded once at module import) | `csharp/schemas/order.xsd` (copied to output dir; loaded once in singleton service) |
| **Dependency injection** | Module-level singleton (`STORED_SCHEMA`) | `IServiceCollection` singleton (`OrderSchemaService`) |

---

## Stored XSD Schema

Both implementations share the same logical schema, located in `schemas/order.xsd`.
The schema describes an `<Order>` document with the following structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Order>
  <OrderId>ORD-001</OrderId>
  <CustomerName>Jane Doe</CustomerName>
  <OrderDate>2024-03-15</OrderDate>
  <Items>
    <Item>
      <ProductId>PROD-42</ProductId>
      <ProductName>Widget</ProductName>
      <Quantity>3</Quantity>
      <UnitPrice>9.99</UnitPrice>
    </Item>
  </Items>
</Order>
```

---

## API

### `POST /api/processXml`

**Request**

| Header | Value |
|--------|-------|
| `Content-Type` | `application/xml` (or `text/xml`) |

Body: an XML document conforming to `schemas/order.xsd`.

**Success response – `200 OK`**

```json
{
  "orderId": "ORD-001",
  "customerName": "Jane Doe",
  "orderDate": "2024-03-15",
  "items": [
    {
      "productId": "PROD-42",
      "productName": "Widget",
      "quantity": 3,
      "unitPrice": 9.99,
      "lineTotal": 29.97
    }
  ],
  "orderTotal": 29.97
}
```

**Error responses**

| Status | Meaning |
|--------|---------|
| `400 Bad Request` | Empty body or malformed XML |
| `422 Unprocessable Entity` | Well-formed XML that does not conform to the schema |
| `500 Internal Server Error` | Unexpected processing failure |

---

## Language Comparison

### Schema loading

The XSD schema file is loaded **once** and reused for every request, avoiding
repeated I/O on each invocation.

**Python** – module-level initialisation (runs once when the module is first
imported by the Functions host):

```python
# src/xml_processor.py
_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "order.xsd"

with _SCHEMA_PATH.open("rb") as _f:
    _XML_SCHEMA_DOC = etree.parse(_f)

STORED_SCHEMA: etree.XMLSchema = etree.XMLSchema(_XML_SCHEMA_DOC)
```

**C#** – singleton service registered in the DI container (runs once when the
host process starts):

```csharp
// Services/OrderSchemaService.cs
public sealed class OrderSchemaService
{
    private readonly XmlSchemaSet _schemaSet;

    public OrderSchemaService()
    {
        _schemaSet = new XmlSchemaSet();
        string schemaPath = Path.Combine(
            AppContext.BaseDirectory, "schemas", "order.xsd");
        _schemaSet.Add(null, schemaPath);
        _schemaSet.Compile();
    }
    // ...
}

// Program.cs
services.AddSingleton<OrderSchemaService>();
```

### Schema validation

**Python** (`lxml`):

```python
if not STORED_SCHEMA.validate(tree):
    errors = "; ".join(str(e) for e in STORED_SCHEMA.error_log)
    raise ValueError(f"XML does not conform to Order schema: {errors}")
```

**C#** (`System.Xml`):

```csharp
var settings = new XmlReaderSettings
{
    ValidationType = ValidationType.Schema,
    Schemas        = _schemaSet,
};
settings.ValidationEventHandler += (_, e) =>
{
    if (validationError is null)
        validationError = e.Message;
};
```

### XML parsing

**Python** (XPath via `lxml`):

```python
def _parse_order(root: etree._Element) -> dict:
    items_el = root.find("Items")
    for item_el in items_el.findall("Item"):
        qty   = int(text(item_el, "Quantity"))
        price = float(Decimal(text(item_el, "UnitPrice")))
        ...
```

**C#** (LINQ to XML):

```csharp
var items = root
    .Element("Items")!
    .Elements("Item")
    .Select(item =>
    {
        int     qty       = (int)item.Element("Quantity")!;
        decimal unitPrice = (decimal)item.Element("UnitPrice")!;
        decimal lineTotal = Math.Round(qty * unitPrice, 2);
        return new OrderItem(...);
    })
    .ToList();
```

### Key differences

| Concern | Python | C# |
|---------|--------|----|
| XML library | `lxml` (third-party, must be in `requirements.txt`) | `System.Xml` / `System.Xml.Linq` (built into .NET BCL) |
| XSD validation API | `etree.XMLSchema.validate()` | `XmlReaderSettings.ValidationType = Schema` |
| LINQ / comprehensions | List comprehensions | LINQ (`Select`, `Where`, `Sum`) |
| Type safety | Duck-typed at runtime | Statically typed; `record` types for models |
| Cold-start overhead | Lower (interpreter starts faster) | Higher (.NET runtime + JIT) |
| Warm-request throughput | Moderate | Higher (AOT / JIT compiled code) |
| Deployment size | Smaller | Larger (includes .NET runtime) |

---

## Running Locally

### Python

```bash
# Install dependencies
pip install -r requirements.txt

# Start the Functions host
func start
```

Call the endpoint:

```bash
curl -X POST http://localhost:7071/api/processXml \
  -H "Content-Type: application/xml" \
  --data-binary @- <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<Order>
  <OrderId>ORD-001</OrderId>
  <CustomerName>Jane Doe</CustomerName>
  <OrderDate>2024-03-15</OrderDate>
  <Items>
    <Item>
      <ProductId>PROD-42</ProductId>
      <ProductName>Widget</ProductName>
      <Quantity>3</Quantity>
      <UnitPrice>9.99</UnitPrice>
    </Item>
  </Items>
</Order>
EOF
```

### C#

```bash
cd csharp

# Restore packages
dotnet restore

# Start the Functions host
func start --csharp
```

Call the endpoint using the same `curl` command above (the port and route are
identical).

---

## Docker (Python)

The Python implementation includes a `Dockerfile`. Build and run with:

```bash
docker build -t xml-processor-python .
docker run -p 7071:80 xml-processor-python
```
