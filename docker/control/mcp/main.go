// MCP manager: authenticated remote entrypoint. Docker and Git operations
// are delegated to constrained private brokers, never a host shell.
package main

import (
 "context"
 "crypto/subtle"
 "encoding/json"
 "errors"
 "io"
 "log"
 "net"
 "net/http"
 "os"
 "path/filepath"
 "strings"
 "time"
 "github.com/modelcontextprotocol/go-sdk/mcp"
)

type Empty struct{}
type Name struct { Container string }
type Operation struct { Container string; Operation string }
type Image struct { Image string }
type Exec struct { Argv []string; User string }
type Path struct { Path string }
type Write struct { Path string; Content string }
type Out map[string]any
var workspace *os.Root

func broker(data Out)(*mcp.CallToolResult,Out,error){
 c,e:=net.DialTimeout("unix","/rpc/panolab.sock",3*time.Second)
 if e!=nil{return nil,nil,e}
 defer c.Close()
 _=c.SetDeadline(time.Now().Add(185*time.Second))
 request,e:=json.Marshal(data);if e!=nil{return nil,nil,e}
 if _,e=c.Write(append(request,'\n'));e!=nil{return nil,nil,e}
 reply,e:=io.ReadAll(io.LimitReader(c,65536));if e!=nil{return nil,nil,e}
 var result Out
 if e=json.Unmarshal(reply,&result);e!=nil{return nil,nil,e}
 return nil,result,nil
}
func status(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"status"})}
func build(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"build"})}
func pull(_ context.Context,_ *mcp.CallToolRequest,in Image)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"pull","image":in.Image})}
func create(_ context.Context,_ *mcp.CallToolRequest,in Image)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"create","image":in.Image})}
func lifecycle(_ context.Context,_ *mcp.CallToolRequest,in Operation)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"lifecycle","container":in.Container,"operation":in.Operation})}
func logs(_ context.Context,_ *mcp.CallToolRequest,in Name)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"logs","container":in.Container})}
func exec(_ context.Context,_ *mcp.CallToolRequest,in Exec)(*mcp.CallToolResult,Out,error){return broker(Out{"action":"exec","argv":in.Argv,"user":in.User})}

func safePath(s string) error {
 if s==""||filepath.IsAbs(s)||strings.ContainsRune(s,'\\')||strings.ContainsRune(s,0){return errors.New("invalid relative path")}
 n:=filepath.Clean(s)
 if n=="."||n==".."||strings.HasPrefix(n,"../"){return errors.New("path traversal")}
 return nil
}
func listing(_ context.Context,_ *mcp.CallToolRequest,in Path)(*mcp.CallToolResult,Out,error){
 p:=in.Path;if p==""{p="."}
 if p!="."{if e:=safePath(p);e!=nil{return nil,nil,e}}
 f,e:=workspace.Open(p);if e!=nil{return nil,nil,e};defer f.Close()
 es,e:=f.ReadDir(100);if e!=nil && !errors.Is(e,io.EOF){return nil,nil,e}
 result:=[]Out{}
 for _,v:=range es{result=append(result,Out{"name":v.Name(),"directory":v.IsDir()})}
 return nil,Out{"entries":result},nil
}
func read(_ context.Context,_ *mcp.CallToolRequest,in Path)(*mcp.CallToolResult,Out,error){
 if e:=safePath(in.Path);e!=nil{return nil,nil,e}
 f,e:=workspace.Open(in.Path);if e!=nil{return nil,nil,e};defer f.Close()
 st,e:=f.Stat();if e!=nil{return nil,nil,e}
 if !st.Mode().IsRegular()||st.Size()>1048576{return nil,nil,errors.New("not a regular file or exceeds 1 MiB")}
 b,e:=io.ReadAll(io.LimitReader(f,1048577));if e!=nil{return nil,nil,e}
 return nil,Out{"content":string(b),"path":in.Path},nil
}
func write(_ context.Context,_ *mcp.CallToolRequest,in Write)(*mcp.CallToolResult,Out,error){
 if e:=safePath(in.Path);e!=nil{return nil,nil,e}
 if len(in.Content)>1048576{return nil,nil,errors.New("file exceeds 1 MiB")}
 if strings.HasPrefix(filepath.Base(in.Path),"."){return nil,nil,errors.New("hidden file blocked")}
 f,e:=workspace.OpenFile(in.Path,os.O_WRONLY|os.O_CREATE|os.O_TRUNC,0600)
 if e!=nil{return nil,nil,e}
 _,e=f.Write([]byte(in.Content));ce:=f.Close();if e==nil{e=ce}
 if e!=nil{return nil,nil,e}
 return nil,Out{"written":in.Path,"bytes":len(in.Content)},nil
}
type RepoCommit struct { Paths []string; Message string }

