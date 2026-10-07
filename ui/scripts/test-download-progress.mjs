import {build} from 'esbuild'
import {mkdtempSync, rmSync} from 'node:fs'
import {resolve, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'
const root = fileURLToPath(new URL('..', import.meta.url))
const directory = mkdtempSync(join(root, '.progress-tests-'))
try {
    const entryPoints = [
        resolve(root, 'tests/downloadProgress.test.tsx'),
        resolve(root, 'tests/safeDelayUi.test.tsx'),
    ]
    await build({
        entryPoints,
        outdir: directory,
        bundle: true,
        platform: 'node',
        format: 'esm',
        packages: 'external',
        jsx: 'automatic',
        loader: {'.css': 'empty'},
        plugins: [{
            name: 'wireloft-version-test',
            setup(build) {
                build.onResolve({filter: /^virtual:wireloft-version$/}, () => ({
                    path: 'wireloft-version',
                    namespace: 'wireloft-version-test',
                }))
                build.onLoad({filter: /.*/, namespace: 'wireloft-version-test'}, () => ({
                    contents: 'export const WIRELOFT_VERSION = "test"',
                    loader: 'js',
                }))
            },
        }],
    })
    execFileSync(
        process.execPath,
        [
            '--test',
            join(directory, 'downloadProgress.test.js'),
            join(directory, 'safeDelayUi.test.js'),
        ],
        {stdio:'inherit'},
    )
} finally {
    rmSync(directory, {recursive:true,force:true})
}
