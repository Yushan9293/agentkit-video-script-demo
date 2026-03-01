# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
AgentKit Toolkit - Build, deploy, and manage AI agents.

This package provides both CLI and SDK interfaces for agent development:

CLI Usage:
    $ agentkit build
    $ agentkit deploy
    $ agentkit invoke "Hello, agent!"

SDK Usage:
    >>> from agentkit.toolkit import sdk
    >>> result = sdk.build(config_file="agentkit.yaml")
    >>> result = sdk.deploy()
    >>> result = sdk.invoke(payload={"prompt": "Hello!"})
"""

# Export SDK module for programmatic access
from . import sdk

# Export ExecutionContext for advanced usage
from .context import ExecutionContext

__all__ = ["sdk", "ExecutionContext"]
