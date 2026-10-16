package config
import "net/http"
func Configure() {
    http.Get("https://configured.example.invalid")
}
