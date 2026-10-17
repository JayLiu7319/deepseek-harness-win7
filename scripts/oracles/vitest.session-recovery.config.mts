import { defineConfig } from './official/node_modules/vitest/dist/config.js'
import base from './vitest.agent-lifecycle.config.mts'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, writeFileSync, symlinkSync, unlinkSync, rmdirSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

// Upstream's new generation collision test unconditionally creates a file
// symlink. This Windows token may lack that privilege. Probe the actual host;
// only that exact test may skip, only for observed EPERM. Other errors fail.
let unavailableSymlink = false
if (process.platform === 'win32') {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-source-symlink-'))
  const target = join(directory, 'target'), link = join(directory, 'link')
  try {
    writeFileSync(target, 'owned symlink capability probe', {flag:'wx'})
    try { symlinkSync(target, link, 'file') }
    catch (error:any) {
      if (error.code !== 'EPERM') throw error
      unavailableSymlink = true
      console.error(JSON.stringify({sourceEnvironmentSkip:'file-symlink-privilege',code:error.code,
        test:'fails loud without altering a colliding symlink target'}))
    }
  } finally {
    try { unlinkSync(link) } catch (error:any) { if(error.code !== 'ENOENT')throw error }
    unlinkSync(target)
    rmdirSync(directory)
  }
}
export default defineConfig({ ...base, test: { ...base.test,
  ...(unavailableSymlink ? {testNamePattern:/^(?!.*fails loud without altering a colliding symlink target$)/} : {}),
  setupFiles: [fileURLToPath(new URL('./source-working-directory.mts', import.meta.url))],
  include: [
  'reference/packages/core/session/tests/repair.spec.ts',
  'reference/packages/session/session-persistence/tests/storage-contract.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/jsonl.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/content-admission.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/generation.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/lease.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/migration-refusal.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/migration-verifier.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/multi-edge-publication.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/v2-ptc-migration.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/v2-system-migration.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/v3-event-admission.spec.ts',
  'reference/packages/session/session-persistence-jsonl/tests/win32.spec.ts',
] } })
