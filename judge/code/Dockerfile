# Separate, disposable Docker daemon for local code execution. No host socket.
FROM docker:28-dind
COPY sandbox/Dockerfile /opt/aura-code/Dockerfile
COPY judge/code/start.sh /usr/local/bin/aura-code-start
RUN chmod 755 /usr/local/bin/aura-code-start
ENV DOCKER_TLS_CERTDIR=""
ENTRYPOINT ["/usr/local/bin/aura-code-start"]
