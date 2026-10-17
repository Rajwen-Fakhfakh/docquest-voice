/** @type {import('next').NextConfig} */
const nextConfig = {
  // Image de prod minimale (voir frontend/Dockerfile) : ne copie que le nécessaire pour `next start`.
  output: "standalone",
};

module.exports = nextConfig;
