using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using XmlProcessorFunction.Services;

var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults()
    .ConfigureServices(services =>
    {
        services.AddApplicationInsightsTelemetryWorkerService();
        services.ConfigureFunctionsApplicationInsights();

        // Register the schema service as a singleton so the XSD is loaded once
        // and reused across all warm invocations – mirrors the Python module-level
        // approach where STORED_SCHEMA is initialised at import time.
        services.AddSingleton<OrderSchemaService>();
    })
    .Build();

await host.RunAsync();
