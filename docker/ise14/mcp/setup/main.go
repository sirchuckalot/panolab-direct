// Separate, owner-approved ISE media and installation service.
// It does not provide the persistent five-tool vendor build worker
// and never authorizes FPGA programming or unbounded host operations.
package main
import(
 "archive/tar";"compress/gzip";"compress/bzip2";"context";"crypto/sha256";"crypto/subtle";"encoding/hex";"encoding/json";"errors";"fmt";"io";"log";"net/http";"os";"os/exec";"path/filepath";"strings";"sync";"time"
 "github.com/modelcontextprotocol/go-sdk/mcp"
)
type Empty struct{}
type InstallInput struct{SHA256 string; Confirmation string}
type Out map[string]any
type State struct{State string; Error string}
var mu sync.Mutex
var busy bool
const approve="INSTALL_ISE_14_7_IN_PANOLAB_ONLY"
func regular(p string)bool{i,e:=os.Lstat(p);return e==nil&&i.Mode().IsRegular()}
func checksum()(string,int64,error){
 f,e:=os.Open("/media/ise.tar");if e!=nil{return "",0,e};defer f.Close()
 i,e:=f.Stat();if e!=nil||!i.Mode().IsRegular()||i.Size()>20<<30{return "",0,errors.New("invalid ISE tarball")}
 h:=sha256.New();n,e:=io.Copy(h,f);return hex.EncodeToString(h.Sum(nil)),n,e
}
func info(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 return nil,Out{"service":"panolab-setup","tarball":regular("/media/ise.tar"),"license":regular("/licenses/Xilinx.lic"),"installed":regular("/opt/Xilinx/14.7/ISE_DS/settings64.sh"),"docker_socket":false},nil
}
func inspect(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 h,n,e:=checksum();if e!=nil{return nil,nil,e}
 return nil,Out{"sha256":h,"bytes":n,"license":regular("/licenses/Xilinx.lic"),"required_confirmation":approve},nil
}
func load()State{
 b,e:=os.ReadFile("/work/install-state.json");if e!=nil{return State{State:"not_started"}}
 var s State;if json.Unmarshal(b,&s)!=nil{return State{State:"corrupt"}}
 if s.State=="running"&&!busy{s.State="interrupted"}
 return s
}
func save(s State){
 b,_:=json.Marshal(s)
 if e:=os.WriteFile("/work/install-state.json.tmp",b,0600);e!=nil{log.Print(e);return}
 if e:=os.Rename("/work/install-state.json.tmp","/work/install-state.json");e!=nil{log.Print(e)}
}
func status(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 mu.Lock();defer mu.Unlock()
 s:=load();return nil,Out{"state":s.State,"error":s.Error},nil
}
func validateArchive()error{
 f,e:=os.Open("/media/ise.tar");if e!=nil{return e};defer f.Close()
 b:=make([]byte,3);if _,e=f.ReadAt(b,0);e!=nil{return e}
 var rd io.Reader=f
 if b[0]==31&&b[1]==139{z,err:=gzip.NewReader(f);if err!=nil{return err};defer z.Close();rd=z
 }else if string(b)=="BZh"{rd=bzip2.NewReader(f)}
 t:=tar.NewReader(rd);var bytes int64;var count int
 for{
  h,err:=t.Next();if errors.Is(err,io.EOF){return nil};if err!=nil{return err}
  count++;if count>200000{return errors.New("tar member count exceeded")}
  n:=filepath.Clean(h.Name)
  if h.Name==""||filepath.IsAbs(h.Name)||n==".."||n=="."||strings.HasPrefix(n,"../")||strings.ContainsRune(h.Name,'\\'){return errors.New("unsafe tar path")}
  if h.Typeflag!=tar.TypeReg&&h.Typeflag!=tar.TypeRegA&&h.Typeflag!=tar.TypeDir{return errors.New("archive includes symlink/device; installation blocked")}
  if h.Size<0||h.Size>4<<30{return errors.New("invalid member size")}
  bytes+=h.Size;if bytes>30<<30{return errors.New("tar extraction size exceeded")}
 }
}
func perform(ctx context.Context)error{
 if !regular("/licenses/Xilinx.lic"){return errors.New("license missing")}
 files,e:=os.ReadDir("/opt/Xilinx");if e!=nil{return e};if len(files)>0{return errors.New("ISE installation directory not empty")}
 if e=validateArchive();e!=nil{return e}
 if e=os.Mkdir("/work/ise-media",0700);e!=nil{return e}
 c:=exec.CommandContext(ctx,"tar","-xf","/media/ise.tar","-C","/work/ise-media")
 if b,e:=c.CombinedOutput();e!=nil{return fmt.Errorf("tar extraction failed: %w (%s)",e,string(b[:min(len(b),256)]))}
 var dir string
 e=filepath.Walk("/work/ise-media",func(p string,i os.FileInfo,err error)error{
  if err!=nil{return err}
  if i.IsDir()||filepath.Base(p)!="batchxsetup"||filepath.Base(filepath.Dir(p))!="lin64"{return nil}
  if dir!=""{return errors.New("multiple installers")}
  dir=filepath.Dir(filepath.Dir(filepath.Dir(p)));return nil
 });if e!=nil{return e}
 if dir==""||!regular(filepath.Join(dir,"xsetup")){return errors.New("ISE native batch installer missing")}
 if e=os.Chmod(filepath.Join(dir,"bin/lin64/batchxsetup"),0700);e!=nil{return e}
 lf,e:=os.OpenFile("/work/ise-install.log",os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600);if e!=nil{return e};defer lf.Close()
 c=exec.CommandContext(ctx,"/bin/bash","-c","yes | ./bin/lin64/batchxsetup --batch /config/ise-system-edition.batch")
 c.Dir=dir;c.Env=append(os.Environ(),"HOME=/work","TERM=xterm");c.Stdout=lf;c.Stderr=lf
 if e=c.Run();e!=nil{return fmt.Errorf("vendor installer failed: %w",e)}
 if !regular("/opt/Xilinx/14.7/ISE_DS/settings64.sh"){return errors.New("ISE settings file missing after installation")}
 return nil
}
func start(_ context.Context,_ *mcp.CallToolRequest,in InstallInput)(*mcp.CallToolResult,Out,error){
 if in.Confirmation!=approve{return nil,nil,errors.New("explicit owner confirmation phrase required")}
 h,_,e:=checksum();if e!=nil{return nil,nil,e}
 if subtle.ConstantTimeCompare([]byte(h),[]byte(in.SHA256))!=1{return nil,nil,errors.New("archive checksum mismatch")}
 mu.Lock()
 if busy||load().State!="not_started"{mu.Unlock();return nil,nil,errors.New("installation already attempted; manual review required")}
 busy=true;save(State{State:"running"});mu.Unlock()
 go func(){
  ctx,cancel:=context.WithTimeout(context.Background(),2*time.Hour);defer cancel()
  err:=perform(ctx)
  mu.Lock();defer mu.Unlock()
  if err!=nil{save(State{State:"failed",Error:err.Error()})}else{save(State{State:"succeeded"})}
  busy=false
 }()
 return nil,Out{"state":"running","message":"ISE installation running inside CentOS; use ise_install_status"},nil
}
func main(){
 token,e:=os.ReadFile("/run/secrets/mcp-bearer");if e!=nil||len(token)<39{log.Fatal("MCP authorization file missing")}
 s:=mcp.NewServer(&mcp.Implementation{Name:"panolab-setup",Version:"0.1.0"},nil)
 mcp.AddTool(s,&mcp.Tool{Name:"lab_status",Description:"Scoped read-only setup status"},info)
 mcp.AddTool(s,&mcp.Tool{Name:"ise_media_inspect",Description:"Inspect ISE tarball checksum without revealing files"},inspect)
 mcp.AddTool(s,&mcp.Tool{Name:"ise_install_start",Description:"Explicitly approved ISE installation in private CentOS environment"},start)
 mcp.AddTool(s,&mcp.Tool{Name:"ise_install_status",Description:"Read installation status"},status)
 h:=mcp.NewStreamableHTTPHandler(func(_ *http.Request)*mcp.Server{return s},&mcp.StreamableHTTPOptions{Stateless:true,JSONResponse:true})
 mux:=http.NewServeMux()
 mux.HandleFunc("/mcp",func(w http.ResponseWriter,r *http.Request){
  if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")),token)!=1{http.Error(w,"unauthorized",401);return}
  h.ServeHTTP(w,r)
 })
 log.Fatal((&http.Server{Addr:":8766",Handler:mux,ReadHeaderTimeout:5*time.Second}).ListenAndServe())
}
