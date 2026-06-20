#!/usr/bin/env bash

docker compose run --rm --no-deps certbot certonly --webroot -w /var/www/certbot \
  -d assistant.joshowen.uk \
  -d auth.joshowen.uk \
  -d beszel.joshowen.uk \
  -d books-request.joshowen.uk \
  -d books.joshowen.uk \
  -d budget.joshowen.uk \
  -d debrid.joshowen.uk \
  -d docs.joshowen.uk \
  -d dockge.joshowen.uk \
  -d factorio.joshowen.uk \
  -d ha.joshowen.uk \
  -d joshowen.uk \
  -d ntfy.joshowen.uk \
  -d obsidian.joshowen.uk \
  -d pdf.joshowen.uk \
  -d tools.joshowen.uk \
