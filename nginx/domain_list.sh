#!/usr/bin/env bash

docker compose run certbot certonly --webroot -w /var/www/certbot \
  -d joshowen.uk \
  -d auth.joshowen.uk \
  -d books-request.joshowen.uk \
  -d books.joshowen.uk \
  -d budget.joshowen.uk \
  -d docs.joshowen.uk \
  -d pdf.joshowen.uk \
  -d tools.joshowen.uk \
  -d factorio.joshowen.uk \