func repoService(in Out)(*mcp.CallToolResult,Out,error){
 c,e:=net.DialTimeout("unix","/repo-rpc/panolab-git.sock",3*time.Second)
 if e!=nil{return nil,nil,e}
 defer c.Close()
 _=c.SetDeadline(time.Now().Add(170*time.Second))
 request,e:=json.Marshal(in);if e!=nil{return nil,nil,e}
 if _,e=c.Write(append(request,'\n'));e!=nil{return nil,nil,e}
 reply,e:=io.ReadAll(io.LimitReader(c,1200000));if e!=nil{return nil,nil,e}
 var result Out
 if e=json.Unmarshal(reply,&result);e!=nil{return nil,nil,e}
 return nil,result,nil
}
func repoStatus(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"status"})
}
func repoList(_ context.Context,_ *mcp.CallToolRequest,in Path)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"list","path":in.Path})
}
func repoRead(_ context.Context,_ *mcp.CallToolRequest,in Path)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"read","path":in.Path})
}
func repoWrite(_ context.Context,_ *mcp.CallToolRequest,in Write)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"write","path":in.Path,"content":in.Content})
}
func repoSync(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"sync"})
}
func repoCommit(_ context.Context,_ *mcp.CallToolRequest,in RepoCommit)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"commit","paths":in.Paths,"message":in.Message})
}
func repoPush(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 return repoService(Out{"action":"push"})
}
func attachDev(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
 return broker(Out{"action":"attach_checkout","image":"panolab-direct-modern:local"})
}

func main(){
 var e error
 workspace,e=os.OpenRoot("/workspace");if e!=nil{log.Fatal(e)}
 token,e:=os.ReadFile("/run/secrets/mcp-bearer");if e!=nil||len(token)<39{log.Fatal("private MCP bearer missing")}
 s:=mcp.NewServer(&mcp.Implementation{Name:"panolab-manager",Version:"0.1.0"},nil)
 mcp.AddTool(s,&mcp.Tool{Name:"lab_status",Description:"Read PanoLab service status"},status)
 mcp.AddTool(s,&mcp.Tool{Name:"lab_logs",Description:"Read 100 log lines from a known PanoLab service"},logs)
 mcp.AddTool(s,&mcp.Tool{Name:"lab_lifecycle",Description:"Start, stop, or restart named PanoLab services only"},lifecycle)
 mcp.AddTool(s,&mcp.Tool{Name:"image_build_modern",Description:"Build the approved PanoLab development image"},build)
 mcp.AddTool(s,&mcp.Tool{Name:"image_pull_approved",Description:"Pull approved Ubuntu/Python container image"},pull)
 mcp.AddTool(s,&mcp.Tool{Name:"dev_create",Description:"Create one restricted development container"},create)
 mcp.AddTool(s,&mcp.Tool{Name:"dev_exec",Description:"Execute an argument array inside dev container, never host"},exec)
 mcp.AddTool(s,&mcp.Tool{Name:"workspace_list",Description:"List files in the PanoLab-only workspace"},listing)
 mcp.AddTool(s,&mcp.Tool{Name:"workspace_read",Description:"Read a workspace file (up to 1 MiB)"},read)
 mcp.AddTool(s,&mcp.Tool{Name:"workspace_write",Description:"Write a workspace file (up to 1 MiB)"},write)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_status",Description:"Read existing laptop Git checkout branch, commit and changes"},repoStatus)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_list",Description:"List approved source paths in the existing laptop checkout"},repoList)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_read",Description:"Read approved source file (no secrets or symlinks)"},repoRead)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_write",Description:"Write approved source file in the owner local clone; not a second checkout"},repoWrite)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_sync",Description:"Fetch and fast-forward the clean current main/development branch"},repoSync)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_commit",Description:"Commit selected source files on the current approved branch"},repoCommit)
 mcp.AddTool(s,&mcp.Tool{Name:"repo_push",Description:"Push approved branch only if scoped GitHub credentials exist"},repoPush)
 mcp.AddTool(s,&mcp.Tool{Name:"dev_attach_checkout",Description:"Safely reconfigure PanoLab dev container with selected bind mounts from existing laptop clone"},attachDev)
 registerSetupTools(s,newSetupProxy(string(token)))
 registerISETools(s, iseCall)
 handler:=mcp.NewStreamableHTTPHandler(func(_ *http.Request)*mcp.Server{return s},&mcp.StreamableHTTPOptions{Stateless:true,JSONResponse:true})
 mux:=http.NewServeMux()
 mux.HandleFunc("/mcp",func(w http.ResponseWriter,r *http.Request){
  if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")),token)!=1{http.Error(w,"unauthorized",401);return}
  handler.ServeHTTP(w,r)
 })
 log.Fatal((&http.Server{Addr:":8767",Handler:mux,ReadHeaderTimeout:5*time.Second}).ListenAndServe())
}
