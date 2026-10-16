namespace System {
    class Console { public static void WriteLine(string value) {} }
}
namespace System.Net.Http {
    class HttpClient { public void GetAsync(string value) {} }
}
class Protocol {
    const string Scheme = "https://schema.example.invalid/v1";
    void Run() {
        System.Console.WriteLine("intentional fake method");
        new System.Net.Http.HttpClient().GetAsync("https://fake.example.invalid");
        var example = "catch (Exception) {} Console.WriteLine(fake)";
        // client.GetAsync("https://comment.example.invalid")
    }
}
