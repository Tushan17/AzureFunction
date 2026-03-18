using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Xml;
using System.Xml.Linq;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.Extensions.Logging;
using XmlProcessorFunction.Models;
using XmlProcessorFunction.Services;

namespace XmlProcessorFunction;

/// <summary>
/// HTTP-triggered Azure Function that accepts an XML Order document,
/// validates it against the stored XSD schema, and returns a JSON
/// representation that includes computed line totals and the order total.
///
/// C# equivalent of the Python <c>processXml</c> route in function_app.py.
/// </summary>
public sealed class ProcessXmlFunction
{
    private static readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    private readonly ILogger<ProcessXmlFunction> _logger;
    private readonly OrderSchemaService _schemaService;

    public ProcessXmlFunction(
        ILogger<ProcessXmlFunction> logger,
        OrderSchemaService schemaService)
    {
        _logger = logger;
        _schemaService = schemaService;
    }

    /// <summary>
    /// POST /api/processXml
    ///
    /// Request body: XML conforming to schemas/order.xsd
    ///
    /// Example:
    /// <code>
    /// &lt;Order&gt;
    ///   &lt;OrderId&gt;ORD-001&lt;/OrderId&gt;
    ///   &lt;CustomerName&gt;Jane Doe&lt;/CustomerName&gt;
    ///   &lt;OrderDate&gt;2024-03-15&lt;/OrderDate&gt;
    ///   &lt;Items&gt;
    ///     &lt;Item&gt;
    ///       &lt;ProductId&gt;PROD-42&lt;/ProductId&gt;
    ///       &lt;ProductName&gt;Widget&lt;/ProductName&gt;
    ///       &lt;Quantity&gt;3&lt;/Quantity&gt;
    ///       &lt;UnitPrice&gt;9.99&lt;/UnitPrice&gt;
    ///     &lt;/Item&gt;
    ///   &lt;/Items&gt;
    /// &lt;/Order&gt;
    /// </code>
    /// </summary>
    [Function("ProcessXml")]
    public async Task<HttpResponseData> Run(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "processXml")]
        HttpRequestData req)
    {
        _logger.LogInformation("ProcessXml function received a request.");

        string body = await new StreamReader(req.Body).ReadToEndAsync();

        if (string.IsNullOrWhiteSpace(body))
        {
            return await ErrorResponse(
                req,
                HttpStatusCode.BadRequest,
                "Request body must be a non-empty XML document.");
        }

        // --- Schema validation (against the stored XSD) --------------------
        string? validationError = _schemaService.Validate(body);
        if (validationError is not null)
        {
            return await ErrorResponse(
                req,
                HttpStatusCode.UnprocessableEntity,
                $"XML does not conform to Order schema: {validationError}");
        }

        // --- Parsing --------------------------------------------------------
        OrderResponse order;
        try
        {
            order = ParseOrder(body);
        }
        catch (XmlException ex)
        {
            return await ErrorResponse(
                req,
                HttpStatusCode.BadRequest,
                $"Malformed XML: {ex.Message}");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Unexpected error while processing XML.");
            return await ErrorResponse(
                req,
                HttpStatusCode.InternalServerError,
                "XML processing failed.");
        }

        var response = req.CreateResponse(HttpStatusCode.OK);
        response.Headers.Add("Content-Type", "application/json; charset=utf-8");
        await response.WriteStringAsync(JsonSerializer.Serialize(order, _jsonOptions));
        return response;
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private static OrderResponse ParseOrder(string xml)
    {
        var doc = XDocument.Parse(xml);
        var root = doc.Root!;

        string orderId       = (string?)root.Element("OrderId")      ?? string.Empty;
        string customerName  = (string?)root.Element("CustomerName") ?? string.Empty;
        string orderDate     = (string?)root.Element("OrderDate")    ?? string.Empty;

        var items = root
            .Element("Items")!   // "Items" is required by the XSD schema.
            .Elements("Item")
            .Select(item =>
            {
                int     qty       = (int)item.Element("Quantity")!;
                decimal unitPrice = (decimal)item.Element("UnitPrice")!;
                decimal lineTotal = Math.Round(qty * unitPrice, 2);

                return new OrderItem(
                    ProductId:   (string?)item.Element("ProductId")   ?? string.Empty,
                    ProductName: (string?)item.Element("ProductName") ?? string.Empty,
                    Quantity:    qty,
                    UnitPrice:   unitPrice,
                    LineTotal:   lineTotal);
            })
            .ToList();

        decimal orderTotal = Math.Round(items.Sum(i => i.LineTotal), 2);

        return new OrderResponse(orderId, customerName, orderDate, items, orderTotal);
    }

    private static async Task<HttpResponseData> ErrorResponse(
        HttpRequestData req,
        HttpStatusCode statusCode,
        string message)
    {
        var response = req.CreateResponse(statusCode);
        response.Headers.Add("Content-Type", "application/json; charset=utf-8");
        await response.WriteStringAsync(
            JsonSerializer.Serialize(new { error = message }, _jsonOptions));
        return response;
    }
}
