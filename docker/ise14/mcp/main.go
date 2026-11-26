// PanoLab ISE 14.7 MCP build worker: generic, project-driven compilation.
// Test designs, smoke procedures, and test pass/fail decisions belong to the MCP client.
package main

import (
 "context"
 "crypto/sha256"
 "crypto/subtle"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "log"
 "net/http"
 "os"
 "os/exec"
 "path/filepath"
 "regexp"
 "strings"
 "sync"
 "time"

 "github.com/modelcontextprotocol/go-sdk/mcp"
)

type Empty struct{}
type Info struct {
 Name string `json:"name"`
 InterfaceVersion string `json:"interface_version"`
 InstanceID string `json:"instance_id"`
 Vendor string `json:"vendor"`
 ToolchainVersion string `json:"toolchain_version"`
 Profiles []string `json:"profiles"`
 ISE bool `json:"ise_available"`
 License bool `json:"license_available"`
 LicenseValidated bool `json:"license_validated"`
 LicenseValidationStatus string `json:"license_validation_status"`
 LicenseValidationJob string `json:"license_validation_job_id,omitempty"`
 Programming bool `json:"programming_supported"`
}
type StartInput struct { Profile string `json:"profile"`; Project string `json:"project"` }
type StartOutput struct { ID string `json:"job_id"`; State string `json:"state"` }
type JobInput struct { ID string `json:"job_id"`; Artifact string `json:"artifact,omitempty"`; Offset int64 `json:"offset,omitempty"` }
type Status struct { ID string `json:"job_id"`; State string `json:"state"`; ExitCode int `json:"exit_code"` }
type Artifact struct { Name string `json:"name"`; SHA256 string `json:"sha256"`; Bytes int64 `json:"bytes"`; MediaType string `json:"media_type"` }
type BuildResult struct { ID string `json:"job_id"`; State string `json:"state"`; ExitCode int `json:"exit_code"`; Project string `json:"project"`; Profile string `json:"profile"`; Logs string `json:"log_tail"`; LogsTruncated bool `json:"logs_truncated"`; Artifacts []Artifact `json:"artifacts"`; ChunkBase64 string `json:"chunk_base64,omitempty"`; ChunkOffset int64 `json:"chunk_offset,omitempty"`; NextOffset int64 `json:"next_offset,omitempty"`; ChunkEOF bool `json:"chunk_eof,omitempty"` }
type projectSpec struct { Top string `json:"top"`; Part string `json:"part"`; Verilog []string `json:"verilog"`; UCF string `json:"ucf"` }
type job struct { id, state, project, profile string; exit int; cancel context.CancelFunc }
type jobRecord struct { ID string `json:"job_id"`; State string `json:"state"`; Exit int `json:"exit_code"`; Project string `json:"project"`; Profile string `json:"profile"` }
var jobs = struct {sync.Mutex; items map[string]*job; license licenseIdentity; licenseGeneration uint64; licenseJob string}{items:map[string]*job{}}
var root="/results/jobs"
var projectsRoot="/projects"
var safeName=regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,63}$`)
var safeFile=regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`)
var allowedParts=map[string]bool{"xc6slx150-fgg484-2":true}

var artifactNames=map[string]bool{"xst.log":true,"ngdbuild.log":true,"map.log":true,"par.log":true,"trce.log":true,"bitgen.log":true,"design.bit":true,"design.twr":true}
func persistJob(j *job)error{
 rec:=jobRecord{ID:j.id,State:j.state,Exit:j.exit,Project:j.project,Profile:j.profile}
 b,err:=json.Marshal(rec);if err!=nil{return err}
 dir:=filepath.Join(root,j.id)
 if err=os.MkdirAll(dir,0700);err!=nil{return err}
 tmp:=filepath.Join(dir,"job.json.tmp")
 if err=os.WriteFile(tmp,b,0600);err!=nil{return err}
 return os.Rename(tmp,filepath.Join(dir,"job.json"))
}
func readProjectFile(base,name string)([]byte,error){
 file:=filepath.Join(base,name)
 info,err:=os.Lstat(file);if err!=nil{return nil,err}
 if !info.Mode().IsRegular(){return nil,errors.New("project file must be regular and not a symlink")}
 if info.Size()>8*1024*1024{return nil,errors.New("project file exceeds 8 MiB limit")}
 return os.ReadFile(file)
}

// License identity and proof are private and process-local. All observations
// and proof updates are serialized with the job state.
type licenseIdentity struct {
 info os.FileInfo
 digest [sha256.Size]byte
}

