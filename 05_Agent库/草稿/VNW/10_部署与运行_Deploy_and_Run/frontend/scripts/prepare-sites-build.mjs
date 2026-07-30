import { cp, mkdir, readdir, rename, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'

const dist = path.resolve('dist')
const client = path.join(dist, 'client')
const server = path.join(dist, 'server')

await rm(client, { recursive: true, force: true })
await mkdir(client, { recursive: true })
await mkdir(server, { recursive: true })

for (const entry of await readdir(dist)) {
  if (entry === 'client' || entry === 'server') continue
  await rename(path.join(dist, entry), path.join(client, entry))
}

const worker = `export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request)
    if (response.status !== 404 || request.method !== 'GET') return response
    const url = new URL(request.url)
    url.pathname = '/index.html'
    return env.ASSETS.fetch(new Request(url, request))
  },
}
`

await writeFile(path.join(server, 'index.js'), worker)
for (const entry of await readdir(client)) {
  await cp(path.join(client, entry), path.join(dist, entry), { recursive: true })
}
