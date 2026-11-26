package main

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestISEBuildResultOptionalTimingSelector(t *testing.T) {
	const job = "1795652101955866441"
	server := mcp.NewServer(&mcp.Implementation{Name: "test-manager", Version: "1"}, nil)
	registerISETools(server, func(tool string, args Out) (*mcp.CallToolResult, Out, error) {
		if tool != "build_result" || args["ID"] != job {
			return nil, nil, fmt.Errorf("unexpected broker call %s: %v", tool, args)
		}
		return nil, Out{"artifact": args["Artifact"]}, nil
	})
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	clientTransport, serverTransport := mcp.NewInMemoryTransports()
	serverSession, err := server.Connect(ctx, serverTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer serverSession.Close()
	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "1"}, nil)
	session, err := client.Connect(ctx, clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer session.Close()
	for _, selector := range []string{"", "design.twr"} {
		args := Out{"ID": job}
		if selector != "" {
			args["Artifact"] = selector
		}
		result, err := session.CallTool(ctx, &mcp.CallToolParams{Name: "ise_build_result", Arguments: args})
		if err != nil || result.IsError {
			t.Fatalf("selector %q failed: %v, %v", selector, err, result)
		}
		data, ok := result.StructuredContent.(map[string]any)
		if !ok || data["artifact"] != selector {
			t.Fatalf("selector %q yielded %v", selector, result.StructuredContent)
		}
	}
}