func readLicenseIdentity(path string) licenseIdentity {
 const maxBytes = 1024 * 1024
 before, err := os.Lstat(path)
 if err != nil || !before.Mode().IsRegular() || before.Size() > maxBytes {
  return licenseIdentity{}
 }
 f, err := os.Open(path)
 if err != nil {
  return licenseIdentity{}
 }
 defer f.Close()
 opened, err := f.Stat()
 if err != nil || !sameLicenseFile(before, opened) {
  return licenseIdentity{}
 }
 hash := sha256.New()
 size, err := io.Copy(hash, io.LimitReader(f, maxBytes+1))
 after, statErr := os.Lstat(path)
 if err != nil || statErr != nil || size != before.Size() || !sameLicenseFile(before, after) {
  return licenseIdentity{}
 }
 var digest [sha256.Size]byte
 copy(digest[:], hash.Sum(nil))
 return licenseIdentity{info: before, digest: digest}
}

func sameLicenseFile(a, b os.FileInfo) bool {
 return b.Mode().IsRegular() && os.SameFile(a, b) &&
  a.Size() == b.Size() && a.Mode() == b.Mode() && a.ModTime().Equal(b.ModTime())
}

func observeLicenseLocked() bool {
 current := readLicenseIdentity(os.Getenv("XILINXD_LICENSE_FILE"))
 previous := jobs.license
 if (current.info == nil) != (previous.info == nil) ||
  (current.info != nil && previous.info != nil &&
   (!sameLicenseFile(previous.info, current.info) || previous.digest != current.digest)) {
  jobs.licenseGeneration++
  jobs.licenseJob = ""
 }
 jobs.license = current
 return current.info != nil
}

