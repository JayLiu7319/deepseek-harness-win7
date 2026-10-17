// Pinned upstream fixtures resolve repository-relative paths from cwd.
// Vitest keeps its explicit root/include paths; only forked test code uses Source cwd.
import {fileURLToPath} from 'node:url'
process.chdir(fileURLToPath(new URL('../../reference/', import.meta.url)))
