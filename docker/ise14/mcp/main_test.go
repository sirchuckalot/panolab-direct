package main

import (
 "context"
 "errors"
 "encoding/base64"
 "bytes"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func TestBuildRejectsUnapprovedProfile(t *testing.T) {
 _,_,err:=start(context.Background(),nil,StartInput{Profile:"shell",Project:"counter"})
 if err==nil || !strings.Contains(err.Error(),"unsupported build profile"){t.Fatalf("unexpected error: %v",err)}
}
func TestProjectNamesStayInsideApprovedRoot(t *testing.T) {
 for _,id:=range []string{"","../etc","/tmp/demo","counter;rm -rf /","bad name"}{
  if _,_,err:=loadProject(id);err==nil{t.Errorf("accepted unsafe project name %q",id)}
 }
}
func TestPrepareBuildFilesNoVendorExecution(t *testing.T) {
 dir:=t.TempDir();base:=filepath.Join(dir,"project");out:=filepath.Join(dir,"out")
 if err:=os.Mkdir(base,0700);err!=nil{t.Fatal(err)}
 if err:=os.Mkdir(out,0700);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(filepath.Join(base,"counter.v"),[]byte("module counter_top(); endmodule\n"),0600);err!=nil{t.Fatal(err)}
 p:=projectSpec{Top:"counter_top",Part:"xc6slx150-fgg484-2",Verilog:[]string{"counter.v"}}
 if err:=prepare(out,base,p);err!=nil{t.Fatal(err)}
 raw,err:=os.ReadFile(filepath.Join(out,"design.xst"));if err!=nil{t.Fatal(err)}
 if !strings.Contains(string(raw),"-p xc6slx150-fgg484-2")||!strings.Contains(string(raw),"-top counter_top"){t.Fatal("incorrect build inputs")}
}
func TestRejectUnknownJobIDs(t *testing.T){
 for _,id:=range []string{"","../../etc","12;rm -rf /","123abc","999999999999999999"}{
  if _,err:=lookup(id);err==nil{t.Errorf("accepted ID %q",id)}
 }
}

func TestPersistedResultsSurviveWorkerRestartAndStreamChunks(t *testing.T){
 oldRoot:=root
 root=filepath.Join(t.TempDir(),"jobs")
 defer func(){root=oldRoot}()
 jobs.Lock();oldItems:=jobs.items;jobs.items=map[string]*job{};jobs.Unlock()
 defer func(){jobs.Lock();jobs.items=oldItems;jobs.Unlock()}()
 j:=&job{id:"123456",state:"succeeded",exit:0,project:"counter",profile:"ise14-implementation"}
 if err:=persistJob(j);err!=nil{t.Fatal(err)}
 payload:=bytes.Repeat([]byte("bitstream-data-"),10000)
 artifact:=filepath.Join(root,j.id,"design.bit")
 if err:=os.WriteFile(artifact,payload,0600);err!=nil{t.Fatal(err)}
 restored,err:=lookup(j.id)
 if err!=nil||restored.state!="succeeded"{t.Fatalf("restart restore failed: %v, %+v",err,restored)}
 var rebuilt []byte
 offset:=int64(0)
 for i:=0;i<10;i++{
  _,res,err:=result(context.Background(),nil,JobInput{ID:j.id,Artifact:"design.bit",Offset:offset})
  if err!=nil{t.Fatal(err)}
  decoded,err:=base64.StdEncoding.DecodeString(res.ChunkBase64);if err!=nil{t.Fatal(err)}
  rebuilt=append(rebuilt,decoded...)
  offset=res.NextOffset
  if res.ChunkEOF{break}
 }
 if !bytes.Equal(rebuilt,payload){t.Fatal("artifact bytes lost during chunk transfer")}
 if _,_,err=result(context.Background(),nil,JobInput{ID:j.id,Artifact:"../../etc/passwd"});err==nil{
  t.Fatal("accepted unsafe artifact filename")
 }
 if _,_,err=result(context.Background(),nil,JobInput{ID:j.id,Artifact:"design.bit",Offset:-1});err==nil{
  t.Fatal("accepted negative offset")
 }
}
func TestRestartMarksIncompleteJobInterrupted(t *testing.T){
 oldRoot:=root;root=filepath.Join(t.TempDir(),"jobs");defer func(){root=oldRoot}()
 jobs.Lock();oldItems:=jobs.items;jobs.items=map[string]*job{};jobs.Unlock()
 defer func(){jobs.Lock();jobs.items=oldItems;jobs.Unlock()}()
 j:=&job{id:"987654",state:"running",exit:-1,project:"counter",profile:"ise14-implementation"}
 if err:=persistJob(j);err!=nil{t.Fatal(err)}
 restored,err:=lookup(j.id)
 if err!=nil||restored.state!="interrupted"||restored.exit!=125{t.Fatalf("unexpected recovery: %v %+v",err,restored)}
}
func TestRejectSymlinkProjectInputs(t *testing.T){
 oldProjects:=projectsRoot;projectsRoot=t.TempDir();defer func(){projectsRoot=oldProjects}()
 base:=filepath.Join(projectsRoot,"counter")
 if err:=os.Mkdir(base,0700);err!=nil{t.Fatal(err)}
 if err:=os.WriteFile(filepath.Join(base,"build.json"),[]byte(`{"top":"counter_top","part":"xc6slx150-fgg484-2","verilog":["counter.v"]}`),0600);err!=nil{t.Fatal(err)}
 external:=filepath.Join(t.TempDir(),"hidden.v")
 if err:=os.WriteFile(external,[]byte("module hidden(); endmodule"),0600);err!=nil{t.Fatal(err)}
 if err:=os.Symlink(external,filepath.Join(base,"counter.v"));err!=nil{t.Fatal(err)}
 if _,_,err:=loadProject("counter");err==nil{t.Fatal("accepted symlink into external source tree")}
}

func TestSimulatedSixStageISEPipelineAndUCF(t *testing.T){
 dir:=t.TempDir()
 p:=projectSpec{Part:"xc6slx150-fgg484-2",Top:"counter_top",UCF:"board.ucf"}
 var called []string
 var ngd []string
 fake:=func(ctx context.Context,location,stage string,args ...string)error{
  called=append(called,stage)
  if stage=="ngdbuild"{ngd=append([]string{},args...)}
  if stage=="bitgen"{
   return os.WriteFile(filepath.Join(location,"design.bit"),[]byte("FAKE CONTENT; NOT A VENDOR BITSTREAM"),0600)
  }
  return nil
 }
 if err:=runBuildWith(context.Background(),dir,p,fake);err!=nil{t.Fatal(err)}
 expected:=[]string{"xst","ngdbuild","map","par","trce","bitgen"}
 if !strings.EqualFold(strings.Join(called,","),strings.Join(expected,",")){t.Fatalf("wrong stage order: %v",called)}
 if !strings.Contains(strings.Join(ngd," " ),"-uc design.ucf"){t.Fatalf("UCF ignored by NGDBuild: %v",ngd)}
}
func TestSimulatedISEPipelineStopsOnFailure(t *testing.T){
 dir:=t.TempDir()
 var called []string
 fake:=func(ctx context.Context,location,stage string,args ...string)error{
  called=append(called,stage)
  if stage=="map"{return errors.New("synthetic MAP failure")}
  return nil
 }
 err:=runBuildWith(context.Background(),dir,projectSpec{Part:"xc6slx150-fgg484-2"},fake)
 if err==nil||!strings.Contains(err.Error(),"map"){t.Fatalf("missing MAP failure: %v",err)}
 if strings.Join(called,",")!="xst,ngdbuild,map"{t.Fatalf("later stages executed after failure: %v",called)}
 if _,err:=os.Stat(filepath.Join(dir,"design.bit"));!os.IsNotExist(err){t.Fatal("fake bitstream unexpectedly present")}
}

func TestVendorExecutableUsesPinnedAbsoluteISEBinaryOnly(t *testing.T){
 for _,name:=range []string{"xst","ngdbuild","map","par","trce","bitgen"}{
  got,err:=vendorExecutable(name)
  expected:=filepath.Join("/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64",name)
  if err!=nil||got!=expected{t.Fatalf("stage %q: got %q, err=%v",name,got,err)}
 }
 for _,name:=range []string{"../xst","/bin/sh","bash","xst -h",""}{
  if _,err:=vendorExecutable(name);err==nil{t.Errorf("accepted unsafe vendor executable %q",name)}
 }
}
