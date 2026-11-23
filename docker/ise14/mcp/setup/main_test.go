package main
import "testing"
func TestInstalledDefault(t *testing.T){if !regular("/nonexistent/panolab-setup-test"){t.Log("missing files correctly report false")}else{t.Fatal("unexpected file")}}
