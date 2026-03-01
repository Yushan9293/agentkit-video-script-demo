// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"context"
	"fmt"
	"log"
	"os"

	ccb "github.com/cloudwego/eino-ext/callbacks/cozeloop"
	"github.com/cloudwego/eino/callbacks"
	"github.com/cloudwego/hertz/pkg/app"
	"github.com/coze-dev/cozeloop-go"

	server "github.com/eino-contrib/agentkit-ve/server/a2a"
)

const (
	DEFAULT_DESCRIPTION = "An AI agent developed by the Eino team, specialized in data science, documentation, and software development."

	DEFAULT_INSTRUCTION = `You are an AI agent created by the Eino team.

You excel at the following tasks:
1. Data science
   - Information gathering and fact-checking
   - Data processing and analysis
2. Documentation
   - Writing multi-chapter articles and in-depth research reports
3. Coding & Programming
   - Creating websites, applications, and tools
   - Solve problems and bugs in code (e.g., Golang Python, JavaScript, SQL...)
   - If necessary, using programming to solve various problems beyond development
4. If user gives you tools, finish various tasks that can be accomplished using tools and available resources`
)

func main() {
	ctx := context.Background()

	// Create server instance using the new v2 pattern
	srv := server.New()

	// Register the agent with the server instance
	simpleAgent, err := buildSimpleAgent(ctx)
	if err != nil {
		log.Fatalf("build simple agent failed: %v", err)
	}

	err = srv.RegisterAgent(ctx, simpleAgent, server.WithHandlerPath("/"))
	if err != nil {
		log.Fatalf("register simple agent failed: %v", err)
	}

	closeFn, einoHandler, hertzMiddleware, err := buildCozeLoopTraceCallbacks(ctx, simpleAgent.Name(ctx))
	if err != nil {
		log.Fatalf("build cozeloop trace callbacks failed: %v", err)
	}

	// register eino agent's trace callback
	callbacks.AppendGlobalHandlers(einoHandler /*trace callback*/)

	// Run server with configuration options (blocks until context is cancelled)
	log.Println("Starting A2A server...")
	err = srv.Run(ctx,
		server.WithPort(8000),
		server.WithMiddlewares(hertzMiddleware))
	if err != nil {
		log.Fatalf("run a2a server failed: %v", err)
	}

	closeFn(ctx)
	log.Println("Server stopped gracefully")
}

type closeLoopFn func(ctx context.Context)

func buildCozeLoopTraceCallbacks(ctx context.Context, agentName string) (closeLoopFn, callbacks.Handler, app.HandlerFunc, error) {
	// setup cozeloop
	// COZELOOP_WORKSPACE_ID=your workspace id
	// COZELOOP_API_TOKEN=your token

	// use cozeloop trace, from https://loop.coze.cn/open/docs/cozeloop/go-sdk#4a8c980e
	wsID := os.Getenv("COZELOOP_WORKSPACE_ID")
	apiKey := os.Getenv("COZELOOP_API_TOKEN")
	if wsID == "" || apiKey == "" {
		return func(ctx context.Context) {
				return
			},
			callbacks.NewHandlerBuilder().Build(),
			func(c context.Context, ctx *app.RequestContext) {
				ctx.Next(c)
			}, nil
	}

	client, err := cozeloop.NewClient(
		cozeloop.WithWorkspaceID(wsID),
		cozeloop.WithAPIToken(apiKey),
	)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("cozeloop.NewClient failed, err: %v", err)
	}

	// create eino callback handler
	einoHandler := ccb.NewLoopHandler(client)

	// create hertz middleware as root trace
	hertzMiddleware := func(c context.Context, reqCtx *app.RequestContext) {
		nCtx, span := client.StartSpan(c, agentName, "custom")

		span.SetInput(nCtx, reqCtx.GetRawData())
		span.SetTags(nCtx, map[string]any{
			"path":   reqCtx.Request.Path(),
			"method": reqCtx.Request.Method(),
		})

		reqCtx.Next(nCtx)

		span.SetOutput(nCtx, reqCtx.GetResponse().Body())
		span.Finish(nCtx)
	}

	return client.Close, einoHandler, hertzMiddleware, nil
}
