package service
import (
    "fmt"
    "net/http"
)
func Run(failure error) {
    http.Get("https://api.example.invalid/items")
    if failure != nil {}
    fmt.Println("debug")
}
