FROM caddy:2.11.4-alpine
# The official binary requests CAP_NET_BIND_SERVICE. Under a non-root user with
# cap_drop: ALL this file capability makes exec fail before Caddy starts. The
# fixture only binds 8443, so strip it instead of granting a runtime capability.
# Upstream includes libcap (setcap/getcap); fail the build if removal is incomplete.
RUN setcap -r /usr/bin/caddy \
    && test -z "$(getcap /usr/bin/caddy)" \
    && caddy version