func toolchain(ctx context.Context,r *mcp.CallToolRequest,in Empty)(*mcp.CallToolResult,Info,error){
 _,ise:=os.Stat("/opt/Xilinx/14.7/ISE_DS/settings64.sh")
 instanceID,_:=os.Hostname()
 jobs.Lock()
 available := observeLicenseLocked()
 proof := jobs.licenseJob
 jobs.Unlock()
 validation := "not_yet_validated"
 if !available {
  validation = "unavailable"
 } else if proof != "" {
  validation = "validated"
 }
 return nil,Info{Name:"panolab-ise14",InterfaceVersion:"1.0",InstanceID:instanceID,Vendor:"Xilinx",ToolchainVersion:"ISE 14.7",Profiles:[]string{"ise14-implementation"},ISE:ise==nil,License:available,LicenseValidated:proof!="",LicenseValidationStatus:validation,LicenseValidationJob:proof,Programming:false},nil
}
func loadProject(name string)(projectSpec,string,error){
 if !safeName.MatchString(name){return projectSpec{},"",errors.New("invalid project ID")}
 base:=filepath.Join(projectsRoot,name)
 info,err:=os.Lstat(base);if err!=nil{return projectSpec{},"",err}
 if !info.IsDir(){return projectSpec{},"",errors.New("project path must be a real directory")}
 raw,err:=readProjectFile(base,"build.json")
 if err!=nil{return projectSpec{},"",fmt.Errorf("missing project manifest: %w",err)}
 if len(raw)>8192{return projectSpec{},"",errors.New("manifest too large")}
 var p projectSpec
 if err=json.Unmarshal(raw,&p);err!=nil{return p,"",err}
 if !safeName.MatchString(p.Top) || !allowedParts[p.Part] || len(p.Verilog)==0 || len(p.Verilog)>64 {
  return p,"",errors.New("invalid top, part or source count")
 }
 for _,name:=range p.Verilog {
  if !safeFile.MatchString(name)||!strings.HasSuffix(name,".v"){return p,"",errors.New("invalid Verilog source filename")}
  if _,err=readProjectFile(base,name);err!=nil{return p,"",err}
 }
 if p.UCF!="" {
  if !safeFile.MatchString(p.UCF)||!strings.HasSuffix(p.UCF,".ucf"){return p,"",errors.New("invalid constraints filename")}
  if _,err=readProjectFile(base,p.UCF);err!=nil{return p,"",err}
 }
 return p,base,nil
}
func prepare(dir,base string,p projectSpec)error{
 var prj strings.Builder
 for _,name:=range p.Verilog{
  data,err:=readProjectFile(base,name);if err!=nil{return err}
  if err=os.WriteFile(filepath.Join(dir,name),data,0600);err!=nil{return err}
  fmt.Fprintf(&prj,"verilog work %s\n",name)
 }
 if p.UCF!=""{
  data,err:=readProjectFile(base,p.UCF);if err!=nil{return err}
  if err=os.WriteFile(filepath.Join(dir,"design.ucf"),data,0600);err!=nil{return err}
 }
 if err:=os.WriteFile(filepath.Join(dir,"design.prj"),[]byte(prj.String()),0600);err!=nil{return err}
 xst:=fmt.Sprintf("run\n-ifn design.prj\n-ifmt mixed\n-ofn design\n-ofmt NGC\n-p %s\n-top %s\n-opt_mode Speed\n-opt_level 1\n",p.Part,p.Top)
 return os.WriteFile(filepath.Join(dir,"design.xst"),[]byte(xst),0600)
}
var vendorStages=map[string]bool{"xst":true,"ngdbuild":true,"map":true,"par":true,"trce":true,"bitgen":true}
func vendorExecutable(stage string)(string,error){
 if !vendorStages[stage] {return "",errors.New("unsupported vendor stage")}
 return filepath.Join("/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64",stage),nil
}
func runStage(ctx context.Context,dir,stage string,args ...string)error{
 // Only the six pinned, known ISE executable paths may be launched.
 // Source the 14.7 environment locally within the SAME container.
 executable,err:=vendorExecutable(stage)
 if err!=nil{return err}
 code:=`. /opt/Xilinx/14.7/ISE_DS/settings64.sh && exec "$@"`
 argv:=append([]string{"-c",code,"panolab-stage",executable},args...)
 cmd:=exec.CommandContext(ctx,"/bin/bash",argv...);cmd.Dir=dir
 f,err:=os.OpenFile(filepath.Join(dir,stage+".log"),os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600)
 if err!=nil{return err};defer f.Close()
 cmd.Stdout=f;cmd.Stderr=f
 return cmd.Run()
}
func runBuild(ctx context.Context,dir string,p projectSpec)error{
 return runBuildWith(ctx,dir,p,runStage)
}
func runBuildWith(ctx context.Context,dir string,p projectSpec,stageRunner func(context.Context,string,string,...string)error)error{
 ngdArgs:=[]string{"-p",p.Part}
 if p.UCF!=""{ngdArgs=append(ngdArgs,"-uc","design.ucf")}
 ngdArgs=append(ngdArgs,"design.ngc","design.ngd")
 stages:=[]struct{name string;args []string}{
  {"xst",[]string{"-ifn","design.xst","-ofn","design.syr"}},
  {"ngdbuild",ngdArgs},
  {"map",[]string{"-w","-p",p.Part,"-o","design_map.ncd","design.ngd","design.pcf"}},
  {"par",[]string{"-w","design_map.ncd","design.ncd","design.pcf"}},
  {"trce",[]string{"-v","3","design.ncd","-o","design.twr","design.pcf"}},
  {"bitgen",[]string{"-w","design.ncd","design.bit"}},
 }
 for _,step:=range stages {
  if err:=stageRunner(ctx,dir,step.name,step.args...);err!=nil{return fmt.Errorf("%s: %w",step.name,err)}
 }
 info,err:=os.Lstat(filepath.Join(dir,"design.bit"))
 if err!=nil{return err};if !info.Mode().IsRegular() || info.Size()==0{return errors.New("generated bitstream is missing, nonregular or empty")}
 return nil
}
func start(ctx context.Context,r *mcp.CallToolRequest,in StartInput)(*mcp.CallToolResult,StartOutput,error){
 if in.Profile!="ise14-implementation"{return nil,StartOutput{},errors.New("unsupported build profile")}
 p,base,err:=loadProject(in.Project);if err!=nil{return nil,StartOutput{},err}
 if _,err=os.Stat("/opt/Xilinx/14.7/ISE_DS/settings64.sh");err!=nil{return nil,StartOutput{},errors.New("ISE environment unavailable")}
 jobs.Lock()
 if !observeLicenseLocked() {
  jobs.Unlock()
  return nil,StartOutput{},errors.New("license unavailable")
 }
 for _,j:=range jobs.items{if j.state=="running"{jobs.Unlock();return nil,StartOutput{},errors.New("worker busy")}}
 id:=fmt.Sprintf("%d",time.Now().UnixNano())
 jobctx,cancelFn:=context.WithTimeout(context.Background(),20*time.Minute)
 j:=&job{id:id,state:"running",exit:-1,project:in.Project,profile:in.Profile,cancel:cancelFn}
 jobs.items[id]=j
 jobs.Unlock()
 dir:=filepath.Join(root,id)
 if err=os.MkdirAll(dir,0700);err==nil {err=prepare(dir,base,p)}
 if err==nil{err=persistJob(j)}
 if err!=nil{cancelFn();jobs.Lock();delete(jobs.items,id);jobs.Unlock();return nil,StartOutput{},err}
 go func(){
  defer cancelFn()
  jobs.Lock()
  licenseAvailable := observeLicenseLocked()
  generation := jobs.licenseGeneration
  jobs.Unlock()
  if !licenseAvailable {
   finishJob(jobctx, j, 1, false, generation)
   return
  }
  err:=runBuild(jobctx,dir,p)
  rc:=0;if err!=nil{rc=1;var e *exec.ExitError;if errors.As(err,&e){rc=e.ExitCode()}}
  finishJob(jobctx, j, rc, true, generation)
 }()
 return nil,StartOutput{ID:id,State:"running"},nil
}
func finishJob(ctx context.Context, j *job, rc int, licenseAvailable bool, generation uint64) {
 jobs.Lock()
 defer jobs.Unlock()
 available := observeLicenseLocked()
 j.exit = rc
 switch {
 case ctx.Err() != nil:
  j.state = "cancelled"
 case rc == 0:
  j.state = "succeeded"
 default:
  j.state = "failed"
 }
 if err := persistJob(j); err != nil {
  j.state = "failed"
  j.exit = 125
  log.Print("failed to persist job: ", err)
  return
 }
 if j.state == "succeeded" && licenseAvailable && available && generation == jobs.licenseGeneration {
  jobs.licenseJob = j.id
 }
}

