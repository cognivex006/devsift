package sample
import (
    "fmt"
    "net/http"
)
const Protocol = "https://schema.example.invalid/v1"
var _ = fmt.Sprintf
var _ = http.DefaultClient
func Run(fmt interface{ Println(string) }, http interface{ Get(string) }, failure *int) {
    fmt.Println("intentional fake method")
    http.Get("https://fake.example.invalid")
    if failure != nil {}
    _ = `if err != nil {} fmt.Println("fake")`
    // http.Get("https://comment.example.invalid")
}
