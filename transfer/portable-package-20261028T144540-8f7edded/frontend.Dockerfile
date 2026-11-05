FROM nginxinc/nginx-unprivileged:alpine
COPY app/static/index.html /usr/share/nginx/html/index.html
COPY app/static/ /usr/share/nginx/html/static/
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
