import {build} from 'esbuild'
import {mkdtempSync, readdirSync, rmSync} from 'node:fs'
import {resolve, join} from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'
const root = fileURLToPath(new URL('..', import.meta.url))
const tests = resolve(root, 'tests')
const directory = mkdtempSync(join(root, '.ui-tests-'))
try {
    // TypeScript tests are bundled first; plain .mjs tests run as they are.
    const files = readdirSync(tests)
    const entryPoints = files.filter((name) => /\.test\.tsx?$/.test(name)).map((name) => resolve(tests, name))
    const plainTests = files.filter((name) => name.endsWith('.test.mjs')).map((name) => resolve(tests, name))
    await build({
        entryPoints,
        outdir: directory,
        bundle: true,
        platform: 'node',
        format: 'esm',
        jsx: 'automatic',
        // Pick react-switch's ES module build, as Vite's dev server does.
        conditions: ['development'],
        loader: {'.css': 'empty'},
        plugins: [{
            name: 'external-packages-except-react-switch',
            setup(build) {
                build.onResolve({filter: /^[^./]/}, (args) => (
                    args.path === 'react-switch' || args.path.startsWith('virtual:')
                        ? undefined
                        : {path: args.path, external: true}
                ))
            },
        }, {
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
            ...entryPoints.map((file) => join(directory, file.slice(tests.length + 1).replace(/\.tsx?$/, '.js'))),
            ...plainTests,
        ],
        {stdio:'inherit'},
    )
} finally {
    rmSync(directory, {recursive:true,force:true})
}
