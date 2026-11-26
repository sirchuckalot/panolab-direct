package main

import (
 "context"
 "errors"
 "encoding/base64"
 "encoding/json"
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

func TestTimingReportPagesFitBrokerAndRestoreExactBytes(t *testing.T) {
 oldRoot := root
 root = t.TempDir()
 t.Cleanup(func() { root = oldRoot })
 j := &job{id: "1795652101955866441", state: "succeeded", project: "counter", profile: "ise14-implementation"}
 if err := persistJob(j); err != nil { t.Fatal(err) }
 t.Cleanup(func() {
  jobs.Lock()
  delete(jobs.items, j.id)
  jobs.Unlock()
 })
 payload := bytes.Repeat([]byte("R"), 71042)
 if err := os.WriteFile(filepath.Join(root, j.id, "design.twr"), payload, 0600); err != nil { t.Fatal(err) }
 var rebuilt []byte
 for offset := int64(0); offset < int64(len(payload)); {
  _, page, err := result(context.Background(), nil, JobInput{ID: j.id, Artifact: "design.twr", Offset: offset})
  if err != nil { t.Fatal(err) }
  raw, err := json.Marshal(page)
  if err != nil || len(raw) >= 24000 { t.Fatalf("unsafe page size: %d (%v)", len(raw), err) }
  fragment, err := base64.StdEncoding.DecodeString(page.ChunkBase64)
  want := min(8192, len(payload)-int(offset))
  if err != nil || len(fragment) != want || page.ChunkOffset != offset ||
   page.NextOffset != offset+int64(want) || page.ChunkEOF != (page.NextOffset == int64(len(payload))) {
   t.Fatalf("invalid page at offset %d: %v", offset, err)
  }
  rebuilt = append(rebuilt, fragment...)
  offset = page.NextOffset
 }
 if !bytes.Equal(rebuilt, payload) { t.Fatal("timing report changed in transfer") }
}

func TestLicenseProofRequiresCurrentSuccessfulPersistedBuild(t *testing.T) {
 oldRoot := root
 root = t.TempDir()
 t.Cleanup(func() { root = oldRoot })
 reset := func() {
  jobs.Lock()
  defer jobs.Unlock()
  jobs.license = licenseIdentity{}
  jobs.licenseGeneration = 0
  jobs.licenseJob = ""
 }
 reset()
 t.Cleanup(reset)
 path := filepath.Join(t.TempDir(), "test-license")
 t.Setenv("XILINXD_LICENSE_FILE", path)
 writeLicense := func(content string) {
  t.Helper()
  if err := os.WriteFile(path, []byte(content), 0600); err != nil { t.Fatal(err) }
 }
 expect := func(status, id string) {
  t.Helper()
  _, got, err := toolchain(context.Background(), nil, Empty{})
  if err != nil || got.ToolchainVersion != "ISE 14.7" ||
   got.License != (status != "unavailable") || got.LicenseValidated != (id != "") ||
   got.LicenseValidationStatus != status || got.LicenseValidationJob != id {
   t.Fatalf("license status = %+v, %v", got, err)
  }
 }
 generation := func() uint64 {
  jobs.Lock()
  defer jobs.Unlock()
  if !observeLicenseLocked() { t.Fatal("test license unavailable") }
  return jobs.licenseGeneration
 }
 complete := func(ctx context.Context, id string, rc int, gen uint64) {
  t.Helper()
  finishJob(ctx, &job{id: id, state: "running"}, rc, true, gen)
 }
 ctx := context.Background()
 expect("unavailable", "")
 writeLicense("synthetic fixture A")
 expect("not_yet_validated", "")
 initial := generation()
 complete(ctx, "1000000001", 1, initial)
 expect("not_yet_validated", "")
 cancelled, cancelJob := context.WithCancel(ctx)
 cancelJob()
 complete(cancelled, "1000000002", 0, initial)
 expect("not_yet_validated", "")
 if err := os.WriteFile(filepath.Join(root, "1000000003"), nil, 0600); err != nil { t.Fatal(err) }
 complete(ctx, "1000000003", 0, initial)
 expect("not_yet_validated", "")
 writeLicense("synthetic fixture B")
 complete(ctx, "1000000004", 0, initial)
 expect("not_yet_validated", "")
 current := generation()
 complete(ctx, "1000000005", 0, current)
 expect("validated", "1000000005")
 complete(ctx, "1000000006", 1, current)
 expect("validated", "1000000005")
 reset()
 if j, err := lookup("1000000005"); err != nil || j.state != "succeeded" {
  t.Fatalf("successful job was not persisted: %v", err)
 }
 t.Cleanup(func() {
  jobs.Lock()
  delete(jobs.items, "1000000005")
  jobs.Unlock()
 })
 expect("not_yet_validated", "")
 complete(ctx, "1000000007", 0, generation())
 expect("validated", "1000000007")
 if err := os.Remove(path); err != nil { t.Fatal(err) }
 expect("unavailable", "")
 writeLicense("synthetic fixture B")
 expect("not_yet_validated", "")
}
