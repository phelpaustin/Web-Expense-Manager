# Frontend image: build the React app, then serve it with nginx, which also forwards /api to the backend.
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
# Empty API URL = same origin: the browser calls /api on the page it was loaded from.
ARG VITE_GOOGLE_CLIENT_ID=
ENV VITE_API_URL= VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/onprem/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
