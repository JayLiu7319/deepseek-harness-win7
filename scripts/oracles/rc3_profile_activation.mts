// Candidate-only observation. Never imports client bytes into the product checkout.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh output directory required')
const source = resolve(sourceArg), output = resolve(outputArg)
const pin = execFileSync('git', ['-C', source, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
if (pin !== 'a4c74a91e06b00fe0b0937bde982170c526cc842'
    || execFileSync('git', ['-C', source, 'status', '--porcelain'], { encoding: 'utf8' }).trim()) {
  throw new Error('Unchanged rc.3 Source required')
}
if (existsSync(output)) throw new Error('Fresh output directory required')
mkdirSync(output, { recursive: true })
const home = join(output, 'home'), workspace = join(output, 'workspace')
mkdirSync(workspace)
mkdirSync(join(home, 'profiles/web'), { recursive: true })
writeFileSync(join(home, 'profiles/web/package.json'), JSON.stringify({
  name: 'rc3-activation-observation', private: true, type: 'module',
  dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'], patchReload: 'startup' } },
}) + '\n', 'utf8')
process.env.DSH_HOME = home
process.env.DSH_TELEMETRY_DISABLED = '1'
process.chdir(workspace)
const { runProfile } = await import(pathToFileURL(join(source, 'apps/cli/src/profile-boot.ts')).href)
const { createLaunchEnvironmentSnapshot } = await import(pathToFileURL(join(source, 'packages/util/launch-environment/src/index.ts')).href)
const record: any = { sourceCommit: pin, node: process.version, presets: [], scope: 'Source web activation; no model request or browser execution' }
let runtime: any
try {
  runtime = await runProfile({ profile: 'web', patchFiles: [], args: ['--no-open', '--port', '0'],
    environment: createLaunchEnvironmentSnapshot([{ source: 'process', values: { DSH_HOME: home, DSH_TELEMETRY_DISABLED: '1' } }]) })
  const ctx = runtime.ctx
  const created = await ctx.get('workspaceController').create({ path: workspace })
  for (const [index, preset] of ['minimal', 'standard', 'cordis'].entries()) {
    const sessionId = `session-11111111-1111-4111-8111-${String(index + 1).padStart(12, '0')}`
    await ctx.get('sessionController').create({ sessionId, workspaceId: created.workspace.workspaceId, agentPreset: preset })
    const agent = ctx.get('agents').get(sessionId)
    if (!agent) throw new Error(`Preset ${preset} did not activate an Agent`)
    record.presets.push({ preset, tools: ctx.get('tools').schemas(agent).map((tool: any) => tool.name).sort(),
      entries: [...ctx.loader.entries()].map((entry: any) => ({ id: entry.id, name: entry.options.name,
        disabled: entry.disabled, state: entry.fiber?.state ?? null })),
      sessionVersion: ctx.get('sessions').get(sessionId).header.version })
  }
  record.clientGraph = ctx.get('clientModules').graph()
} catch (error) {
  record.failure = error instanceof Error ? error.stack : String(error)
  process.exitCode = 1
} finally {
  if (runtime) await runtime.shutdown.shutdown(record.failure ? 1 : 0)
  writeFileSync(join(output, 'activation.json'), JSON.stringify(record, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
}
