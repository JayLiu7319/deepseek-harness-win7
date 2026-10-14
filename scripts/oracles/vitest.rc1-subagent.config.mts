import { defineConfig } from './official/node_modules/vitest/dist/config.js'
import base from './vitest.agent-lifecycle.config.mts'

export default defineConfig({ ...base, test: { ...base.test, include: [
  'reference/packages/subagent/subagent/tests/*.spec.ts',
  'reference/packages/subagent/tool-subagent-control/tests/*.spec.ts',
] } })
