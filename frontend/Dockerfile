# Bagheera frontend — build the Vite bundle, serve it with nginx.
# nginx also reverse-proxies /api/* to the backend container, so the app's relative
# /api paths stay same-origin (no domain, no CORS, no code change needed).

# --- Stage 1: build the static bundle -------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- Stage 2: serve with nginx --------------------------------------------------------
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
