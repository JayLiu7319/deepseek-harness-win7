/** Export the unchanged Source data table, never a handwritten catalog. */
import {join,resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
import {writeFileSync} from 'node:fs'
const [source,output]=process.argv.slice(2)
const {OPEN_IN_APP_CATALOG}=await import(pathToFileURL(join(resolve(source),'packages/host/open-in-app/src/catalog.ts')).href)
writeFileSync(output,JSON.stringify(OPEN_IN_APP_CATALOG,null,2)+'\n','utf8')
