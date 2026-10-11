import {build} from 'esbuild'
import {mkdtempSync, rmSync} from 'node:fs'
import {resolve, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'

const root = fileURLToPath(new URL('..', import.meta.url))
const directory = mkdtempSync(join(root, '.catalog-cache-tests-'))

try {
    await build({
        entryPoints: [resolve(root, 'tests/dailywireCatalogCache.test.ts')],
        outdir: directory,
        bundle: true,
        platform: 'node',
        format: 'esm',
        packages: 'external',
    })
    execFileSync(
        process.execPath,
        ['--test', join(directory, 'dailywireCatalogCache.test.js')],
        {stdio: 'inherit'},
    )
} finally {
    rmSync(directory, {recursive: true, force: true})
}
