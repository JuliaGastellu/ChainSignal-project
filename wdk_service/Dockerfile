FROM node:20-bookworm

WORKDIR /app

COPY package*.json ./

RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN npm ci --omit=dev

COPY . .

EXPOSE 3001

CMD ["node", "server.js"]
