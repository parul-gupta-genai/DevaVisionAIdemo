# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package.json and install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source code and build
COPY . .
RUN npm run build

# Serve stage using NGINX
FROM nginx:alpine

# Copy custom NGINX configuration for React Router
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets to NGINX serve directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
