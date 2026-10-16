using System.Net.Http;
class ClientConfiguration {
    void Configure() {
        new HttpClient().GetAsync("https://configured.example.invalid");
    }
}
