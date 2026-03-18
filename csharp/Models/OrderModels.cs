namespace XmlProcessorFunction.Models;

public sealed record OrderItem(
    string ProductId,
    string ProductName,
    int Quantity,
    decimal UnitPrice,
    decimal LineTotal);

public sealed record OrderResponse(
    string OrderId,
    string CustomerName,
    string OrderDate,
    IReadOnlyList<OrderItem> Items,
    decimal OrderTotal);
