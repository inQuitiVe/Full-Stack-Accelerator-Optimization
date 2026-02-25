cd HDnn-PIM-Opt/cimloop/workspace/
$env:DOCKER_ARCH="amd64"
docker compose pull
docker compose up -d
docker compose exec tutorial bash
cd ../../