package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const testSetupToken = "unit-test-token-for-the-fake-setup-service"
const testSetupBearer = "Bearer " + testSetupToken

func testProxy(url string) *setupProxy {
	p := newSetupProxy(testSetupBearer)
	p.url = url
	return p
}

func TestSetupProxySDK(t *testing.T) {
	sha := strings.Repeat("a", 64)
	downstream := mcp.NewServer(&mcp.Implementation{Name: "fake-setup", Version: "1"}, nil)
	mcp.AddTool(downstream, &mcp.Tool{Name: "lab_status"},
		func(context.Context, *mcp.CallToolRequest, Empty) (*mcp.CallToolResult, Out, error) {
			return nil, Out{"service": "fake-setup"}, nil
		})
	mcp.AddTool(downstream, &mcp.Tool{Name: "ise_media_inspect"},
		func(context.Context, *mcp.CallToolRequest, Empty) (*mcp.CallToolResult, any, error) {
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: sha}}}, nil, nil
		})
	mcp.AddTool(downstream, &mcp.Tool{Name: "ise_install_status"},
		func(context.Context, *mcp.CallToolRequest, Empty) (*mcp.CallToolResult, Out, error) {
			return nil, Out{"state": "failed", "error": "private installer diagnostics"}, nil
		})
	mcp.AddTool(downstream, &mcp.Tool{Name: "ise_install_start"},
		func(_ context.Context, _ *mcp.CallToolRequest, in setupInstallInput) (*mcp.CallToolResult, Out, error) {
			if in.SHA256 != sha || in.Confirmation != installConfirmation {
				return nil, nil, errors.New("incorrect arguments")
			}
			return nil, Out{"state": "fake-only"}, nil
		})
	handler := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return downstream },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	var forwarded atomic.Int32
	httpServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		if r.URL.Path != "/mcp" || r.Method != http.MethodPost ||
			r.Header.Get("Authorization") != testSetupBearer ||
			r.Header.Get("Content-Type") != "application/json" ||
			r.Header.Get("Accept") != "application/json, text/event-stream" ||
			r.Header.Get("MCP-Protocol-Version") != "2025-06-18" {
			t.Error("incorrect setup request path, method or headers")
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		handler.ServeHTTP(w, r)
	}))
	defer httpServer.Close()

	manager := mcp.NewServer(&mcp.Implementation{Name: "fake-manager", Version: "1"}, nil)
	registerSetupTools(manager, testProxy(httpServer.URL+"/mcp"))
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	clientTransport, serverTransport := mcp.NewInMemoryTransports()
	serverSession, err := manager.Connect(ctx, serverTransport, nil)
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

	for _, tc := range []struct {
		name       string
		args       any
		structured string
		fallback   string
	}{
		{name: "ise_setup_status", structured: `{"service":"fake-setup"}`},
		{name: "ise_media_inspect", fallback: sha},
		{name: "ise_install_status", structured: `{"error":"ISE setup reported an installation error","state":"failed"}`},
		{name: "ise_install_start", args: setupInstallInput{sha, installConfirmation}, structured: `{"state":"fake-only"}`},
	} {
		t.Run(tc.name, func(t *testing.T) {
			out, err := session.CallTool(ctx, &mcp.CallToolParams{Name: tc.name, Arguments: tc.args})
			if err != nil || out.IsError {
				t.Fatalf("tool call failed: result=%v error=%v", out, err)
			}
			wantText := tc.fallback
			if tc.structured != "" {
				wantText = tc.structured
				data, err := json.Marshal(out.StructuredContent)
				if err != nil || string(data) != tc.structured {
					t.Fatalf("structuredContent = %s, error = %v", data, err)
				}
			} else if out.StructuredContent != nil {
				t.Fatal("fallback unexpectedly produced structuredContent")
			}
			if len(out.Content) != 1 {
				t.Fatalf("content count = %d", len(out.Content))
			}
			if item, ok := out.Content[0].(*mcp.TextContent); !ok || item.Text != wantText {
				t.Fatal("incorrect text content")
			}
		})
	}
	if got := forwarded.Load(); got != 4 {
		t.Fatalf("forwarded %d requests, want one POST per call", got)
	}

	for _, in := range []setupInstallInput{
		{sha, " " + installConfirmation},
		{sha, installConfirmation + "\n"},
		{strings.ToUpper(sha), installConfirmation},
		{sha[:63], installConfirmation},
		{sha + "\n", installConfirmation},
		{strings.Repeat("g", 64), installConfirmation},
	} {
		out, err := session.CallTool(ctx, &mcp.CallToolParams{Name: "ise_install_start", Arguments: in})
		if err != nil || !out.IsError {
			t.Fatalf("expected tool validation error, got result=%v error=%v", out, err)
		}
	}
	if got := forwarded.Load(); got != 4 {
		t.Fatalf("invalid install input reached setup, total POSTs = %d", got)
	}
}

func TestSetupProxySafeFailures(t *testing.T) {
	for _, tc := range []struct {
		name   string
		status int
		body   string
		want   error
	}{
		{"unauthorized", http.StatusUnauthorized, testSetupBearer, errSetupUnavailable},
		{"redirect", http.StatusTemporaryRedirect, testSetupBearer, errSetupUnavailable},
		{"oversized", http.StatusOK, strings.Repeat("x", setupResponseLimit+1), errSetupResponse},
		{"malformed", http.StatusOK, testSetupBearer, errSetupResponse},
		{"protocol error", http.StatusOK, `{"jsonrpc":"2.0","id":1,"error":{"code":-32603,"message":"` + testSetupBearer + `"}}`, errSetupRejected},
		{"tool error", http.StatusOK, `{"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[{"type":"text","text":"` + testSetupBearer + `"}]}}`, errSetupRejected},
		{"echoed bearer", http.StatusOK, `{"jsonrpc":"2.0","id":1,"result":{"structuredContent":{"value":"` + testSetupToken + `"},"content":[]}}`, errSetupResponse},
		{"echoed bearer in fallback", http.StatusOK, `{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"` + testSetupToken + `"}]}}`, errSetupResponse},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/" {
					t.Error("proxy followed a redirect")
				}
				w.Header().Set("Content-Type", "application/json")
				if tc.status == http.StatusTemporaryRedirect {
					w.Header().Set("Location", "/redirected")
				}
				w.WriteHeader(tc.status)
				_, _ = io.WriteString(w, tc.body)
			}))
			defer server.Close()
			assertSetupProxyError(t, testProxy(server.URL), context.Background(), tc.want)
		})
	}
	t.Run("offline", func(t *testing.T) {
		server := httptest.NewServer(http.NotFoundHandler())
		server.Close()
		assertSetupProxyError(t, testProxy(server.URL), context.Background(), errSetupUnavailable)
	})
	t.Run("canceled", func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			cancel()
		}))
		defer server.Close()
		assertSetupProxyError(t, testProxy(server.URL), ctx, context.Canceled)
	})
}

func assertSetupProxyError(t *testing.T, proxy *setupProxy, ctx context.Context, want error) {
	t.Helper()
	result, out, err := proxy.call(ctx, "lab_status", Empty{})
	if result != nil || out != nil || !errors.Is(err, want) || strings.Contains(err.Error(), testSetupToken) {
		t.Fatal("incorrect or unsafe proxy failure")
	}
}