func lookup(id string)(job,error){
 if id==""||strings.Trim(id,"0123456789")!=""{return job{},errors.New("invalid job ID")}
 jobs.Lock();defer jobs.Unlock()
 j,ok:=jobs.items[id];if ok{return *j,nil}
 raw,err:=os.ReadFile(filepath.Join(root,id,"job.json"));if err!=nil{return job{},errors.New("unknown job")}
 var rec jobRecord
 if err=json.Unmarshal(raw,&rec);err!=nil||rec.ID!=id{return job{},errors.New("corrupt job history")}
 restored:=job{id:rec.ID,state:rec.State,exit:rec.Exit,project:rec.Project,profile:rec.Profile}
 if restored.state=="running"{
  restored.state="interrupted";restored.exit=125
  if err:=persistJob(&restored);err!=nil{log.Print("failed to persist interrupted job: ",err)}
 }
 jobs.items[id]=&restored
 return restored,nil
}
func status(ctx context.Context,r *mcp.CallToolRequest,in JobInput)(*mcp.CallToolResult,Status,error){
 j,err:=lookup(in.ID);if err!=nil{return nil,Status{},err}
 return nil,Status{ID:j.id,State:j.state,ExitCode:j.exit},nil
}
func openArtifact(path string) (*os.File, os.FileInfo, error) {
 before, err := os.Lstat(path)
 if err != nil {
  return nil, nil, err
 }
 if !before.Mode().IsRegular() {
  return nil, nil, errors.New("artifact must be a regular file")
 }
 file, err := os.Open(path)
 if err != nil {
  return nil, nil, err
 }
 info, err := file.Stat()
 if err != nil || !info.Mode().IsRegular() || !os.SameFile(before, info) {
  file.Close()
  return nil, nil, errors.New("invalid artifact identity")
 }
 return file, info, nil
}

