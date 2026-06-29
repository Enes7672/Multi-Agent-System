"""
Frontend Development Agent

Develops React/Vue components, styling, and state management using starcoder:3b.
"""

import logging
from typing import Dict, Any

from .base_agent import BaseAgent, AgentRole, TaskResult, AgentCapability

logger = logging.getLogger(__name__)


class FrontendDeveloperAgent(BaseAgent):
    """Frontend development specialist agent."""

    AGENT_ID = "frontend-developer"
    AGENT_ROLE = AgentRole.FRONTEND_DEVELOPER
    AGENT_DESCRIPTION = "Frontend development expert - React, Vue, TypeScript, and UI/UX"
    AGENT_PROMPT = """You are a frontend development expert.
Your tasks:
- Write React/Vue components
- Develop TypeScript/JavaScript code
- Improve UI/UX
- Create CSS/Tailwind styles
- Build responsive designs

Rules:
- Use component-driven development
- Write reusable components
- Use state management
- Optimize performance
- Follow accessibility (a11y) guidelines"""
    AGENT_CAPABILITIES = [
            AgentCapability(
                name="react_component",
                description="React component development",
                input_types=["component_spec", "design"],
                output_types=["typescript", "css"],
            ),
            AgentCapability(
                name="vue_component",
                description="Vue component development",
                input_types=["component_spec"],
                output_types=["typescript", "css"],
            ),
            AgentCapability(
                name="styling",
                description="CSS/Tailwind styles",
                input_types=["design_spec"],
                output_types=["css"],
            ),
            AgentCapability(
                name="state_management",
                description="State management module",
                input_types=["state_spec"],
                output_types=["typescript"],
            ),
        ]


    async def _process_task(self, task_id: str, description: str, context: Dict[str, Any]) -> TaskResult:
        """Process a frontend task and return the result."""
        logger.info(f"Processing frontend task: {task_id}")

        task_type = context.get("task_type", "react_component")
        requirements = context.get("requirements", {})

        output = ""
        files_created = []

        if task_type == "react_component":
            output = await self._create_react_component(requirements)
            files_created.append(f"src/components/{requirements.get('component_name', 'UserComponent')}.tsx")
        elif task_type == "vue_component":
            output = await self._create_vue_component(requirements)
            files_created.append(f"src/components/{requirements.get('component_name', 'UserComponent')}.vue")
        elif task_type == "styling":
            output = await self._create_styling(requirements)
            files_created.append(f"src/styles/{requirements.get('style_name', 'styles')}.css")
        elif task_type == "state_management":
            output = await self._create_state_management(requirements)
            files_created.append(f"src/store/{requirements.get('store_name', 'store')}.ts")

        return TaskResult(
            task_id=task_id,
            success=True,
            output=output,
            files_created=files_created,
        )

    async def _create_react_component(self, requirements: Dict[str, Any]) -> str:
        """Create a React component with props, state, and hooks."""
        component_name = requirements.get("component_name", "UserComponent")
        props = requirements.get("props", [])
        state = requirements.get("state", [])
        hooks = requirements.get("hooks", [])

        code = "import React"

        if "useState" in hooks or state:
            code += ", { useState }"
        if "useEffect" in hooks:
            code += ", { useEffect }"
        if "useContext" in hooks:
            code += ", { useContext }"

        code += " from 'react';\n\n"

        if props:
            code += f"interface {component_name}Props {{\n"
            for prop in props:
                code += f"  {prop['name']}: {prop.get('type', 'any')};\n"
            code += "}\n\n"

        props_str = ", ".join([p["name"] for p in props])
        code += f"const {component_name}: React.FC<{component_name}Props> = ({props_str}) => {{\n"

        for s in state:
            code += f"  const [{s['name']}, set{s['name'].title()}] = useState<{s.get('type', 'any')}>({s.get('initial', 'null')});\n"

        code += "\n"

        if "useEffect" in hooks:
            code += "  useEffect(() => {\n"
            code += "    // Side effects\n"
            code += "  }, []);\n\n"

        for prop in props:
            if prop.get("isEvent"):
                code += f"  const handle{prop['name'].title()} = () => {{\n"
                code += f"    // Handle {prop['name']}\n"
                code += "  };\n\n"

        code += "  return (\n"
        code += f'    <div className="{component_name.lower()}">\n'
        code += f"      <h2>{component_name}</h2>\n"

        for prop in props:
            if not prop.get("isEvent"):
                code += f"      <p>{{${'{'}{prop['name']}{'}'}}}</p>\n"

        code += "    </div>\n"
        code += "  );\n"
        code += "};\n\n"

        code += f"export default {component_name};\n"

        return code

    async def _create_vue_component(self, requirements: Dict[str, Any]) -> str:
        """Create a Vue component with template, script, and scoped styles."""
        component_name = requirements.get("component_name", "UserComponent")
        props = requirements.get("props", [])
        data = requirements.get("data", [])
        methods = requirements.get("methods", [])

        code = "<template>\n"
        code += f'  <div class="{component_name.lower()}">\n'
        code += f"    <h2>{component_name}</h2>\n"

        for prop in props:
            if not prop.get("isEvent"):
                code += f"    <p>{{{{ {prop['name']} }}}}</p>\n"

        code += "  </div>\n"
        code += "</template>\n\n"

        code += '<script setup lang="ts">\n'

        if props:
            code += "defineProps<{\n"
            for prop in props:
                code += f"  {prop['name']}: {prop.get('type', 'any')};\n"
            code += ">();\n\n"

        for d in data:
            code += f"const {d['name']} = ref<{d.get('type', 'any')}>({d.get('initial', 'null')});\n"

        code += "\n"

        for method in methods:
            code += f"const {method['name']} = () => {{\n"
            code += f"  // {method.get('description', '')}\n"
            code += "};\n\n"

        code += "</script>\n\n"

        code += "<style scoped>\n"
        code += f".{component_name.lower()} {{\n"
        code += "  /* Component styles */\n"
        code += "}\n"
        code += "</style>\n"

        return code

    async def _create_styling(self, requirements: Dict[str, Any]) -> str:
        """Create CSS or Tailwind styles."""
        style_name = requirements.get("style_name", "styles")
        use_tailwind = requirements.get("use_tailwind", True)

        if use_tailwind:
            code = f"/* {style_name} - Tailwind CSS */\n\n"
            code += "/* Custom utilities */\n"
            code += "@layer utilities {\n"
            code += "  .glass {\n"
            code += "    @apply bg-white/10 backdrop-blur-lg border border-white/20;\n"
            code += "  }\n\n"
            code += "  .card {\n"
            code += "    @apply bg-white rounded-xl shadow-lg p-6;\n"
            code += "  }\n\n"
            code += "  .btn-primary {\n"
            code += "    @apply bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors;\n"
            code += "  }\n\n"
            code += "  .btn-secondary {\n"
            code += "    @apply bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold py-2 px-4 rounded-lg transition-colors;\n"
            code += "  }\n"
            code += "}\n\n"
            code += "/* Animations */\n"
            code += "@keyframes fade-in {\n"
            code += "  from { opacity: 0; transform: translateY(-10px); }\n"
            code += "  to { opacity: 1; transform: translateY(0); }\n"
            code += "}\n\n"
            code += ".animate-fade-in {\n"
            code += "  animation: fade-in 0.3s ease-out;\n"
            code += "}\n"
        else:
            code = f"/* {style_name} - CSS */\n\n"
            code += ":root {\n"
            code += "  --primary-color: #3b82f6;\n"
            code += "  --secondary-color: #6b7280;\n"
            code += "  --background-color: #ffffff;\n"
            code += "  --text-color: #1f2937;\n"
            code += "}\n\n"
            code += ".container {\n"
            code += "  max-width: 1200px;\n"
            code += "  margin: 0 auto;\n"
            code += "  padding: 0 1rem;\n"
            code += "}\n\n"
            code += ".card {\n"
            code += "  background: var(--background-color);\n"
            code += "  border-radius: 0.5rem;\n"
            code += "  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);\n"
            code += "  padding: 1.5rem;\n"
            code += "}\n\n"
            code += ".btn {\n"
            code += "  display: inline-flex;\n"
            code += "  align-items: center;\n"
            code += "  padding: 0.5rem 1rem;\n"
            code += "  border-radius: 0.375rem;\n"
            code += "  font-weight: 600;\n"
            code += "  transition: all 0.2s;\n"
            code += "}\n"

        return code

    async def _create_state_management(self, requirements: Dict[str, Any]) -> str:
        """Create a Zustand state management store."""
        store_name = requirements.get("store_name", "appStore")
        state = requirements.get("state", [])
        actions = requirements.get("actions", [])

        code = 'import { create } from "zustand";\n\n'

        code += f"interface {store_name.title()}State {{\n"
        for s in state:
            code += f"  {s['name']}: {s.get('type', 'any')};\n"
        for action in actions:
            code += f"  {action['name']}: {action.get('params', '()')}: void;\n"
        code += "}\n\n"

        code += f"export const use{store_name.title()} = create<{store_name.title()}State>((set) => ({{\n"

        for s in state:
            code += f"  {s['name']}: {s.get('initial', 'null')},\n"

        code += "\n"

        for action in actions:
            code += f"  {action['name']}: ({action.get('params', '')}) =>\n"
            code += "    set((state) => ({\n"
            code += f"      // {action.get('description', '')}\n"
            code += "    })),\n"

        code += "}));\n"

        return code


