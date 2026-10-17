import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// vitest runs from the frontend folder
const read = (name) => readFileSync(join(process.cwd(), name), 'utf8')

const vercel = JSON.parse(read('vercel.json'))
const html = read('index.html')

const headers = Object.fromEntries(
  vercel.headers.flatMap((rule) => rule.headers.map((h) => [h.key, h.value])),
)
const csp = Object.fromEntries(
  headers['Content-Security-Policy'].split(';').map((d) => {
    const [name, ...values] = d.trim().split(/\s+/)
    return [name, values]
  }),
)

describe('vercel.json security headers', () => {
  it('applies to every path and keeps the single-page-app rewrite', () => {
    expect(vercel.headers[0].source).toBe('/(.*)')
    expect(vercel.rewrites[0].destination).toBe('/index.html')
  })

  it('sends the basic hardening headers', () => {
    expect(headers['X-Content-Type-Options']).toBe('nosniff')
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(headers['Referrer-Policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['Permissions-Policy']).toContain('camera=()')
  })

  it('does not allow inline or eval script, framing, or foreign base/form targets', () => {
    expect(csp['script-src']).not.toContain("'unsafe-inline'")
    expect(csp['script-src']).not.toContain("'unsafe-eval'")
    expect(csp['frame-ancestors']).toEqual(["'none'"])
    expect(csp['base-uri']).toEqual(["'self'"])
    expect(csp['form-action']).toEqual(["'self'"])
  })

  it('still lets Google sign-in, Google fonts and the API through', () => {
    expect(csp['script-src']).toContain('https://accounts.google.com/gsi/client')
    expect(csp['font-src']).toContain('https://fonts.gstatic.com')
    expect(csp['style-src']).toContain('https://fonts.googleapis.com')
    expect(csp['connect-src'].join(' ')).toContain('onrender.com')
  })

  it('index.html has no inline script the policy would block', () => {
    const inline = [...html.matchAll(/<script\b([^>]*)>/g)].filter((m) => !/\bsrc=/.test(m[1]))
    expect(inline).toEqual([])
  })
})
