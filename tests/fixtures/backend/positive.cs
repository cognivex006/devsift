using System;
using System.Net.Http;
class Service {
    async System.Threading.Tasks.Task Run(Exception failure) {
        using var client = new HttpClient();
        await client.GetAsync("https://api.example.invalid/items");
        try { throw failure; } catch (Exception) { }
        Console.WriteLine("debug");
    }
}
