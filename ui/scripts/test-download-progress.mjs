import {build} from 'esbuild'
import {mkdtempSync, rmSync} from 'node:fs'
import {resolve, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'
const root = fileURLToPath(new URL('..', import.meta.url))
const directory = mkdtempSync(join(root, '.progress-tests-'))
try {
    const outfile = join(directory, 'tests.mjs')
    await build({entryPoints:[resolve(root, 'tests/downloadProgress.test.tsx')],outfile,bundle:true,platform:'node',format:'esm',packages:'external',jsx:'automatic',loader:{'.css':'empty'}})
    execFileSync(process.execPath, ['--test', outfile], {stdio:'inherit'})
} finally {
    rmSync(directory, {recursive:true,force:true})
}
