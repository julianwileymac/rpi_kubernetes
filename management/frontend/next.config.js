/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  
  // Environment variables
  env: {
    API_URL: process.env.API_URL || 'http://localhost:8080',
  },
  
  // Rewrites for API proxy in development
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.API_URL || 'http://localhost:8080'}/api/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
