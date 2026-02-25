@REM cd HDnn-PIM-Opt/cimloop/workspace/
set DOCKER_ARCH=amd64
docker compose pull
docker compose up --build -d
docker compose exec tutorial bash
@REM cd ../../