const isGitHubPages = process.env.GITHUB_PAGES === '1'

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(isGitHubPages && {
    output: 'export',
    basePath: '/Andro-DLS',
    assetPrefix: '/Andro-DLS/',
  }),
  images: { unoptimized: true },
  trailingSlash: true,
}

module.exports = nextConfig
