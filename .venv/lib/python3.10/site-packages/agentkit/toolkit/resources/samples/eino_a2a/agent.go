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
	"os"

	"github.com/cloudwego/eino/adk"
	"github.com/eino-contrib/agentkit-ve/components/model/chatmodelprovider"
)

func buildSimpleAgent(ctx context.Context) (adk.Agent, error) {
	agentName := "{{ agent_name | default('A2ASimpleAgent') }}"
	var description string
	{% if description %}description = `{{ description }}`{% else %}description = DEFAULT_DESCRIPTION{% endif %}

	var instruction string
	{% if system_prompt %}instruction = `{{ system_prompt }}`{% else %}instruction = DEFAULT_INSTRUCTION{% endif %}
	// // ========================================================

	// Resolve BaseURL from env or use default
	baseURL := os.Getenv("MODEL_AGENT_BASE_URL")
	if baseURL == "" {
		baseURL = "https://ark.cn-beijing.volces.com/api/v3"
	}

	cm, err := chatmodelprovider.NewChatModel(ctx, &chatmodelprovider.Config{
		Provider: os.Getenv("MODEL_AGENT_PROVIDER"),
		APIKey:   os.Getenv("MODEL_AGENT_API_KEY"),
		Model:    os.Getenv("MODEL_AGENT_NAME"),
		BaseURL:  os.Getenv("MODEL_AGENT_API_BASE"),
	})
	if err != nil {
		return nil, err
	}

	a, err := adk.NewChatModelAgent(ctx, &adk.ChatModelAgentConfig{
		Name:        agentName,
		Description: description,
		Instruction: instruction,
		Model:       cm,
	})

	if err != nil {
		return nil, fmt.Errorf("failed to create chatmodel: %w", err)
	}

	return a, nil
}
