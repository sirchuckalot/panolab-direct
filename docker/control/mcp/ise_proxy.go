package main

// ISE access is relayed through the existing restricted rootless Docker broker.
// The manager never receives the worker's bearer token or a Docker socket.
// These are *project build* operations only; there is no host shell or FPGA
// programming tool in this interface.
import (
 "context"
 "github.com/modelcontextprotocol/go-sdk/mcp"
)

type ISEBuildRequest struct {
 Profile string
 Project string
}
type ISEJobRequest struct {
 ID string
}
type ISEStageRequest struct {
 Project string
}
func iseCall(tool string, args Out)(*mcp.CallToolResult,Out,error){
 return broker(Out{"action":"ise_rpc","tool":tool,"arguments":args})
}
func registerISETools(s *mcp.Server){
 mcp.AddTool(s,&mcp.Tool{Name:"ise_toolchain_info",Description:"Inspect the isolated ISE 14.7 build worker (no license disclosure)"},
  func(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
   return iseCall("toolchain_info",Out{})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_worker_diagnostics",Description:"Inspect safe worker project and results-directory readiness without secrets or logs"},
  func(_ context.Context,_ *mcp.CallToolRequest,_ Empty)(*mcp.CallToolResult,Out,error){
   return iseCall("diagnose",Out{})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_project_stage",Description:"Stage a validated immutable FPGA source revision from the approved development workspace (no vendor rebuild or hardware programming)"},
  func(_ context.Context,_ *mcp.CallToolRequest,in ISEStageRequest)(*mcp.CallToolResult,Out,error){
   return broker(Out{"action":"ise_stage","project":in.Project})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_build_start",Description:"Start a bounded ISE Spartan-6 build for a pre-staged approved project; no FPGA programming"},
  func(_ context.Context,_ *mcp.CallToolRequest,in ISEBuildRequest)(*mcp.CallToolResult,Out,error){
   return iseCall("build_start",Out{"Profile":in.Profile,"Project":in.Project})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_build_status",Description:"Check a bounded ISE build job by numeric ID"},
  func(_ context.Context,_ *mcp.CallToolRequest,in ISEJobRequest)(*mcp.CallToolResult,Out,error){
   return iseCall("build_status",Out{"ID":in.ID})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_build_result",Description:"Read sanitized ISE build result status, artifact metadata, and diagnostic categories"},
  func(_ context.Context,_ *mcp.CallToolRequest,in ISEJobRequest)(*mcp.CallToolResult,Out,error){
   return iseCall("build_result",Out{"ID":in.ID})
  })
 mcp.AddTool(s,&mcp.Tool{Name:"ise_build_cancel",Description:"Cancel a running ISE project build by numeric ID"},
  func(_ context.Context,_ *mcp.CallToolRequest,in ISEJobRequest)(*mcp.CallToolResult,Out,error){
   return iseCall("build_cancel",Out{"ID":in.ID})
  })
}
