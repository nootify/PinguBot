if ! [ -x "$(command -v docker)" ]; then
  echo 'Error: docker is not installed.' >&2
  exit 1
fi

if ! [ -x "$(command -v gzip)" ]; then
  echo 'Error: gzip is not installed.' >&2
  exit 1
fi

cp -v .gitignore .dockerignore
docker build -t bots/pingubot-build:latest .
docker save bots/pingubot-build:latest | gzip > pingubot-build.tar.gz
rm -fr .dockerignore