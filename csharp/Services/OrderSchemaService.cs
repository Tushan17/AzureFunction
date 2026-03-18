using System.Xml;
using System.Xml.Schema;

namespace XmlProcessorFunction.Services;

/// <summary>
/// Loads and stores the Order XSD schema once at startup.
/// Registered as a singleton in the DI container so the schema file
/// is read only once for the lifetime of the Function host process –
/// equivalent to the module-level <c>STORED_SCHEMA</c> in the Python version.
/// </summary>
public sealed class OrderSchemaService
{
    private readonly XmlSchemaSet _schemaSet;

    public OrderSchemaService()
    {
        _schemaSet = new XmlSchemaSet();

        // The schema file is copied to the output directory by the .csproj
        // <None Update> item, so it is always alongside the assembly.
        string schemaPath = Path.Combine(
            AppContext.BaseDirectory, "schemas", "order.xsd");

        _schemaSet.Add(null, schemaPath);
        _schemaSet.Compile();
    }

    /// <summary>
    /// Validate <paramref name="xml"/> against the stored Order schema.
    /// Returns <c>null</c> on success, or the first validation error message.
    /// </summary>
    public string? Validate(string xml)
    {
        string? validationError = null;

        var settings = new XmlReaderSettings
        {
            ValidationType = ValidationType.Schema,
            Schemas = _schemaSet,
        };

        settings.ValidationEventHandler += (_, e) =>
        {
            if (validationError is null)
                validationError = e.Message;
        };

        using var reader = XmlReader.Create(new StringReader(xml), settings);
        try
        {
            while (reader.Read()) { }
        }
        catch (XmlException ex)
        {
            return ex.Message;
        }

        return validationError;
    }
}