func result(ctx context.Context,r *mcp.CallToolRequest,in JobInput)(*mcp.CallToolResult,BuildResult,error){
 j,err:=lookup(in.ID);if err!=nil{return nil,BuildResult{},err}
 out:=BuildResult{ID:j.id,State:j.state,ExitCode:j.exit,Project:j.project,Profile:j.profile,Artifacts:[]Artifact{}}
 dir:=filepath.Join(root,j.id)
 // Chunk queries avoid regenerating artifact hashes for every page.
 if in.Artifact!=""{
  if !artifactNames[in.Artifact]{return nil,BuildResult{},errors.New("unknown artifact")}
  if in.Offset<0{return nil,BuildResult{},errors.New("negative artifact offset")}
  f,info,err:=openArtifact(filepath.Join(dir,in.Artifact));if err!=nil{return nil,BuildResult{},err}
  defer f.Close()
  if in.Offset>info.Size(){return nil,BuildResult{},errors.New("invalid artifact offset")}
  chunkLimit := 49152 // Preserve paging for direct clients of other artifacts.
  if in.Artifact == "design.twr" {
   chunkLimit = 8192 // 10,924 base64 bytes plus framing fit the broker cap.
  }
  b:=make([]byte,chunkLimit)
  n,err:=f.ReadAt(b,in.Offset)
  if err!=nil&&!errors.Is(err,io.EOF){return nil,BuildResult{},err}
  out.ChunkBase64=base64.StdEncoding.EncodeToString(b[:n])
  out.ChunkOffset=in.Offset
  out.NextOffset=in.Offset+int64(n)
  out.ChunkEOF=out.NextOffset>=info.Size()
 }
 if in.Artifact!=""{return nil,out,nil}
 // The MCP client defines pass/fail test criteria. No baked-in smoke assertion.
 for _,name:=range []string{"xst.log","ngdbuild.log","map.log","par.log","trce.log","bitgen.log","design.bit","design.twr"}{
  f,_,err:=openArtifact(filepath.Join(dir,name));if err!=nil{continue}
  h:=sha256.New()
  n,copyErr:=io.Copy(h,f)
  if copyErr!=nil {
   f.Close()
   continue
  }
  mime:="text/plain";if strings.HasSuffix(name,".bit"){mime="application/octet-stream"}
  out.Artifacts=append(out.Artifacts,Artifact{Name:name,SHA256:hex.EncodeToString(h.Sum(nil)),Bytes:n,MediaType:mime})
  if strings.HasSuffix(name,".log"){
   const limit = 4096
   if n > limit { out.LogsTruncated = true }
   start := max(0, n-limit)
   b := make([]byte, n-start)
   if _, err := f.ReadAt(b, start); err == nil {
    out.Logs += name+":\n"+string(b)+"\n"
   }
  }
  f.Close()
 }
 if len(out.Logs)>32768{out.LogsTruncated=true;out.Logs=out.Logs[len(out.Logs)-32768:]}

 return nil,out,nil
}
func cancel(ctx context.Context,r *mcp.CallToolRequest,in JobInput)(*mcp.CallToolResult,Status,error){
 if _,err:=lookup(in.ID);err!=nil{return nil,Status{},err}
 jobs.Lock();defer jobs.Unlock()
 j:=jobs.items[in.ID]
 if j.state=="running"&&j.cancel!=nil{j.cancel()}
 return nil,Status{ID:j.id,State:j.state,ExitCode:j.exit},nil
}
func main(){
 if err:=os.MkdirAll(root,0700);err!=nil{log.Fatal(err)}
 s:=mcp.NewServer(&mcp.Implementation{Name:"panolab-ise14",Version:"0.2.0"},nil)
 mcp.AddTool(s,&mcp.Tool{Name:"toolchain_info",Description:"Read ISE toolchain and build profile availability"},toolchain)
 mcp.AddTool(s,&mcp.Tool{Name:"build_start",Description:"Run an approved project's generic ISE implementation build"},start)
 mcp.AddTool(s,&mcp.Tool{Name:"build_status",Description:"Read job state"},status)
 mcp.AddTool(s,&mcp.Tool{Name:"build_result",Description:"Read implementation report metadata, digests, and bounded stage logs"},result)
 mcp.AddTool(s,&mcp.Tool{Name:"build_cancel",Description:"Cancel an active build"},cancel)
 if os.Getenv("PANOLAB_MCP_TRANSPORT")=="stdio"{
  if err:=s.Run(context.Background(),&mcp.StdioTransport{});err!=nil{log.Fatal(err)}
  return
 }
 token:=os.Getenv("PANOLAB_MCP_TOKEN")
 if len(token)<32{log.Fatal("PANOLAB_MCP_TOKEN must contain at least 32 characters for HTTP mode")}
 m:=mcp.NewStreamableHTTPHandler(func(r *http.Request)*mcp.Server{return s},&mcp.StreamableHTTPOptions{Stateless:true,JSONResponse:true})
 mux:=http.NewServeMux()
 mux.HandleFunc("/mcp",func(w http.ResponseWriter,r *http.Request){
  got:=strings.TrimPrefix(r.Header.Get("Authorization"),"Bearer ")
  if subtle.ConstantTimeCompare([]byte(got),[]byte(token))!=1{http.Error(w,"unauthorized",http.StatusUnauthorized);return}
  m.ServeHTTP(w,r)
 })
 srv:=&http.Server{Addr:":8765",Handler:mux,ReadHeaderTimeout:5*time.Second}
 log.Fatal(srv.ListenAndServe())
}
