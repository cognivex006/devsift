package service
import (
    "fmt"
    "net/http"
)
func Run(failure error) {
    http.Get("https://go.example.invalid/items")
    if failure != nil {}
    fmt.Println("backend-debug")
}
