# Interfaz estática (React + Vite) servida por nginx, que además hace de proxy
# hacia las réplicas de la API en el mismo origen (cookies sin CORS). (E08)

FROM node:20-bookworm-slim AS compilacion
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=compilacion /web/dist /usr/share/nginx/html
# La imagen oficial procesa /etc/nginx/templates/*.template con envsubst y solo
# reemplaza variables definidas en el entorno: $host o $remote_addr quedan intactas.
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV API_UPSTREAM=api:8001
EXPOSE 8080
