import azure.functions as func
import logging
import json

from lxml import etree

from src.route import optimize_route
from src.xml_processor import validate_and_parse_order

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="firstFunc")
def firstFunc(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )

@app.route(route="secondFunc")
def secondFunc(req: func.HttpRequest) -> func.HttpResponse:
    name = req.get_json().get('name') if req.get_json(silent=True) else None
    if name:
        return func.HttpResponse(
            body=f"Hello, {name}. This is the second function. It executed successfully.", 
            status_code=200, 
            mimetype="text/plain", 
            charset="utf-8", 
            headers={"Custom-Header": "CustomValue"})

    return func.HttpResponse(
        body="This is the second function. It executed successfully.", 
        status_code=200, 
        mimetype="text/plain", 
        charset="utf-8", 
        headers={"Custom-Header": "CustomValue"})


@app.route(route="optimizeRoute", methods=["POST"])
def optimizeRouteFunc(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Maps route optimisation endpoint.

    Expected JSON body:
    {
        "start": {"lat": 52.36006, "lon": 4.85106},
        "legs":  [
            {"id": 1, "lat": 52.36187, "lon": 4.90736},
            {"id": 2, "lat": 52.38105, "lon": 4.89391}
        ],
        "end":   {"lat": 52.37628, "lon": 4.90765}
    }

    Returns JSON:
    {
        "optimizedLegs": [
            {"id": 2, "lat": 52.38105, "lon": 4.89391, "originalIndex": 1},
            {"id": 1, "lat": 52.36187, "lon": 4.90736, "originalIndex": 0}
        ],
        "totalDistanceMeters": 12540,
        "totalTravelTimeSeconds": 620
    }
    """
    logging.info('optimizeRoute function received a request.')

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Request body must be valid JSON."}),
            status_code=400,
            mimetype="application/json",
        )

    start = body.get("start")
    legs  = body.get("legs")
    end   = body.get("end")

    if start is None or legs is None or end is None:
        return func.HttpResponse(
            body=json.dumps({"error": "'start', 'legs', and 'end' are required fields."}),
            status_code=400,
            mimetype="application/json",
        )

    if not isinstance(legs, list):
        return func.HttpResponse(
            body=json.dumps({"error": "'legs' must be an array."}),
            status_code=400,
            mimetype="application/json",
        )

    for field, value in [("start", start), ("end", end)]:
        if not isinstance(value, dict) or "lat" not in value or "lon" not in value:
            return func.HttpResponse(
                body=json.dumps({"error": f"'{field}' must be an object with 'lat' and 'lon'."}),
                status_code=400,
                mimetype="application/json",
            )

    for i, leg in enumerate(legs):
        if not isinstance(leg, dict) or "lat" not in leg or "lon" not in leg:
            return func.HttpResponse(
                body=json.dumps({"error": f"legs[{i}] must be an object with 'lat' and 'lon'."}),
                status_code=400,
                mimetype="application/json",
            )
        if "id" not in leg:
            return func.HttpResponse(
                body=json.dumps({"error": f"legs[{i}] is missing required field 'id'."}),
                status_code=400,
                mimetype="application/json",
            )
        if not isinstance(leg["id"], int):
            return func.HttpResponse(
                body=json.dumps({"error": f"legs[{i}].id must be an integer."}),
                status_code=400,
                mimetype="application/json",
            )

    try:
        result = optimize_route(start, legs, end)
    except ValueError as exc:
        return func.HttpResponse(
            body=json.dumps({"error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("Azure Maps call failed.")
        return func.HttpResponse(
            body=json.dumps({"error": "Route optimisation failed.", "detail": str(exc)}),
            status_code=502,
            mimetype="application/json",
        )

    return func.HttpResponse(
        body=json.dumps(result),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="processXml", methods=["POST"])
def processXmlFunc(req: func.HttpRequest) -> func.HttpResponse:
    """
    Validate and process an XML Order document against the stored XSD schema.

    Expected request body: an XML document conforming to schemas/order.xsd.

    Example request body:
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

    Returns JSON with the parsed order including computed line totals and
    the overall order total.
    """
    logging.info("processXml function received a request.")

    xml_bytes = req.get_body()
    if not xml_bytes:
        return func.HttpResponse(
            body=json.dumps({"error": "Request body must be a non-empty XML document."}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        order = validate_and_parse_order(xml_bytes)
    except etree.XMLSyntaxError as exc:
        return func.HttpResponse(
            body=json.dumps({"error": str(exc)}),
            status_code=400,
            mimetype="application/json",
        )
    except ValueError as exc:
        return func.HttpResponse(
            body=json.dumps({"error": str(exc)}),
            status_code=422,
            mimetype="application/json",
        )
    except Exception as exc:
        logging.exception("Unexpected error while processing XML.")
        return func.HttpResponse(
            body=json.dumps({"error": "XML processing failed.", "detail": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        body=json.dumps(order),
        status_code=200,
        mimetype="application/json",
    )