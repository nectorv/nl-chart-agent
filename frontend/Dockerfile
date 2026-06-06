FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM node:20-alpine
RUN npm install -g serve
COPY --from=builder /app/dist /dist
CMD ["/bin/sh", "-c", "echo 'starting serve on port '${PORT:-3000} && serve -s /dist -l ${PORT:-3000}"]
