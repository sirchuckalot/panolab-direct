package main

import (
 "reflect"
 "testing"
)

func TestRootlessISEArchiveExtractionNeverRestoresVendorOwnership(t *testing.T){
 got:=rootlessExtractionArgs()
 want:=[]string{"--no-same-owner","--no-same-permissions","-xf","/media/ise.tar","-C","/work/ise-media"}
 if !reflect.DeepEqual(got,want){
  t.Fatalf("unsafe ISE vendor extraction options: got %q, want %q",got,want)
 }
}
